import json
import os
import secrets
import sqlite3
import hashlib
import smtplib
import time
from email.message import EmailMessage
from datetime import datetime, timedelta, timezone

import stripe
from flask import jsonify, request

try:
    from config_loader import CONFIG as APP_CONFIG
except Exception:  # pragma: no cover
    APP_CONFIG = {}

try:
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail
except Exception:  # pragma: no cover
    SendGridAPIClient = None
    Mail = None

try:
    from twilio.rest import Client as TwilioClient
except Exception:  # pragma: no cover
    TwilioClient = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'license_store.db')
PRICE_MAP_PATH = os.getenv('PRICE_MAP_PATH', os.path.join(BASE_DIR, 'price_map.json'))
LICENSE_SECRET = os.getenv('LICENSE_SECRET', 'CHANGE_ME')
if LICENSE_SECRET == 'CHANGE_ME':
    print("[LICENSE] WARNING: LICENSE_SECRET is using the default value. "
          "Set the LICENSE_SECRET env var in production or license keys can be forged.")

STRIPE_SECRET_KEY = os.getenv('STRIPE_SECRET_KEY') or APP_CONFIG.get('STRIPE_SECRET_KEY')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET') or APP_CONFIG.get('STRIPE_WEBHOOK_SECRET')
HUB_BASE_URL = os.getenv('HUB_BASE_URL') or APP_CONFIG.get('HUB_BASE_URL')

SENDGRID_API_KEY = os.getenv('SENDGRID_API_KEY')
SENDGRID_FROM_EMAIL = os.getenv('SENDGRID_FROM_EMAIL')

# Gmail SMTP (simplest, free) — preferred email channel. Requires a Google
# "App Password" (16 chars, needs 2-Step Verification enabled on the account).
GMAIL_ADDRESS = os.getenv('GMAIL_ADDRESS') or APP_CONFIG.get('GMAIL_ADDRESS')
GMAIL_APP_PASSWORD = os.getenv('GMAIL_APP_PASSWORD') or APP_CONFIG.get('GMAIL_APP_PASSWORD')

TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_FROM_NUMBER = os.getenv('TWILIO_FROM_NUMBER')


def _norm_email(value):
    return (value or '').strip().lower()


# ── Admin brute-force lockout ─────────────────────────────────────────────────
# Granting/revoking licenses is owner-only. These endpoints require the exact
# LICENSE_SECRET, and this locks out an IP after repeated bad guesses so the
# secret can't be brute-forced.
_ADMIN_FAILS = {}            # ip -> (fail_count, locked_until_epoch)
_ADMIN_MAX_FAILS = 5
_ADMIN_LOCK_SECONDS = 900    # 15-minute lockout after too many bad secrets


def _admin_check(req):
    """Verify the admin bearer secret with per-IP lockout.
    Returns (ok: bool, error_response_or_None)."""
    ip = (req.headers.get('X-Forwarded-For', '') or req.remote_addr or 'unknown').split(',')[0].strip()
    now = time.time()
    rec = _ADMIN_FAILS.get(ip)
    if rec and rec[1] > now:
        return False, (jsonify({'error': 'Too many attempts — temporarily locked out.'}), 429)
    auth = req.headers.get('Authorization', '').strip()
    secret = auth[len('Bearer '):] if auth.startswith('Bearer ') else ''
    if LICENSE_SECRET == 'CHANGE_ME' or not secret or secret != LICENSE_SECRET:
        count = (rec[0] if rec else 0) + 1
        until = now + _ADMIN_LOCK_SECONDS if count >= _ADMIN_MAX_FAILS else 0
        _ADMIN_FAILS[ip] = (count, until)
        return False, (jsonify({'error': 'Unauthorized. Use: Authorization: Bearer <LICENSE_SECRET>'}), 403)
    _ADMIN_FAILS.pop(ip, None)   # success clears the counter
    return True, None


