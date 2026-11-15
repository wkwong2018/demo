"""Allow ``python -m market_risk``."""

from __future__ import annotations

import sys

from market_risk.cli import main

if __name__ == "__main__":
    sys.exit(main())
