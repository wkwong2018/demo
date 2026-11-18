"""Session P&L explain for a linear snapshot book.

Personal methodology demo. Not a production risk system and not investment advice.
"""

from pnl_attribution.book import (
    SAMPLE_SESSION,
    Book,
    FactorReturn,
    Loading,
    Position,
    load_book,
    load_sample_book,
    make_book,
)
from pnl_attribution.errors import PnlAttributionError
from pnl_attribution.explain import ExplainResult, InstrumentExplain, explain_book
from pnl_attribution.version import __version__

__all__ = [
    "Book",
    "ExplainResult",
    "FactorReturn",
    "InstrumentExplain",
    "Loading",
    "PnlAttributionError",
    "Position",
    "SAMPLE_SESSION",
    "__version__",
    "explain_book",
    "load_book",
    "load_sample_book",
    "make_book",
]