def register_license_routes(app):
    init_db()
    if STRIPE_SECRET_KEY and LICENSE_SECRET == 'CHANGE_ME':
        print("[LICENSE] WARNING: LICENSE_SECRET is still the default. "
              "Set a strong LICENSE_SECRET env var before selling licenses.")

    @app.route('/api/license/start', methods=['POST'])
    def start_verification():
        payload = request.json or {}
        email = _norm_email(payload.get('email'))
        phone = (payload.get('phone') or '').strip()
        app_id = (payload.get('appId') or '').strip()
        tier = (payload.get('tier') or '').strip()

        if not app_id or not tier:
            return jsonify({'error': 'appId and tier are required'}), 400

        if not email and not phone:
            return jsonify({'error': 'email or phone is required'}), 400

        code = f"{secrets.randbelow(1000000):06d}"
        verification_id = secrets.token_urlsafe(16)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)

        store_verification(verification_id, email, phone, app_id, tier, code, expires_at)

        delivery = []
        try:
            if email:
                send_email_code(email, code, app_id, tier)
                delivery.append('email')
            if phone:
                send_sms_code(phone, code, app_id, tier)
                delivery.append('sms')
        except Exception as exc:
            delete_verification(verification_id)
            return jsonify({'error': str(exc)}), 500

        return jsonify({'verificationId': verification_id, 'delivery': delivery})

    @app.route('/api/license/verify', methods=['POST'])
    def verify_code():
        payload = request.json or {}
        verification_id = (payload.get('verificationId') or '').strip()
        code = (payload.get('code') or '').strip()

        if not verification_id or not code:
            return jsonify({'error': 'verificationId and code are required'}), 400

        record = get_verification(verification_id)
        if not record:
            return jsonify({'error': 'verification not found'}), 404

        if record['expires_at'] < datetime.now(timezone.utc):
            return jsonify({'error': 'verification expired'}), 400

        if record['code_hash'] != hash_code(code):
            return jsonify({'error': 'invalid code'}), 400

        mark_verification_verified(verification_id)
        return jsonify({'status': 'verified'})

    @app.route('/api/checkout', methods=['POST'])
    def create_checkout():
        payload = request.json or {}
        verification_id = (payload.get('verificationId') or '').strip()
        email = _norm_email(payload.get('email'))
        app_id = (payload.get('appId') or '').strip()
        tier = (payload.get('tier') or '').strip()

        if not verification_id or not email or not app_id or not tier:
            return jsonify({'error': 'verificationId, email, appId, tier required'}), 400

        record = get_verification(verification_id)
        if not record or not record['verified']:
            return jsonify({'error': 'verification required'}), 400

        if record['expires_at'] < datetime.now(timezone.utc):
            return jsonify({'error': 'verification expired'}), 400

        price_info = get_price_info(app_id, tier)
        if not price_info:
            return jsonify({'error': 'missing price configuration'}), 400

        if not STRIPE_SECRET_KEY:
            return jsonify({'error': 'stripe not configured'}), 500

        stripe.api_key = STRIPE_SECRET_KEY
        success_url, cancel_url = build_redirect_urls()

        session = stripe.checkout.Session.create(
            mode=price_info['mode'],
            line_items=[{'price': price_info['priceId'], 'quantity': 1}],
            success_url=success_url,
            cancel_url=cancel_url,
            customer_email=email,
            metadata={
                'app_id': app_id,
                'tier': tier,
                'verification_id': verification_id,
            },
        )

        return jsonify({'sessionId': session.id, 'url': session.url})

    @app.route('/api/license/confirm', methods=['POST'])
    def confirm_license():
        payload = request.json or {}
        session_id = (payload.get('sessionId') or '').strip()
        if not session_id:
            return jsonify({'error': 'sessionId required'}), 400

        if not STRIPE_SECRET_KEY:
            return jsonify({'error': 'stripe not configured'}), 500

        stripe.api_key = STRIPE_SECRET_KEY
        session = stripe.checkout.Session.retrieve(session_id)

        if session.status != 'complete':
            return jsonify({'error': 'checkout not complete'}), 400

        app_id = session.metadata.get('app_id')
        tier = session.metadata.get('tier')
        verification_id = session.metadata.get('verification_id')
        email = session.customer_email or session.get('customer_details', {}).get('email')

        if not app_id or not tier:
            return jsonify({'error': 'missing metadata'}), 400

        price_info = get_price_info(app_id, tier)
        if not price_info:
            return jsonify({'error': 'missing price configuration'}), 400

        duration_days = price_info.get('durationDays', 30)
        expires_at = datetime.now(timezone.utc) + timedelta(days=duration_days)
        license_key = generate_license_key()

        store_license(
            email=email,
            app_id=app_id,
            tier=tier,
            license_key=license_key,
            expires_at=expires_at,
            session_id=session_id,
            billing_type=price_info.get('billingType', 'monthly'),
        )

        if verification_id:
            mark_verification_consumed(verification_id)

        response = {
            'appId': app_id,
            'tier': tier,
            'email': email,
            'licenseKey': license_key,
            'status': 'active',
            'activatedAt': int(datetime.now(timezone.utc).timestamp() * 1000),
            'expiresAt': int(expires_at.timestamp() * 1000),
            'billingType': price_info.get('billingType', 'monthly'),
        }
        return jsonify(response)

    @app.route('/api/license/grant', methods=['POST'])
    def grant_license():
        """Deprecated: use /api/license/admin/grant instead."""
        payload = request.json or {}
        secret = (payload.get('secret') or '').strip()
        if LICENSE_SECRET == 'CHANGE_ME' or not secret or secret != LICENSE_SECRET:
            return jsonify({'error': 'unauthorized'}), 403
        email = _norm_email(payload.get('email'))
        app_id = (payload.get('appId') or 'alien-ai-trader').strip()
        tier = (payload.get('tier') or 'monthly').strip()
        if not email:
            return jsonify({'error': 'email required'}), 400
        price_info = get_price_info(app_id, tier) or {}
        duration = price_info.get('durationDays', 30)
        expires_at = datetime.now(timezone.utc) + timedelta(days=duration)
        key = generate_license_key()
        store_license(
            email=email,
            app_id=app_id,
            tier=tier,
            license_key=key,
            expires_at=expires_at,
            session_id='manual-grant',
            billing_type=price_info.get('billingType', 'monthly'),
        )
        return jsonify({'status': 'granted', 'email': email, 'tier': tier,
                        'licenseKey': key,
                        'expiresAt': int(expires_at.timestamp() * 1000)}), 200

    @app.route('/api/license/admin/grant', methods=['POST'])
    def admin_grant_license():
        """Admin endpoint: issue a license for any email after manual Stripe payment.
        Authorization: Bearer <LICENSE_SECRET>
        Body: {"email": "user@example.com", "appId": "alien-ai-trader", "tier": "monthly"}
        """
        ok, err = _admin_check(request)
        if err:
            return err

        payload = request.json or {}
        email = _norm_email(payload.get('email'))
        app_id = (payload.get('appId') or 'alien-ai-trader').strip()
        tier = (payload.get('tier') or 'monthly').strip()

        if not email:
            return jsonify({'error': 'email required'}), 400
        
        price_info = get_price_info(app_id, tier) or {}
        duration = price_info.get('durationDays', 30)
        expires_at = datetime.now(timezone.utc) + timedelta(days=duration)
        key = generate_license_key()
        
        store_license(
            email=email,
            app_id=app_id,
            tier=tier,
            license_key=key,
            expires_at=expires_at,
            session_id='admin-grant',
            billing_type=price_info.get('billingType', 'monthly'),
        )
        
        print(f'[LICENSE] Admin granted {tier} license to {email}')
        return jsonify({
            'status': 'granted',
            'email': email,
            'tier': tier,
            'licenseKey': key,
            'expiresAt': int(expires_at.timestamp() * 1000),
        }), 200

    @app.route('/api/license/admin/revoke', methods=['POST'])
    def admin_revoke_license():
        """Admin endpoint: revoke (delete) a license for an email.
        Authorization: Bearer <LICENSE_SECRET>
        Body: {"email": "user@example.com", "appId": "alien-ai-trader"}
        """
        ok, err = _admin_check(request)
        if err:
            return err

        payload = request.json or {}
        email = _norm_email(payload.get('email'))
        app_id = (payload.get('appId') or 'alien-ai-trader').strip()
        if not email:
            return jsonify({'error': 'email required'}), 400

        delete_license(email, app_id)
        print(f'[LICENSE] Admin revoked license for {email} ({app_id})')
        return jsonify({'status': 'revoked', 'email': email, 'appId': app_id}), 200

    @app.route('/api/license/diag', methods=['GET'])
    def license_diag():
        """Support diagnostic - reports which pieces are configured.
        Booleans and modes only; never returns secret values."""
        key = STRIPE_SECRET_KEY or ''
        mode = 'live' if key.startswith('sk_live_') else ('test' if key.startswith('sk_test_') else 'unset/invalid')
        price_map = load_price_map().get('alien-ai-trader', {})
        tiers = {}
        for tier, info in price_map.items():
            pid = info.get('priceId', '') if isinstance(info, dict) else str(info)
            tiers[tier] = {'priceId_set': bool(pid) and 'REPLACE' not in pid,
                           'priceId_prefix': pid[:9] if pid else ''}
        gmail_set = bool(GMAIL_ADDRESS and GMAIL_APP_PASSWORD)
        sendgrid_set = bool(SENDGRID_API_KEY and SENDGRID_FROM_EMAIL)
        return jsonify({
            'stripe_key_present': bool(key),
            'stripe_key_mode': mode,
            'webhook_secret_set': bool(STRIPE_WEBHOOK_SECRET),
            'license_secret_set': LICENSE_SECRET != 'CHANGE_ME',
            'gmail_set': gmail_set,
            'sendgrid_set': sendgrid_set,
            'email_ready': _email_configured(),
            'email_via': 'gmail' if gmail_set else ('sendgrid' if sendgrid_set else 'none'),
            'price_map_tiers': tiers,
        }), 200

    @app.route('/api/license/admin/diag', methods=['GET'])
    def admin_diag():
        """Diagnostics for admin license granting."""
        return jsonify({
            'license_secret_set': LICENSE_SECRET != 'CHANGE_ME',
            'stripe_key_present': bool(STRIPE_SECRET_KEY),
            'message': 'To grant a license: POST /api/license/admin/grant with Authorization: Bearer <LICENSE_SECRET>'
        }), 200

    @app.route('/api/license/pricing', methods=['GET'])
    def license_pricing():
        """Public price list for one app — the user's installed copy fetches this
        so Buy buttons always show current prices without re-downloading the app."""
        app_id = (request.args.get('appId') or '').strip()
        if not app_id:
            return jsonify({'error': 'appId required'}), 400
        tiers = load_price_map().get(app_id, {})
        out = []
        for tier, info in tiers.items():
            if isinstance(info, dict):
                out.append({
                    'tier': tier,
                    'price': info.get('price'),
                    'billingType': info.get('billingType', 'one_time'),
                    'buyUrl': info.get('buyUrl', ''),
                })
        return jsonify(out), 200

    @app.route('/api/license/validate', methods=['POST'])
    def validate_license():
        """Activation check used by installed copies of the app.
        Order of truth: local DB first, then Stripe directly — so licenses
        survive a Render disk wipe and Payment Link purchases are honored."""
        payload = request.json or {}
        email = _norm_email(payload.get('email'))
        app_id = (payload.get('appId') or '').strip()
        if not email or not app_id:
            return jsonify({'error': 'email and appId required'}), 400

        record = get_license(email, app_id)

        # Owner-issued comp licenses (admin/manual grants) have no Stripe payment
        # behind them, so the Stripe cross-check below would always see "no
        # purchase" and wrongly revoke them. Honor them directly while unexpired.
        if (record and record.get('session_id') in MANUAL_GRANT_SESSIONS
                and record['expires_at'] > datetime.now(timezone.utc)):
            return jsonify(_license_response(record)), 200

        # Stripe is the source of truth. Check it FIRST so cancellations and
        # refunds are honored instead of being masked by a stale cached record.
        found = find_active_stripe_purchase(email, app_id)
        if found:
            license_key = record['license_key'] if record else generate_license_key()
            delete_license(email, app_id)  # keep exactly one current row
            store_license(
                email=email,
                app_id=app_id,
                tier=found['tier'],
                license_key=license_key,
                expires_at=found['expires_at'],
                session_id='stripe-lookup',
                billing_type=found['billing_type'],
            )
            return jsonify(_license_response(get_license(email, app_id))), 200

        # Stripe shows no active purchase. If a cached license still looks valid,
        # only honor it when Stripe is UNREACHABLE (so a Stripe/Render outage
        # never locks out a paying user). If Stripe is reachable and says no,
        # the subscription was cancelled/refunded — revoke the cache.
        if record and record['expires_at'] > datetime.now(timezone.utc):
            if _stripe_reachable():
                delete_license(email, app_id)
                return jsonify({'status': 'none'}), 200
            return jsonify(_license_response(record)), 200

        return jsonify({'status': 'none'}), 200

    @app.route('/api/license/status', methods=['POST'])
    def license_status():
        payload = request.json or {}
        email = _norm_email(payload.get('email'))
        app_id = (payload.get('appId') or '').strip()

        if not email or not app_id:
            return jsonify({'error': 'email and appId required'}), 400

        record = get_license(email, app_id)
        if not record:
            return jsonify({'status': 'none'}), 200

        response = {
            'appId': record['app_id'],
            'tier': record['tier'],
            'email': record['email'],
            'licenseKey': record['license_key'],
            'status': 'active' if record['expires_at'] > datetime.now(timezone.utc) else 'expired',
            'activatedAt': int(record['activated_at'].timestamp() * 1000),
            'expiresAt': int(record['expires_at'].timestamp() * 1000),
            'billingType': record['billing_type'],
        }
        return jsonify(response)

    # ── Stripe webhook: auto-provision license the moment payment clears ──────
    @app.route('/api/stripe/webhook', methods=['POST'])
    def stripe_webhook():
        """Stripe calls this URL immediately after a successful payment.
        Configure it in Stripe Dashboard → Developers → Webhooks pointing to:
          https://alien-ai-trader-dashboard.onrender.com/api/stripe/webhook
        Events to send: checkout.session.completed
        """
        payload = request.get_data()
        sig_header = request.headers.get('Stripe-Signature', '')

        if STRIPE_WEBHOOK_SECRET:
            try:
                event = stripe.Webhook.construct_event(
                    payload, sig_header, STRIPE_WEBHOOK_SECRET
                )
            except stripe.error.SignatureVerificationError:
                return jsonify({'error': 'invalid signature'}), 400
            except Exception as exc:
                return jsonify({'error': str(exc)}), 400
        else:
            # No webhook secret configured — accept but log a warning
            print('[WEBHOOK] WARNING: STRIPE_WEBHOOK_SECRET not set. '
                  'Webhook signature not verified — set it in Render env vars.')
            try:
                event = json.loads(payload)
            except Exception:
                return jsonify({'error': 'invalid JSON'}), 400

        event_type = event.get('type') if isinstance(event, dict) else event['type']
        obj = (event.get('data', {}).get('object', {})
               if isinstance(event, dict)
               else event['data']['object'])

        if event_type == 'checkout.session.completed':
            _webhook_provision_license(obj)
        elif event_type in ('invoice.paid', 'invoice.payment_succeeded'):
            # Recurring renewal cleared — extend the license so paying
            # subscribers never lapse at the end of a billing cycle.
            _webhook_renew_license(obj)
        elif event_type == 'customer.subscription.deleted':
            # Cancel-at-period-end has fully ended (or an immediate cancel).
            _webhook_revoke_subscription(obj)
        elif event_type == 'customer.subscription.updated':
            sub_status = ((obj.get('status') if isinstance(obj, dict)
                           else getattr(obj, 'status', '')) or '').lower()
            if sub_status in ('canceled', 'unpaid', 'incomplete_expired'):
                _webhook_revoke_subscription(obj)
        elif event_type in ('charge.refunded', 'refund.created', 'charge.refund.updated'):
            # Refund = revoke immediately (cancels the sub + clears the cache).
            _webhook_handle_refund(obj)

        return jsonify({'status': 'ok'}), 200

    # ── Debug endpoint: why is a specific email not activating? ───────────────
    @app.route('/api/license/debug', methods=['POST'])
    def license_debug():
        """Diagnostic only — returns detailed reason why activation fails for
        a given email. Never exposes secret values."""
        payload = request.json or {}
        email = (payload.get('email') or '').strip().lower()
        app_id = (payload.get('appId') or 'alien-ai-trader').strip()
        if not email:
            return jsonify({'error': 'email required'}), 400

        result = {'email': email, 'app_id': app_id, 'checks': []}

        # 1. Local DB check
        record = get_license(email, app_id)
        if record:
            active = record['expires_at'] > datetime.now(timezone.utc)
            result['checks'].append({
                'check': 'local_db',
                'found': True,
                'active': active,
                'expires_at': record['expires_at'].isoformat(),
                'tier': record['tier'],
            })
        else:
            result['checks'].append({'check': 'local_db', 'found': False})

        # 2. Stripe key present?
        if not STRIPE_SECRET_KEY:
            result['checks'].append({'check': 'stripe_key', 'present': False,
                                     'error': 'STRIPE_SECRET_KEY not set on server'})
            return jsonify(result), 200
        result['checks'].append({'check': 'stripe_key', 'present': True})

        # 3. Stripe customer lookup
        stripe.api_key = STRIPE_SECRET_KEY
        app_prices = load_price_map().get(app_id, {})
        price_to_tier = {
            (info.get('priceId') if isinstance(info, dict) else info): tier
            for tier, info in app_prices.items()
            if (info.get('priceId') if isinstance(info, dict) else info)
        }
        expected_price_ids = list(price_to_tier.keys())
        result['checks'].append({'check': 'expected_price_ids', 'ids': expected_price_ids})

        try:
            customers = stripe.Customer.list(email=email, limit=10)
            cust_list = customers.get('data', []) if isinstance(customers, dict) else list(customers.auto_paging_iter())
            # Only get up to 10 to avoid slow iteration
            if not isinstance(customers, dict):
                cust_list = [c for c in customers.data]

            result['checks'].append({'check': 'stripe_customers_found', 'count': len(cust_list)})

            sub_details = []
            for cust in cust_list:
                cust_id = cust.get('id') if isinstance(cust, dict) else cust.id
                subs = stripe.Subscription.list(customer=cust_id, status='all', limit=20)
                sub_list = subs.get('data', []) if isinstance(subs, dict) else subs.data
                for sub in sub_list:
                    sub_status = sub.get('status') if isinstance(sub, dict) else sub.status
                    items_obj = sub.get('items', {}) if isinstance(sub, dict) else sub.items
                    item_list = items_obj.get('data', []) if isinstance(items_obj, dict) else items_obj.data
                    price_ids_on_sub = []
                    for item in item_list:
                        price_obj = item.get('price', {}) if isinstance(item, dict) else item.price
                        pid = price_obj.get('id') if isinstance(price_obj, dict) else price_obj.id
                        price_ids_on_sub.append(pid)
                    matches = [p for p in price_ids_on_sub if p in price_to_tier]
                    sub_details.append({
                        'status': sub_status,
                        'price_ids': price_ids_on_sub,
                        'matches_price_map': matches,
                        'tier': price_to_tier.get(matches[0]) if matches else None,
                    })
            result['checks'].append({'check': 'stripe_subscriptions', 'subscriptions': sub_details})
        except Exception as exc:
            result['checks'].append({'check': 'stripe_lookup_error', 'error': str(exc)})

        return jsonify(result), 200


