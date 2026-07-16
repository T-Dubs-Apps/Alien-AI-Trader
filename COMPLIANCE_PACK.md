# Alien AI Trader - Compliance Pack (Operational Draft)

Important: This pack is an operational drafting aid, not legal advice. Use this as a working package for counsel review before public launch.

## 1) Plain-English Risk Disclosure (In-App + Website)
Use this text anywhere users enable automation or view performance.

Suggested copy:

Alien AI Trader is software that helps automate trading logic based on user-selected settings. It does not guarantee profits, avoid losses, or predict market outcomes with certainty.

Trading securities involves substantial risk, including the risk of losing some or all invested capital. Market conditions, liquidity, slippage, spreads, outages, broker constraints, and data quality can affect outcomes.

Past performance, backtests, simulations, and paper-trading results are not guarantees of future performance. Live trading can behave materially differently than paper trading.

You are responsible for your account configuration, risk settings, and all trade decisions executed through your broker account.

## 2) Live Trading Consent Text (Required Before Enabling Live)
Use this as a mandatory acknowledgement modal with checkbox + timestamp.

Suggested copy:

Live Trading Consent

By enabling Live Trading, you acknowledge and agree that:

1. Real money is at risk, and losses can occur quickly.
2. You are solely responsible for all orders sent to your broker account.
3. You understand live trading may differ from paper trading due to fills, slippage, spreads, volatility, and market structure.
4. You have reviewed and set your risk controls (position sizing, stop-loss, max positions, and automation toggles).
5. You understand this software is a tool and does not provide personalized investment advice.

Checkbox label:
I understand and accept the risks of live trading with real funds.

Recommended UX controls:

- Require re-confirmation when switching Paper -> Live.
- Display a visible Live badge across the interface.
- Log timestamp, account mode, and user acknowledgement event in audit log.

## 3) Terms and Policy Checklist for Counsel
Bring this list to a securities/commodities attorney.

Business model and classification:

- Is this software-only tooling, investment adviser activity, signal service, CTA/CPO, or broker-dealer-adjacent activity?
- Which registrations/exemptions may apply in each target jurisdiction?
- Is subscription pricing structure creating additional regulatory obligations?

Product statements and marketing:

- Review all claims for implied guarantees or misleading performance impressions.
- Validate acceptable language for testimonials, examples, and hypothetical results.
- Confirm required legends/disclosures for website, onboarding, and in-app banners.

User control and custody boundaries:

- Confirm non-custodial posture is legally and operationally accurate.
- Confirm no discretionary control is exercised by operator over user funds.
- Confirm secret/key handling and isolation support stated legal position.

Contracts and legal docs:

- Terms of Use
- Risk Disclosure
- Privacy Policy
- Data Processing/Retention disclosures
- Arbitration/venue/limitation clauses (if desired)

Operational controls for defensibility:

- Audit logging standard and retention period
- Incident response and outage communications
- Kill-switch procedures
- Support boundaries (what support can and cannot do)

## 4) Marketing Do and Do-Not List (Reusable Across Apps)

Do:

- Say it is a user-controlled software tool.
- Emphasize risk controls and user responsibility.
- Distinguish paper results from live outcomes.
- Use clear non-advisory language.

Do not:

- Promise income or certainty.
- Use language like guaranteed, risk-free, always wins, never loses.
- Imply personalized investment advice without proper licensing.
- Present hypothetical/paper performance as expected live results.

## 5) Deployment Hardening Checklist (Reg + Security Hygiene)
Before each production launch:

- DASHBOARD_PASSWORD set
- ADMIN_API_TOKEN set
- ALLOWED_ORIGINS set to exact HTTPS origins (no wildcard)
- LICENSE_SECRET set strong and unique
- Live keys only where required
- Public routes reviewed
- Admin routes token/session protected
- Audit logs enabled
- Health endpoint and uptime monitor configured

## 6) Suggested In-App Compliance Surfaces
Where to place required messaging:

- Login page footer: high-level risk warning
- Mode switch modal: mandatory Live Trading consent
- Settings panel: plain-language risk reminder
- Notifications panel: link to full risk disclosure
- Footer/legal menu: Terms, Privacy, Risk Disclosure

## 7) Recordkeeping Recommendations
Maintain this evidence set for each release:

- Version + commit hash
- Release date/time
- Risk disclosure version shown to user
- Consent event logs (mode switch acknowledgements)
- Incident timeline if outages occurred

## 8) Quick Decision Framework (Go/No-Go)
Use before opening to public users:

Go only if:

- Counsel reviewed and approved disclosures and terms
- Licensing/registration path is clear for target users/regions
- Monitoring, logging, and kill-switch are tested
- Support response plan exists

No-Go if:

- Counsel unresolved on classification/registration
- Marketing still contains return guarantees or implied certainty
- Access controls or origin restrictions are misconfigured

## 9) Copy/Paste Short Risk Banner
Use this compact warning in top navigation when Live mode is active:

Live mode uses real funds. Losses can exceed expectations. Review risk settings before trading.

## 10) Next Action Plan (1 Week)

Day 1:

- Add Terms, Privacy, Risk Disclosure pages.
- Add Live consent modal + audit event logging.

Day 2-3:

- Counsel review package with this file, architecture notes, and user flows.

Day 4:

- Update copy based on counsel feedback.

Day 5:

- Run final compliance + security checklist.
- Freeze copy for release.
