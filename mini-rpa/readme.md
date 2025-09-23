RegTechRPA Demo

A mini-Robotic Process Automation (RPA) system for regulatory reporting, built for QRT interview prep.

Features





Inputs: API (async, 3-4 endpoints), CSV (chunked for large files), SQLite DB.



Compliance Rules: Large position (>5%), volume limits (>10k), wash trades (<60s), sanctioned counterparties (binary search).



Output: Exports to CSV with chunking for large data.



API Server: Async server with rate limiting (max 10 concurrent), timeout (5s), input sanitization.



Logging: Audit trails to regtech_rpa.log.



Efficiency: Vectorized pandas, binary search, async I/O.

Setup





Install dependencies: pip install aiohttp pandas numpy



Save files in a directory (e.g., regtech_rpa/).



Run: python main.py

Demo





Pipeline: Processes dummy trades from DB, applies rules, exports to output.csv.



API: Test with curl -X POST http://localhost:8080/process -d '{"endpoints": []}'.



Check regtech_rpa.log for audit trail.

Notes





Simulates HKMA trade reporting (e.g., derivatives).



Mitigates risks: Race conditions (asyncio.Lock), deadlocks (timeouts).



Extensible: Add cloud (AWS S3), RPA tools (UiPath API), ML anomaly detection.