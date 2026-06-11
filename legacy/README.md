# Legacy Files

**worker.py** — The original standalone trading-engine process. It ran as a
separate Render Background Worker service alongside the dashboard.

In June 2026 the engine was integrated directly into `dashboard.py` (it starts
automatically inside the web process) to cut Render hosting costs by ~$7/month.

**Do not run worker.py.** Running it alongside `dashboard.py` would start a
second trading engine and place duplicate orders. It is kept here only for
reference and history.
