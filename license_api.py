import json
import os
import secrets
import sqlite3
import hashlib
from datetime import datetime, timedelta, timezone

import stripe
from flask import jsonify, request

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

STRIPE_SECRET_KEY = os.getenv('STRIPE_SECRET_KEY')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')
HUB_BASE_URL = os.getenv('HUB_BASE_URL')

SENDGRID_API_KEY = os.getenv('SENDGRID_API_KEY')
SENDGRID_FROM_EMAIL = os.getenv('SENDGRID_FROM_EMAIL')

TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_FROM_NUMBER = os.getenv('TWILIO_FROM_NUMBER')


def register_license_routes(app):
    init_db()

    @app.route('/api/license/start', methods=['POST'])
    def start_verification():
        payload = request.json or {}
        email = (payload.get('email') or '').strip()
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
        email = (payload.get('email') or '').strip()
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

    @app.route('/api/license/status', methods=['POST'])
    def license_status():
        payload = request.json or {}
        email = (payload.get('email') or '').strip()
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


def get_license(email, app_id):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM licenses WHERE email = ? AND app_id = ? ORDER BY id DESC LIMIT 1",
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
        'billing_type': row['billing_type'],
    }


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
    if not SENDGRID_API_KEY or not SENDGRID_FROM_EMAIL:
        raise RuntimeError('email service not configured')
    if not SendGridAPIClient or not Mail:
        raise RuntimeError('sendgrid library not installed')

    subject = 'Your PAPI Central verification code'
    content = (
        f"Your verification code for {app_id} ({tier}) is: {code}\n\n"
        'This code expires in 15 minutes.'
    )
    message = Mail(
        from_email=SENDGRID_FROM_EMAIL,
        to_emails=email,
        subject=subject,
        plain_text_content=content,
    )
    client = SendGridAPIClient(SENDGRID_API_KEY)
    client.send(message)


def send_sms_code(phone, code, app_id, tier):
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN or not TWILIO_FROM_NUMBER:
        raise RuntimeError('sms service not configured')
    if not TwilioClient:
        raise RuntimeError('twilio library not installed')

    body = f"PAPI Central code for {app_id} ({tier}): {code}"
    client = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    client.messages.create(from_=TWILIO_FROM_NUMBER, to=phone, body=body)