def _webhook_provision_license(session):
    """Provision a license record from a completed Stripe checkout session.
    Called by the webhook handler — runs silently (errors are logged, not raised)."""
    try:
        # Determine customer email
        email = None
        if isinstance(session, dict):
            cd = session.get('customer_details') or {}
            email = cd.get('email') or session.get('customer_email')
        else:
            cd = getattr(session, 'customer_details', None)
            email = (getattr(cd, 'email', None) if cd else None) or getattr(session, 'customer_email', None)

        if not email:
            print('[WEBHOOK] No email found on session — cannot provision.')
            return

        email = email.strip().lower()

        # Determine app_id and tier from metadata first, then line_items
        if isinstance(session, dict):
            metadata = session.get('metadata') or {}
        else:
            metadata = dict(getattr(session, 'metadata', {}) or {})

        app_id = metadata.get('app_id', 'alien-ai-trader')
        tier = metadata.get('tier')
        session_id = (session.get('id') if isinstance(session, dict)
                      else getattr(session, 'id', 'webhook'))

        if not tier and STRIPE_SECRET_KEY:
            # Payment Link purchase — no metadata, look up line items
            stripe.api_key = STRIPE_SECRET_KEY
            try:
                items = stripe.checkout.Session.list_line_items(session_id, limit=5)
                item_list = items.get('data', []) if isinstance(items, dict) else items.data
                price_map = load_price_map()
                for item in item_list:
                    price_obj = item.get('price', {}) if isinstance(item, dict) else item.price
                    pid = price_obj.get('id') if isinstance(price_obj, dict) else price_obj.id
                    for t, info in price_map.get(app_id, {}).items():
                        expected = info.get('priceId') if isinstance(info, dict) else info
                        if expected == pid:
                            tier = t
                            break
                    if tier:
                        break
            except Exception as exc:
                print(f'[WEBHOOK] Could not retrieve line items: {exc}')

        if not tier:
            print(f'[WEBHOOK] Could not determine tier for session {session_id} — cannot provision.')
            return

        price_info = get_price_info(app_id, tier)
        if not price_info:
            print(f'[WEBHOOK] No price info for app_id={app_id} tier={tier}')
            return

        duration_days = price_info.get('durationDays', 30)
        expires_at = datetime.now(timezone.utc) + timedelta(days=duration_days)
        license_key = generate_license_key()

        # Check if license already exists (idempotent)
        existing = get_license(email, app_id)
        if existing and existing['expires_at'] > datetime.now(timezone.utc):
            print(f'[WEBHOOK] License already active for {email} — skipping duplicate.')
            return

        store_license(
            email=email,
            app_id=app_id,
            tier=tier,
            license_key=license_key,
            expires_at=expires_at,
            session_id=session_id,
            billing_type=price_info.get('billingType', 'monthly'),
        )
        print(f'[WEBHOOK] License provisioned for {email} app={app_id} tier={tier} expires={expires_at.date()}')

        # Send activation email
        try:
            _send_activation_email(email, app_id, tier, license_key)
        except Exception as exc:
            print(f'[WEBHOOK] Activation email failed (non-fatal): {exc}')

    except Exception as exc:
        print(f'[WEBHOOK] Unexpected error provisioning license: {exc}')


