import csv
import json
import sqlite3
import threading
import time
from datetime import datetime
from queue import Queue
from urllib import request
from concurrent.futures import ThreadPoolExecutor

# quick hack: stream rows to avoid memory blowup
def stream_trades_from_file(file_path="trades.csv"):
    with open(file_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            yield row

# TODO: handle DB connection pooling if we scale this
def read_trades_from_db(db_path="trades.db"):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS trades (id TEXT, symbol TEXT, quantity INTEGER, price REAL, timestamp TEXT)")
    cur.execute("SELECT * FROM trades")
    for row in cur.fetchall():
        yield {
            "id": row[0], "symbol": row[1],
            "quantity": row[2], "price": row[3],
            "timestamp": row[4]
        }
    conn.close()

# TODO: handle auth headers if endpoints require tokens
class ApiFetcher:
    def __init__(self, urls):
        self.urls = urls
        self.results = {}
        self.lock = threading.Lock()

    def fetch(self, url):
        try:
            with request.urlopen(url, timeout=5) as resp:
                data = json.loads(resp.read().decode())
                with self.lock:
                    self.results[url] = data
        except Exception as e:
            with self.lock:
                self.results[url] = {"error": str(e)}

    def fetch_all(self):
        threads = []
        for url in self.urls:
            t = threading.Thread(target=self.fetch, args=(url,))
            threads.append(t)
            t.start()
        for t in threads:
            t.join()
        return self.results

# TODO: consider using a proper rule engine if this grows
def check_rules(trade, config):
    violations = []
    try:
        qty = int(trade["quantity"])
        price = float(trade["price"])
        notional = qty * price
        ts = datetime.fromisoformat(trade["timestamp"])

        # Rule 1: Position limit
        if qty > config["position_limit"]:
            violations.append(f"{trade['id']} violates POSITION_LIMIT")

        # Rule 2: Restricted symbols
        if trade["symbol"] in config["restricted_symbols"]:
            violations.append(f"{trade['id']} uses RESTRICTED_SYMBOL")

        # Rule 3: Notional threshold
        if notional > config["notional_threshold"]:
            violations.append(f"{trade['id']} exceeds NOTIONAL_THRESHOLD")

        # Rule 4: Market hours
        market_start = datetime.strptime(config["market_hours"]["start"], "%H:%M").time()
        market_end = datetime.strptime(config["market_hours"]["end"], "%H:%M").time()
        if not (market_start <= ts.time() <= market_end):
            violations.append(f"{trade['id']} is OUTSIDE_MARKET_HOURS")

    except Exception as e:
        violations.append(f"{trade.get('id', 'unknown')} has ERROR: {str(e)}")

    return violations

# TODO: support JSON export for downstream systems
def export_violations(violations, path="violations.csv", chunk_size=1000):
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["violation"])
        chunk = []
        for v in violations:
            chunk.append([v])
            if len(chunk) >= chunk_size:
                writer.writerows(chunk)
                chunk = []
        if chunk:
            writer.writerows(chunk)

# TODO: log job duration for performance tracking
def process_job(source, config):
    if source == "file":
        trades = stream_trades_from_file()
    elif source == "db":
        trades = read_trades_from_db()
    elif source == "api":
        fetcher = ApiFetcher(config["api_endpoints"])
        api_data = fetcher.fetch_all()
        trades = (t for url in config["api_endpoints"] for t in api_data.get(url, []) if isinstance(t, dict))
    else:
        trades = []

    violations = []
    for trade in trades:
        violations.extend(check_rules(trade, config))

    export_violations(violations)
    print(f"Processed {len(violations)} violations")

# TODO: add cron integration or argparse for CLI control
def main():
    with open("config.json") as f:
        config = json.load(f)

    # Simulate job queue with max 10 inflight jobs
    job_queue = Queue(maxsize=10)

    def worker():
        while True:
            try:
                job = job_queue.get(timeout=1)
                process_job(job["source"], config)
                job_queue.task_done()
            except:
                pass

    threading.Thread(target=worker, daemon=True).start()

    # Submit a few demo jobs
    job_queue.put({"source": "file"})
    job_queue.put({"source": "db"})
    job_queue.put({"source": "api"})

    job_queue.join()
    print("All jobs done.")

if __name__ == "__main__":
    main()
