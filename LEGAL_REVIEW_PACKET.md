# Legal Review Packet (Counsel Handoff)

Purpose: Provide counsel with concise technical and operational context for classification, disclosure, and launch-risk review.

Important: This packet is not legal advice.

## 1) Product Summary
Alien AI Trader is a user-deployed automation application that connects to user-controlled broker API credentials. The application can operate in paper mode and live mode. Users set risk parameters and can toggle automation.

## 2) Key Architecture Facts

- User deployment model: each user controls their own deployment environment.
- Broker custody: funds remain at broker; app does not custody funds directly.
- Access model: dashboard password and admin controls are available.
- Mode model: paper and live modes with explicit switching.
- Controls: position/risk settings, stop logic, mode toggles.

## 3) Questions for Counsel

Regulatory classification:

- Is the product considered software tooling only, investment adviser activity, commodity trading advisory activity, broker-dealer activity, or another category?
- Which registrations, notices, or exemptions apply in target jurisdictions?

Commercial model:

- Does subscription-based access change licensing obligations?
- Are there disclosure obligations for advertised performance examples?

User communication:

- Are current risk disclosures adequate?
- What mandatory language is required for live-trading enablement?

Territorial scope:

- Which states/countries require additional controls or restrictions?

## 4) Documents to Review

- Terms of Use (draft/final)
- Privacy Policy
- Risk Disclosure
- Live Trading Consent
- Marketing pages and claims
- In-app notifications and mode-switch text

## 5) Operational Controls Checklist

- Dashboard access controls configured
- Admin token configured
- Allowed origins restricted to explicit HTTPS origins
- Audit logs retained with timestamps
- Incident response and rollback process documented
- Kill-switch tested

## 6) Claims and Marketing Review Checklist

Disallow or revise language that implies:

- guaranteed profits
- low/no risk outcomes
- certainty of execution outcomes
- personalized recommendations without licensing basis

Require explicit caveats on:

- paper-vs-live differences
- slippage and fill uncertainty
- possible losses

## 7) Suggested Deliverables from Counsel

- Written classification memo
- Jurisdictional launch matrix (allowed/restricted)
- Required disclosures and exact text
- Required onboarding and consent flow requirements
- Required policy updates before public release

## 8) Decision Gate Before Broad Launch

Do not broad-launch until:

- counsel sign-off is complete
- disclosures/consent copy is approved
- marketing language is approved
- operational safeguards and monitoring are verified

## 9) Attachments

Attach these files for review:

- COMPLIANCE_PACK.md
- RISK_DISCLOSURE.md
- LIVE_TRADING_CONSENT.md
- Current Terms/Privacy drafts (if available)