def _webhook_renew_license(invoice):
    """Extend a license when a recurring subscription invoice is paid.
    The FIRST invoice (billing_reason='subscription_create') is already handled
    by checkout.session.completed, so we skip it here and only stack time onto
    renewals — guaranteeing a paying subscriber never lapses at cycle end."""
    try:
        if isinstance(invoice, dict):
            billing_reason = invoice.get('billing_reason') or ''
            email = invoice.get('customer_email')
            customer_id = invoice.get('customer')
            invoice_id = invoice.get('id', 'renewal')
            lines = (invoice.get('lines') or {}).get('data', []) or []
        else:
            billing_reason = getattr(invoice, 'billing_reason', '') or ''
            email = getattr(invoice, 'customer_email', None)
            customer_id = getattr(invoice, 'customer', None)
            invoice_id = getattr(invoice, 'id', 'renewal')
            lines = list(getattr(getattr(invoice, 'lines', None), 'data', []) or [])

        # First payment is provisioned by checkout.session.completed — don't double up.
        if billing_reason == 'subscription_create':
            return

        if not email:
            email = _customer_email(customer_id)
        if not email:
            print('[WEBHOOK] Renewal: no customer email — cannot extend.')
            return
        email = _norm_email(email)

        # Identify app_id + tier from the invoice's line-item price IDs.
        app_id, tier = 'alien-ai-trader', None
        price_map = load_price_map()
        for line in lines:
            price_obj = (line.get('price') if isinstance(line, dict)
                         else getattr(line, 'price', None)) or {}
            pid = (price_obj.get('id') if isinstance(price_obj, dict)
                   else getattr(price_obj, 'id', None))
            for a_id, tiers in price_map.items():
                if not isinstance(tiers, dict):
                    continue
                for t, info in tiers.items():
                    expected = info.get('priceId') if isinstance(info, dict) else info
                    if expected and expected == pid:
                        app_id, tier = a_id, t
                        break
                if tier:
                    break
            if tier:
                break

        existing = get_license(email, app_id)
        if not tier and existing:
            tier = existing.get('tier')
        if not tier:
            print(f'[WEBHOOK] Renewal: could not determine tier for {email} — skipping.')
            return

        price_info = get_price_info(app_id, tier) or {}
        duration_days = price_info.get('durationDays', 30)

        now = datetime.now(timezone.utc)
        # Stack onto remaining time if the license is still active.
        base = existing['expires_at'] if (existing and existing['expires_at'] > now) else now
        new_expires = base + timedelta(days=duration_days)
        license_key = existing['license_key'] if existing else generate_license_key()

        store_license(
            email=email,
            app_id=app_id,
            tier=tier,
            license_key=license_key,
            expires_at=new_expires,
            session_id=invoice_id,
            billing_type=price_info.get('billingType', 'monthly'),
        )
        print(f'[WEBHOOK] Renewal extended license for {email} '
              f'app={app_id} tier={tier} -> {new_expires.date()}')

        # If the license had fully lapsed, re-send the key so they can re-activate.
        if not existing:
            try:
                _send_activation_email(email, app_id, tier, license_key)
            except Exception as exc:
                print(f'[WEBHOOK] Renewal email failed (non-fatal): {exc}')

    except Exception as exc:
        print(f'[WEBHOOK] Unexpected error renewing license: {exc}')


