"""Local lake layout."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from risk_lake.errors import RiskLakeError
from risk_lake.lake import LocalLakeWriter, relative_table_path


def test_writer_uses_date_partition(tmp_path: Path) -> None:
    frame = pd.DataFrame(
        {
            "event_id": ["mf-2026-01-05-SYN-EQ-1"],
            "session_date": ["2026-01-05"],
            "value": [100.5],
        }
    )
    writer = LocalLakeWriter(tmp_path / "lake")
    written = writer.write_table(
        "bronze",
        "market-factors",
        frame,
        partition={"date": "2026-01-05"},
    )
    path = Path(written)
    assert path == tmp_path / "lake" / "bronze" / "market-factors" / "date=2026-01-05" / "part-000.parquet"
    assert path.is_file()
    loaded = writer.read_dataset("bronze", "market-factors")
    assert loaded.iloc[0]["value"] == 100.5
    assert relative_table_path("bronze", "market-factors", {"date": "2026-01-05"}) == (
        "bronze/market-factors/date=2026-01-05/part-000.parquet"
    )


def test_partition_values_cannot_escape_the_lake() -> None:
    with pytest.raises(RiskLakeError):
        relative_table_path("bronze", "market-factors", {"date": "../secret"})
    with pytest.raises(RiskLakeError):
        relative_table_path("raw", "market-factors")
