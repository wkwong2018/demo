"""Allow ``python -m pnl_attribution``."""

from __future__ import annotations

import sys

from pnl_attribution.cli import main

if __name__ == "__main__":
    sys.exit(main())