def _stripe_reachable():
    """Light check: is Stripe's API responding right now? Used to tell the
    difference between 'no active purchase' (revoke) and 'Stripe/Render outage'
    (keep the cached license so a paying user is never wrongly locked out)."""
    if not STRIPE_SECRET_KEY:
        return False
    try:
        stripe.api_key = STRIPE_SECRET_KEY
        stripe.Customer.list(limit=1)
        return True
    except Exception:
        return False


def _customer_email(customer_id):
    """Resolve a Stripe customer id to its email (normalized)."""
    if not customer_id or not STRIPE_SECRET_KEY:
        return None
    try:
        stripe.api_key = STRIPE_SECRET_KEY
        cust = stripe.Customer.retrieve(customer_id)
        return _norm_email(cust.get('email') if isinstance(cust, dict)
                           else getattr(cust, 'email', None))
    except Exception as exc:
        print(f'[WEBHOOK] Could not retrieve customer {customer_id}: {exc}')
        return None


def _webhook_revoke_subscription(sub, app_id='alien-ai-trader'):
    """A subscription was deleted/expired in Stripe — drop the cached license
    so the installed app downgrades to paper on its next re-check."""
    try:
        if isinstance(sub, dict):
            customer_id = sub.get('customer')
            metadata = sub.get('metadata') or {}
        else:
            customer_id = getattr(sub, 'customer', None)
            metadata = dict(getattr(sub, 'metadata', {}) or {})
        app_id = metadata.get('app_id', app_id)
        email = _customer_email(customer_id)
        if not email:
            print('[WEBHOOK] Subscription revoke: no customer email, skipping.')
            return
        delete_license(email, app_id)
        print(f'[WEBHOOK] Revoked license for {email} (subscription ended).')
    except Exception as exc:
        print(f'[WEBHOOK] Error revoking subscription: {exc}')


