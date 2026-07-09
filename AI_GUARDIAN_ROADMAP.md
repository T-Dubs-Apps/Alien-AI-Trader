# AI Guardian Roadmap

This document turns the "guardian" idea into a realistic build plan for Alien AI Trader.

## Goal

Build the app in layers so it can:
- stay online and recover from common failures
- log every trade and operational event
- store searchable history for the owner and paying customers
- generate weekly and monthly intelligence reports
- learn from outcomes without changing itself unsafely

## Core Principle

The system should be intelligent about observing, reporting, and recommending, but rule-based about execution.

That means:
- AI can analyze, summarize, score, and suggest
- deterministic code controls deployment, trading permissions, and secrets
- no autonomous self-modifying production code

## Phase 1: Guardian Layer

Build a background guardian that monitors:
- app heartbeat
- engine state
- license status
- broker auth
- Render environment health
- disk space / database health
- stale session / stale engine status
- market-hours vs off-hours mode

Actions it can take safely:
- restart the trading engine thread
- switch to paper mode when live checks fail
- pause buys when the safety shield triggers
- log incidents for later review
- notify the user and preserve the failure reason

## Phase 2: Event Ledger

Store every meaningful event as an append-only record:
- buy
- sell
- hold
- stop-loss
- trailing stop
- shield trigger
- license activation
- login/logout
- configuration change
- heartbeat / restart
- API failures
- data fetch failures

Recommended fields:
- timestamp
- user_id / tenant_id
- symbol
- action
- price
- quantity
- strategy or reason
- market regime
- profit / loss
- source service
- raw metadata

## Phase 3: Searchable Trade Database

Create a searchable database for owners and paying customers.

Recommended storage options:
- PostgreSQL with full-text search for production
- SQLite for local development or single-user testing
- object storage for weekly/monthly report files

Search should support:
- plain text search
- symbol search
- date range search
- action search
- outcome search
- weekly/monthly report search

Example queries:
- "show all losing trades in June"
- "find all BUY actions for AAPL"
- "what changed in the week before the best gains?"
- "show shield triggers and why they fired"

## Phase 4: Weekly and Monthly Intelligence Jobs

### Weekly job
Run every Friday after market close.

Tasks:
- gather the week’s ledger records
- separate them into dated weekly folders
- generate a weekly report
- compare the current week with prior weeks
- highlight repeated wins, repeated losses, and unusual events
- store report text plus raw summaries

### Monthly job
Run on the last market day of the month after close.

Tasks:
- combine all weekly findings for the month
- compare the month against prior months
- identify which patterns correlated with gains
- identify which patterns correlated with losses
- rank signals and strategies by usefulness
- archive the monthly report in a month folder

## Phase 5: Learning Layer

This layer should learn from history, but only through controlled updates.

What it can learn:
- which indicators worked best in which market regime
- which holding periods were most profitable
- which exit reasons preserved gains
- which symbols were consistently weak or strong
- which times of day or market conditions produced better outcomes

What it should not do:
- rewrite its own source code
- change live risk rules without approval
- move customer money without guardrails
- update secrets or deploy settings autonomously

Safe learning outputs:
- ranked strategies
- reports
- recommended parameter changes
- alerts for suspicious behavior
- candidate watchlists

## Phase 6: Customer Search Box

Add a customer-facing search interface that returns text answers from the trader database.

Permissions:
- paying customers can query the trader database
- owners/admins can query all tenants
- non-paying users should only see their own data or limited public views

Response types:
- direct text answer
- filtered table results
- linked report file
- raw event snippets

## Phase 7: Storage Layout

Suggested structure on persistent disk or cloud storage:

- `data/events/YYYY/MM/DD/`
- `data/weekly/YYYY-WW/`
- `data/monthly/YYYY-MM/`
- `data/reports/`
- `data/index/`
- `data/customer_exports/`

Each weekly folder should contain:
- raw ledger export
- weekly summary
- anomaly notes
- strategy ranking snapshot

Each monthly folder should contain:
- consolidated weekly summaries
- monthly analysis
- promoted insights
- configuration recommendations

## Phase 8: Render Deployment Rules

For Render, the safest practice is:
- keep paper mode as the default boot state
- keep live trading off until both license and live keys are valid
- use persistent disk for long-term data
- keep a single service if the engine runs in-process
- use health checks and explicit startup diagnostics
- verify environment-variable changes with Render’s Env Vars save/deploy flow

## Implementation Order

1. Guardian layer
2. Event ledger
3. Weekly/monthly jobs
4. Searchable database
5. Customer search box
6. Learning reports
7. Controlled strategy recommendation pipeline
8. Optional AI summarization layer

## Success Criteria

The app is working well when it can:
- stay online without manual babysitting
- recover from common failures safely
- keep a complete searchable trading history
- show weekly and monthly patterns clearly
- support customer access without exposing secrets
- improve recommendations based on evidence, not guesswork

## Final Rule

If the AI cannot explain why it changed something, it should not change it.
