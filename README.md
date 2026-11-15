# demo

Personal collection of small, independent demos. Each folder stands alone.

- [Algo-trading](Algo-trading/) — Python scripts that screen stocks and ETFs and write a technical and fundamental summary. `main.py` runs the screener on Tuesdays and Thursdays, and runs the analyzer whenever the script starts.
- [convert_xls_to_xlsx](convert_xls_to_xlsx/) — VBScript that uses Excel to save an `.xls` workbook as `.xlsx`.
- [log_monitoring](log_monitoring/) — VBScript that polls a log directory and can stop a matching process that has run past a time limit, then writes an alert.
- [mini-RPA](mini-RPA/) — Python sketch that reads trades from a CSV, SQLite, or HTTP endpoint and flags breaches of the limits in `config.json`.
- [task-scheduler-auto-importer](task-scheduler-auto-importer/) — Windows batch file that creates a Task Scheduler folder and imports XML task definitions from the same directory.
- [market-risk-var-es](market-risk-var-es/) — One-day historical and parametric Value at Risk, Expected Shortfall, and Kupiec / Christoffersen backtests on a recorded portfolio of public ETFs. Install, run, and test instructions are in that folder's README.
- [market-risk-streaming-lake](market-risk-streaming-lake/) — Synthetic market-risk events on an in-process bus, with an optional Apache Kafka path, a bronze/silver/gold Parquet lake, book limit checks, and a template breach explanation. Install, run, and test instructions are in that folder's README.