def _webhook_handle_refund(charge, app_id='alien-ai-trader'):
    """Refund policy = revoke immediately. Cancel the customer's active
    subscription(s) in Stripe (durable source of truth, survives DB wipes) and
    clear the cached license now."""
    try:
        customer_id = (charge.get('customer') if isinstance(charge, dict)
                       else getattr(charge, 'customer', None))
        email = _customer_email(customer_id)
        if not email:
            print('[WEBHOOK] Refund: no customer email, skipping.')
            return
        if STRIPE_SECRET_KEY and customer_id:
            stripe.api_key = STRIPE_SECRET_KEY
            try:
                subs = stripe.Subscription.list(customer=customer_id, status='all', limit=100)
                sub_list = (subs.get('data', []) if isinstance(subs, dict)
                            else list(subs.auto_paging_iter()))
                for s in sub_list:
                    s_status = ((s.get('status') if isinstance(s, dict)
                                 else getattr(s, 'status', '')) or '').lower()
                    if s_status in ('active', 'trialing', 'past_due'):
                        s_id = s.get('id') if isinstance(s, dict) else s.id
                        try:
                            stripe.Subscription.cancel(s_id)
                        except Exception:
                            stripe.Subscription.delete(s_id)  # older stripe-python
                        print(f'[WEBHOOK] Refund: cancelled subscription {s_id} for {email}.')
            except Exception as exc:
                print(f'[WEBHOOK] Refund: could not cancel subscriptions: {exc}')
        delete_license(email, app_id)
        print(f'[WEBHOOK] Revoked license for {email} (refund).')
    except Exception as exc:
        print(f'[WEBHOOK] Error handling refund: {exc}')


def _email_configured():
    """True if any email channel is usable (Gmail SMTP preferred, SendGrid fallback)."""
    gmail_ok = bool(GMAIL_ADDRESS and GMAIL_APP_PASSWORD)
    sendgrid_ok = bool(SENDGRID_API_KEY and SENDGRID_FROM_EMAIL and SendGridAPIClient and Mail)
    return gmail_ok or sendgrid_ok


def _send_email(to_email, subject, body):
    """Send a plain-text email. Prefers Gmail SMTP (free, no third-party signup);
    falls back to SendGrid if Gmail isn't configured. Returns True if sent,
    False if no channel is configured. Raises on a real send failure."""
    # 1) Gmail SMTP via App Password
    if GMAIL_ADDRESS and GMAIL_APP_PASSWORD:
        msg = EmailMessage()
        msg['Subject'] = subject
        msg['From'] = GMAIL_ADDRESS
        msg['To'] = to_email
        msg.set_content(body)
        with smtplib.SMTP('smtp.gmail.com', 587, timeout=20) as server:
            server.starttls()
            server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            server.send_message(msg)
        print(f'[EMAIL] Sent via Gmail to {to_email}: {subject}')
        return True

    # 2) SendGrid fallback
    if SENDGRID_API_KEY and SENDGRID_FROM_EMAIL and SendGridAPIClient and Mail:
        message = Mail(
            from_email=SENDGRID_FROM_EMAIL,
            to_emails=to_email,
            subject=subject,
            plain_text_content=body,
        )
        SendGridAPIClient(SENDGRID_API_KEY).send(message)
        print(f'[EMAIL] Sent via SendGrid to {to_email}: {subject}')
        return True

    return False


