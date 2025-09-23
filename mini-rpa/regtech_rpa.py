import asyncio
import pandas as pd
import logging
from typing import Dict, Any
from input_handler import InputHandler
from rule_processor import RuleProcessor
from exporter import Exporter

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('regtech_rpa.log'),
        logging.StreamHandler()
    ]
)

class RegTechRPA:
    """Orchestrates RPA pipeline for regulatory reporting."""
    def __init__(self, input_config: Dict[str, Any], output_path: str = 'output.csv'):
        self.input_handler = InputHandler(**input_config)
        self.output_path = output_path
        self.logger = logging.getLogger(__name__)

    async def run(self) -> pd.DataFrame:
        """Run the full RPA pipeline."""
        self.logger.info("Starting RPA pipeline")
        try:
            df = await self.input_handler.fetch_data()
            processor = RuleProcessor(df)
            processed_df = processor.apply_rules()
            exporter = Exporter(processed_df, self.output_path)
            exporter.export()
            self.logger.info("RPA pipeline completed")
            return processed_df
        except Exception as e:
            self.logger.error(f"Pipeline error: {str(e)}")
            raise