"""Allow ``python -m risk_lake``."""

from __future__ import annotations

import sys

from risk_lake.cli import main

if __name__ == "__main__":
    sys.exit(main())