def _send_activation_email(email, app_id, tier, license_key):
    """Email the buyer their activation instructions immediately after purchase."""
    subject = "Your Alien AI Trader subscription is active — here's how to unlock live trading"
    body = f"""Hi,

Your payment was received and your {tier} subscription for Alien AI Trader is now active.

HOW TO ACTIVATE IN THE APP
──────────────────────────
1. Open Alien AI Trader on your computer (double-click the desktop shortcut).
2. Go to the Settings tab → "License — Live Trading" card.
3. Enter THIS email address: {email}
4. Click Activate. The badge will flip to Licensed.

Your license key (optional — email alone is enough): {license_key}

If you have any trouble, just reply to this email.

— Troy Walker · T-Dub's Apps
"""
    if _send_email(email, subject, body):
        print(f'[WEBHOOK] Activation email sent to {email}')
    else:
        print('[WEBHOOK] No email channel configured — skipping activation email.')


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS verifications (
                id TEXT PRIMARY KEY,
                email TEXT,
                phone TEXT,
                app_id TEXT,
                tier TEXT,
                code_hash TEXT,
                verified INTEGER DEFAULT 0,
                consumed INTEGER DEFAULT 0,
                expires_at TEXT
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS licenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT,
                app_id TEXT,
                tier TEXT,
                license_key TEXT,
                activated_at TEXT,
                expires_at TEXT,
                session_id TEXT,
                billing_type TEXT
            )
            """
        )
        conn.commit()


def store_verification(verification_id, email, phone, app_id, tier, code, expires_at):
    email = _norm_email(email)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO verifications (id, email, phone, app_id, tier, code_hash, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                verification_id,
                email,
                phone,
                app_id,
                tier,
                hash_code(code),
                expires_at.isoformat(),
            ),
        )
        conn.commit()


def get_verification(verification_id):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM verifications WHERE id = ?",
            (verification_id,),
        ).fetchone()
        if not row:
            return None
        return parse_verification_row(row)


def delete_verification(verification_id):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM verifications WHERE id = ?", (verification_id,))
        conn.commit()


def mark_verification_verified(verification_id):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("UPDATE verifications SET verified = 1 WHERE id = ?", (verification_id,))
        conn.commit()


def mark_verification_consumed(verification_id):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("UPDATE verifications SET consumed = 1 WHERE id = ?", (verification_id,))
        conn.commit()


def store_license(email, app_id, tier, license_key, expires_at, session_id, billing_type):
    email = _norm_email(email)
    activated_at = datetime.now(timezone.utc)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO licenses (email, app_id, tier, license_key, activated_at, expires_at, session_id, billing_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                email,
                app_id,
                tier,
                license_key,
                activated_at.isoformat(),
                expires_at.isoformat(),
                session_id,
                billing_type,
            ),
        )
        conn.commit()


def delete_license(email, app_id):
    """Revoke: remove every license row for this email+app so the next
    validate returns 'none'. Used on subscription end and on refunds."""
    email = _norm_email(email)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "DELETE FROM licenses WHERE LOWER(email) = LOWER(?) AND app_id = ?",
            (email, app_id),
        )
        conn.commit()


def get_license(email, app_id):
    email = _norm_email(email)
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM licenses WHERE LOWER(email) = LOWER(?) AND app_id = ? ORDER BY id DESC LIMIT 1",
            (email, app_id),
        ).fetchone()
        if not row:
            return None
        return parse_license_row(row)


def parse_verification_row(row):
    return {
        'id': row['id'],
        'email': row['email'],
        'phone': row['phone'],
        'app_id': row['app_id'],
        'tier': row['tier'],
        'code_hash': row['code_hash'],
        'verified': bool(row['verified']),
        'consumed': bool(row['consumed']),
        'expires_at': datetime.fromisoformat(row['expires_at']),
    }


def parse_license_row(row):
    return {
        'email': row['email'],
        'app_id': row['app_id'],
        'tier': row['tier'],
        'license_key': row['license_key'],
        'activated_at': datetime.fromisoformat(row['activated_at']),
        'expires_at': datetime.fromisoformat(row['expires_at']),
        'session_id': row['session_id'],
        'billing_type': row['billing_type'],
    }


# Comp licenses issued by the owner (admin/manual grant) have NO Stripe purchase
# behind them, so the Stripe cross-check in /validate must never revoke them.
MANUAL_GRANT_SESSIONS = {'admin-grant', 'manual-grant'}


def _license_response(record):
    resp = {
        'appId': record['app_id'],
        'tier': record['tier'],
        'email': record['email'],
        'licenseKey': record['license_key'],
        'status': 'active',
        'activatedAt': int(record['activated_at'].timestamp() * 1000),
        'expiresAt': int(record['expires_at'].timestamp() * 1000),
        'billingType': record['billing_type'],
    }
    # Sign so the installed app accepts it (the app rejects UNSIGNED licenses).
    # Requires LICENSE_PRIVATE_KEY to be set on the central server.
    try:
        from license_signing import sign_license, can_sign
        if can_sign():
            resp = sign_license(resp)
        else:
            print('[LICENSE] WARNING: LICENSE_PRIVATE_KEY not set — license cannot be '
                  'signed, so installed apps will reject it.')
    except Exception as exc:
        print(f'[LICENSE] WARNING: could not sign license: {exc}')
    return resp


def find_active_stripe_purchase(email, app_id):
    """Resolve an email to an active purchase using multiple Stripe sources.

    This keeps activation fully autonomous: buyer pays in Stripe, then enters
    the same email in the app to unlock live trading.
    """
    if not STRIPE_SECRET_KEY:
        return None

    stripe.api_key = STRIPE_SECRET_KEY
    email = _norm_email(email)

    app_prices = load_price_map().get(app_id, {})
    price_to_tier = {}
    for tier, info in app_prices.items():
        pid = info.get('priceId') if isinstance(info, dict) else info
        if pid:
            price_to_tier[pid] = (tier, info if isinstance(info, dict) else {})

    valid_sub_status = {'active', 'trialing', 'past_due'}

    def _resolve_period(tier, info, period_end):
        if period_end:
            expires_at = datetime.fromtimestamp(period_end, tz=timezone.utc)
        else:
            expires_at = datetime.now(timezone.utc) + timedelta(days=info.get('durationDays', 30))
        return {
            'tier': tier,
            'expires_at': expires_at,
            'billing_type': info.get('billingType', 'monthly'),
        }

    # 1) Fast path: customer-by-email -> subscriptions.
    #    Payment Links create a NEW Stripe customer on every checkout, so one
    #    buyer can have many duplicate customer records with the active sub on
    #    only one of them. We therefore scan ALL of them and keep the match with
    #    the furthest-out expiry — never early-returning on the first sub seen.
    #    Object access is defensive (dict OR StripeObject) to mirror the proven
    #    /api/license/debug scan.
    try:
        customers = stripe.Customer.list(email=email, limit=100)
        cust_list = (customers.get('data', []) if isinstance(customers, dict)
                     else list(customers.auto_paging_iter()))
        best = None  # furthest-expiry active match across all duplicate customers
        for cust in cust_list:
            cust_id = cust.get('id') if isinstance(cust, dict) else cust.id
            subs = stripe.Subscription.list(customer=cust_id, status='all', limit=100)
            sub_list = (subs.get('data', []) if isinstance(subs, dict)
                        else list(subs.auto_paging_iter()))
            for sub in sub_list:
                status = (sub.get('status') if isinstance(sub, dict) else sub.status) or ''
                if status.lower() not in valid_sub_status:
                    continue
                items_obj = sub.get('items', {}) if isinstance(sub, dict) else sub.items
                item_list = (items_obj.get('data', []) if isinstance(items_obj, dict)
                             else items_obj.data)
                for item in item_list:
                    price_obj = item.get('price', {}) if isinstance(item, dict) else item.price
                    pid = price_obj.get('id') if isinstance(price_obj, dict) else price_obj.id
                    if pid in price_to_tier:
                        tier, info = price_to_tier[pid]
                        period_end = (sub.get('current_period_end') if isinstance(sub, dict)
                                      else getattr(sub, 'current_period_end', None))
                        candidate = _resolve_period(tier, info, period_end)
                        if best is None or candidate['expires_at'] > best['expires_at']:
                            best = candidate
        if best:
            return best
    except Exception as exc:
        print(f'[LICENSE] Stripe lookup path 1 failed: {exc}')

    # 2) Checkout Sessions by typed checkout email (supports payment links)
    try:
        scanned = 0
        sessions = stripe.checkout.Session.list(limit=100)
        for session in sessions.auto_paging_iter():
            scanned += 1
            if scanned > 1000:
                break

            session_email = _norm_email((session.get('customer_details') or {}).get('email') or session.get('customer_email'))
            if session_email != email:
                continue
            if (session.get('status') or '').lower() != 'complete':
                continue
            if (session.get('payment_status') or '').lower() not in {'paid', 'no_payment_required'}:
                continue

            metadata = session.get('metadata') or {}
            session_app_id = (metadata.get('app_id') or app_id).strip()
            if session_app_id != app_id:
                continue

            tier = metadata.get('tier')
            info = None
            if not tier:
                items = stripe.checkout.Session.list_line_items(session['id'], limit=20)
                for item in items.get('data', []):
                    pid = (item.get('price') or {}).get('id')
                    if pid in price_to_tier:
                        tier, info = price_to_tier[pid]
                        break
            elif tier in app_prices:
                raw = app_prices[tier]
                info = raw if isinstance(raw, dict) else {}

            if not tier:
                continue
            if info is None:
                raw = app_prices.get(tier)
                info = raw if isinstance(raw, dict) else {}

            sub_id = session.get('subscription')
            if sub_id:
                sub = stripe.Subscription.retrieve(sub_id)
                if (sub.get('status') or '').lower() not in valid_sub_status:
                    continue
                return _resolve_period(tier, info, sub.get('current_period_end'))

            return _resolve_period(tier, info, None)
    except Exception as exc:
        print(f'[LICENSE] Stripe lookup path 2 failed: {exc}')

    # 3) Paid invoices (helps when session metadata is sparse)
    try:
        scanned = 0
        invoices = stripe.Invoice.list(status='paid', limit=100)
        for inv in invoices.auto_paging_iter():
            scanned += 1
            if scanned > 1000:
                break

            customer_email = _norm_email(inv.get('customer_email'))
            if not customer_email and inv.get('customer'):
                cust = stripe.Customer.retrieve(inv.get('customer'))
                customer_email = _norm_email(cust.get('email'))
            if customer_email != email:
                continue

            for line in inv.get('lines', {}).get('data', []):
                pid = (line.get('price') or {}).get('id')
                if pid in price_to_tier:
                    tier, info = price_to_tier[pid]
                    return _resolve_period(tier, info, inv.get('period_end'))
    except Exception as exc:
        print(f'[LICENSE] Stripe lookup path 3 failed: {exc}')

    # 4) Direct subscription sweep (last-resort catch-all)
    try:
        scanned = 0
        subs = stripe.Subscription.list(status='all', limit=100)
        for sub in subs.auto_paging_iter():
            scanned += 1
            if scanned > 1000:
                break
            if (sub.get('status') or '').lower() not in valid_sub_status:
                continue

            tier = None
            info = None
            for item in sub.get('items', {}).get('data', []):
                pid = (item.get('price') or {}).get('id')
                if pid in price_to_tier:
                    tier, info = price_to_tier[pid]
                    break
            if not tier:
                continue

            customer_id = sub.get('customer')
            if not customer_id:
                continue
            customer = stripe.Customer.retrieve(customer_id)
            if _norm_email(customer.get('email')) != email:
                continue

            return _resolve_period(tier, info, sub.get('current_period_end'))
    except Exception as exc:
        print(f'[LICENSE] Stripe lookup path 4 failed: {exc}')

    return None


def hash_code(code):
    payload = f"{code}:{LICENSE_SECRET}".encode('utf-8')
    return hashlib.sha256(payload).hexdigest()


def generate_license_key():
    return f"LIC-{secrets.token_hex(8).upper()}"


def load_price_map():
    if not os.path.exists(PRICE_MAP_PATH):
        return {}
    with open(PRICE_MAP_PATH, 'r') as handle:
        return json.load(handle)


def get_price_info(app_id, tier):
    price_map = load_price_map()
    app_prices = price_map.get(app_id, {})
    info = app_prices.get(tier)
    if not info:
        return None
    if isinstance(info, str):
        return {
            'priceId': info,
            'mode': 'payment',
            'billingType': 'one_time',
            'durationDays': 365,
        }
    return {
        'priceId': info.get('priceId'),
        'mode': info.get('mode', 'payment'),
        'billingType': info.get('billingType', 'monthly'),
        'durationDays': info.get('durationDays', 30),
    }


def build_redirect_urls():
    base = HUB_BASE_URL
    if not base:
        base = request.headers.get('Origin') or request.host_url.rstrip('/')
    base = base.rstrip('/')
    return (
        f"{base}/apps/success.html?session_id={{CHECKOUT_SESSION_ID}}",
        f"{base}/apps/cancel.html",
    )


def send_email_code(email, code, app_id, tier):
    subject = 'Your Alien AI Trader verification code'
    content = (
        f"Your verification code for {app_id} ({tier}) is: {code}\n\n"
        'This code expires in 15 minutes.'
    )
    if not _send_email(email, subject, content):
        raise RuntimeError('email service not configured')


def send_sms_code(phone, code, app_id, tier):
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN or not TWILIO_FROM_NUMBER:
        raise RuntimeError('sms service not configured')
    if not TwilioClient:
        raise RuntimeError('twilio library not installed')

    body = f"PAPI Central code for {app_id} ({tier}): {code}"
    client = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    client.messages.create(from_=TWILIO_FROM_NUMBER, to=phone, body=body)
