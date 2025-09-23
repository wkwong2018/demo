import asyncio
import aiohttp
import pandas as pd
import sqlite3
import logging
from typing import Dict, Any
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('regtech_rpa.log'),
        logging.StreamHandler()
    ]
)

class InputHandler:
    """Factory for handling different input sources (API, file, DB)."""
    def __init__(self, source_type: str, config: Dict[str, Any]):
        self.source_type = source_type
        self.config = config
        self.logger = logging.getLogger(__name__)

    async def fetch_data(self) -> pd.DataFrame:
        """Fetch data based on source type."""
        self.logger.info(f"Fetching data from {self.source_type}")
        try:
            if self.source_type == 'api':
                return await self._fetch_from_api()
            elif self.source_type == 'file':
                return self._fetch_from_file()
            elif self.source_type == 'db':
                return self._fetch_from_db()
            else:
                raise ValueError("Unsupported source type")
        except Exception as e:
            self.logger.error(f"Error fetching data: {str(e)}")
            raise

    async def _fetch_from_api(self) -> pd.DataFrame:
        """Async fetch from 3-4 endpoints. Uses lock to prevent race conditions."""
        endpoints = self.config.get('endpoints', [
            'https://jsonplaceholder.typicode.com/posts/1',
            'https://jsonplaceholder.typicode.com/posts/2',
            'https://jsonplaceholder.typicode.com/posts/3',
            'https://jsonplaceholder.typicode.com/posts/4'
        ])
        self.logger.debug(f"Fetching from endpoints: {endpoints}")
        timeout = aiohttp.ClientTimeout(total=5)  # Prevent deadlock/hangs
        async with aiohttp.ClientSession(timeout=timeout) as session:
            tasks = [self._fetch_endpoint(session, url) for url in endpoints]
            results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results with lock to avoid race condition
        trades = []
        lock = asyncio.Lock()
        async with lock:
            for res in results:
                if not isinstance(res, Exception):
                    trades.append({
                        'trade_id': res.get('id', pd.np.random.randint(1000)),
                        'asset': f"ASSET_{pd.np.random.choice(['AAPL', 'GOOG', 'TSLA'])}",
                        'volume': pd.np.random.randint(100, 20000),
                        'price': pd.np.random.uniform(100, 500),
                        'counterparty': pd.np.random.choice(['PartnerA', 'PartnerB', 'bad_guy']),
                        'timestamp': pd.to_datetime(datetime.now() - timedelta(seconds=pd.np.random.randint(0, 120)))
                    })
                else:
                    self.logger.error(f"API error: {res}")
        df = pd.DataFrame(trades)
        self.logger.info(f"Fetched {len(df)} trades from API")
        return df

    async def _fetch_endpoint(self, session: aiohttp.ClientSession, url: str) -> Dict:
        """Fetch single endpoint."""
        self.logger.debug(f"Fetching from {url}")
        async with session.get(url) as response:
            return await response.json()

    def _fetch_from_file(self) -> pd.DataFrame:
        """Handle large files with chunking."""
        file_path = self.config['file_path']
        self.logger.info(f"Reading file: {file_path}")
        try:
            chunks = pd.read_csv(file_path, chunksize=10000)  # Memory efficient
            df = pd.concat(chunks)
            self.logger.info(f"Read {len(df)} trades from file")
            return df
        except Exception as e:
            self.logger.error(f"File read error: {str(e)}")
            raise

    def _fetch_from_db(self) -> pd.DataFrame:
        """SQL query for DB."""
        db_path = self.config['db_path']
        self.logger.info(f"Querying database: {db_path}")
        try:
            conn = sqlite3.connect(db_path)
            query = "SELECT * FROM trades"
            df = pd.read_sql_query(query, conn)
            conn.close()
            self.logger.info(f"Read {len(df)} trades from DB")
            return df
        except Exception as e:
            self.logger.error(f"DB query error: {str(e)}")
            raise