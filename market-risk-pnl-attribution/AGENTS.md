# market-risk-pnl-attribution

Personal interview demo. Public or synthetic data only. Not affiliated with any employer.

- Prefer a failing test over a weaker one. Do not relax an assertion, skip a case, or mark a job `continue-on-error` to turn CI green.
- `python -m pytest` and `python -m ruff check --select E4,E7,E9,F src tests` should pass.
- The dollar identities in the README are the spec. If the math changes, update the tests and the README together.
- The default path stays offline: no network, no cloud, no API key, and no employer data.
