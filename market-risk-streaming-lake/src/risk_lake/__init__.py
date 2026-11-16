"""Synthetic market-risk streaming ingest, lake landing, and limit monitor.

Personal interview demo. Not a production risk system and not investment advice.
"""

from risk_lake.events import (
    TOPIC_MARKET_FACTORS,
    TOPIC_PNL,
    TOPIC_POSITIONS,
    MarketFactorEvent,
    PnlEvent,
    PositionEvent,
)
from risk_lake.explain import TemplateExplainer, build_explainer
from risk_lake.lake import AzureDataLakeGen2Writer, LocalLakeWriter
from risk_lake.limits import build_snapshot, load_limits
from risk_lake.measures import historical_es_loss, historical_var_loss
from risk_lake.pipeline import run_demo
from risk_lake.version import __version__

__all__ = [
    "AzureDataLakeGen2Writer",
    "LocalLakeWriter",
    "MarketFactorEvent",
    "PnlEvent",
    "PositionEvent",
    "TOPIC_MARKET_FACTORS",
    "TOPIC_PNL",
    "TOPIC_POSITIONS",
    "TemplateExplainer",
    "__version__",
    "build_explainer",
    "build_snapshot",
    "historical_es_loss",
    "historical_var_loss",
    "load_limits",
    "run_demo",
]
