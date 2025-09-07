#!/usr/bin/env python3
"""
Main Orchestrator:
- Tue/Thu → run market-screener.py
- Daily   → run smart-algo-analyze.py using latest screener output
"""

import datetime
import subprocess
import os

def run_market_screener():
    print("📈 Running market screener...")
    subprocess.run(["python", "market-screener.py"])

def run_algo_analysis(input_csv="highlighted_candidates_market.csv"):
    if not os.path.exists(input_csv):
        print(f"⚠️ Screener output {input_csv} not found. Skipping analysis.")
        return
    print("🔍 Running smart algo analysis...")
    subprocess.run(["python", "smart-stock-analyzer.py", input_csv])

def main():
    today = datetime.datetime.today().weekday()  # Monday=0, Sunday=6
    if today in [1, 3]:  # Tuesday (1) or Thursday (3)
        run_market_screener()
    run_algo_analysis()

if __name__ == "__main__":
    main()
