import pandas as pd
import bisect
import logging
from typing import List
from datetime import datetime, timedelta

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('regtech_rpa.log'),
        logging.StreamHandler()
    ]
)

class RuleProcessor:
    """Applies compliance rules to trade data using Strategy pattern."""
    def __init__(self, df: pd.DataFrame):
        self.df = df.sort_values('timestamp')  # Sort for time-based rules
        self.denied_counterparties = sorted(['bad_guy', 'sanctioned'])  # Sorted for binary search
        self.logger = logging.getLogger(__name__)

    def apply_rules(self) -> pd.DataFrame:
        """Apply all compliance rules."""
        self.logger.info("Applying compliance rules")
        try:
            self._rule_large_position()
            self._rule_volume_limit()
            self._rule_wash_trade()
            self._rule_counterparty_check()
            self.logger.info("Rules applied successfully")
            return self.df
        except Exception as e:
            self.logger.error(f"Error applying rules: {str(e)}")
            raise

    def _rule_large_position(self):
        """Flag if aggregate >5% threshold (SEC 13F-inspired)."""
        self.logger.debug("Checking large position rule")
        agg = self.df.groupby('asset')['volume'].sum()
        self.df['flag_large_position'] = self.df['asset'].map(agg > 50000)  # Vectorized

    def _rule_volume_limit(self):
        """Flag single trade >10k (position limits)."""
        self.logger.debug("Checking volume limit rule")
        self.df['flag_volume_limit'] = self.df['volume'] > 10000

    def _rule_wash_trade(self):
        """Detect buy/sell same asset <60s (SEC 10b-5)."""
        self.logger.debug("Checking wash trade rule")
        self.df['flag_wash_trade'] = False
        for i in range(1, len(self.df)):
            if (self.df.iloc[i]['asset'] == self.df.iloc[i-1]['asset'] and
                (self.df.iloc[i]['timestamp'] - self.df.iloc[i-1]['timestamp']).seconds < 60):
                self.df.at[i, 'flag_wash_trade'] = True
                self.logger.debug(f"Wash trade detected at index {i}")

    def _rule_counterparty_check(self):
        """Flag sanctioned counterparties (OFAC-like)."""
        self.logger.debug("Checking counterparty rule")
        self.df['flag_counterparty'] = self.df['counterparty'].apply(
            lambda x: bisect.bisect_left(self.denied_counterparties, x) < len(self.denied_counterparties) and
                      self.denied_counterparties[bisect.bisect_left(self.denied_counterparties, x)] == x
        )  # Binary search for efficiency