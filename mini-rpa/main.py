import asyncio
import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from regtech_rpa import RegTechRPA
from api_server import init_app
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('regtech_rpa.log'),
        logging.StreamHandler()
    ]
)

async def main():
    logger = logging.getLogger(__name__)
    logger.info("Initializing demo")
    
    # Create dummy data
    dummy_trades = pd.DataFrame([
        {
            'trade_id': i,
            'asset': f"ASSET_{np.random.choice(['AAPL', 'GOOG', 'TSLA'])}",
            'volume': np.random.randint(100, 20000),
            'price': np.random.uniform(100, 500),
            'counterparty': np.random.choice(['PartnerA', 'PartnerB', 'bad_guy']),
            'timestamp': datetime.now() - timedelta(seconds=np.random.randint(0, 120))
        } for i in range(100)
    ])
    dummy_trades.to_csv('dummy_trades.csv', index=False)
    logger.info("Created dummy CSV")
    
    conn = sqlite3.connect('demo.db')
    dummy_trades.to_sql('trades', conn, if_exists='replace', index=False)
    conn.close()
    logger.info("Created dummy DB")

    # Run RPA pipeline
    config = {'source_type': 'db', 'config': {'db_path': 'demo.db'}}
    rpa = RegTechRPA(config)
    result = await rpa.run()
    logger.info(f"Pipeline processed {len(result)} trades")

    # Start API server
    app = await init_app()
    logger.info("Starting API server on http://localhost:8080")
    web.run_app(app, port=8080)

if __name__ == '__main__':
    asyncio.run(main())