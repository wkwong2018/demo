"""Lake writers.

The path layout follows a common ADLS convention::

    bronze/market-factors/date=2026-01-05/part-000.parquet

``LocalLakeWriter`` is the default. It writes that layout on the local
filesystem, so the demo needs no cloud account.

``AzureDataLakeGen2Writer`` uploads the same relative path to an Azure Data
Lake Storage Gen2 filesystem. Construct it only when that backend is wanted.
The Azure SDK is an optional extra and is imported inside the constructor.
"""

from __future__ import annotations

import io
import os
import re
from pathlib import Path
from typing import Mapping, Protocol

import pandas as pd

from risk_lake.errors import RiskLakeError

_LAYERS = frozenset({"bronze", "silver", "gold"})
_DATASET = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_PART_KEY = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_PART_VALUE = re.compile(r"^[A-Za-z0-9._-]+$")
_FILE_NAME = re.compile(r"^[A-Za-z0-9._-]+$")


class LakeWriter(Protocol):
    """Write one table into a medallion layer."""

    def write_table(
        self,
        layer: str,
        dataset: str,
        frame: pd.DataFrame,
        *,
        partition: Mapping[str, str] | None = None,
        file_name: str = "part-000.parquet",
    ) -> str:
        """Write ``frame`` and return the path or URL."""


def relative_table_path(
    layer: str,
    dataset: str,
    partition: Mapping[str, str] | None = None,
    *,
    file_name: str = "part-000.parquet",
) -> str:
    """Return the relative ADLS-style path for one part file."""
    if layer not in _LAYERS:
        raise RiskLakeError("layer must be bronze, silver, or gold")
    if _DATASET.fullmatch(dataset) is None:
        raise RiskLakeError(f"dataset name is not allowed: {dataset}")
    if _FILE_NAME.fullmatch(file_name) is None or Path(file_name).suffix not in {".parquet", ".csv"}:
        raise RiskLakeError(f"file name is not allowed: {file_name}")
    parts = [layer, dataset]
    for key, value in (partition or {}).items():
        if _PART_KEY.fullmatch(key) is None or _PART_VALUE.fullmatch(value) is None:
            raise RiskLakeError(f"partition {key}={value} is not allowed")
        parts.append(f"{key}={value}")
    parts.append(file_name)
    return "/".join(parts)


def read_parquet_tree(root: Path) -> pd.DataFrame:
    """Read every parquet file under ``root`` into one frame."""
    files = sorted(path for path in root.rglob("*.parquet") if path.is_file())
    if not files:
        raise RiskLakeError(f"no parquet files under {root}")
    frames = [pd.read_parquet(path) for path in files]
    return pd.concat(frames, ignore_index=True)


class LocalLakeWriter:
    """Write the medallion layout under a local root directory."""

    def __init__(self, root: str | Path) -> None:
        resolved = Path(root).resolve()
        if resolved == Path("/") or resolved == Path.home():
            raise RiskLakeError("refusing to use this lake path")
        self.root = resolved

    def write_table(
        self,
        layer: str,
        dataset: str,
        frame: pd.DataFrame,
        *,
        partition: Mapping[str, str] | None = None,
        file_name: str = "part-000.parquet",
    ) -> str:
        relative = relative_table_path(layer, dataset, partition, file_name=file_name)
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix == ".parquet":
            frame.to_parquet(path, index=False, engine="pyarrow")
        elif path.suffix == ".csv":
            frame.to_csv(path, index=False)
        else:
            raise RiskLakeError(f"unsupported lake file {path.name}")
        return str(path)

    def read_dataset(self, layer: str, dataset: str) -> pd.DataFrame:
        """Read one dataset back from the local lake."""
        return read_parquet_tree(self.root / layer / dataset)


class AzureDataLakeGen2Writer:
    """Upload parquet or CSV parts to Azure Data Lake Storage Gen2.

    The default demo never constructs this class. Credentials come from the
    environment at ``from_env`` and are not written to disk by this package.

    Environment variables:

    - ``AZURE_STORAGE_FILESYSTEM``: the filesystem (container) name.
    - ``AZURE_STORAGE_CONNECTION_STRING``, or both ``AZURE_STORAGE_ACCOUNT``
      and ``AZURE_STORAGE_ACCOUNT_KEY``.

    Install the extra with ``python -m pip install -e ".[azure]"``.
    """

    def __init__(
        self,
        *,
        filesystem: str,
        account: str = "",
        account_key: str = "",
        connection_string: str = "",
    ) -> None:
        if not filesystem or "/" in filesystem:
            raise RiskLakeError("AZURE_STORAGE_FILESYSTEM must be a filesystem name")
        if not connection_string and not (account and account_key):
            raise RiskLakeError(
                "Azure Data Lake writer needs a connection string or an account and key"
            )
        self._filesystem_name = filesystem
        self._account = account or _account_from_connection_string(connection_string)
        self._account_key = account_key
        self._connection_string = connection_string
        self._service = None
        self._sdk()

    @classmethod
    def from_env(cls) -> AzureDataLakeGen2Writer:
        """Build a writer from the environment. Does not open a connection yet."""
        filesystem = os.environ.get("AZURE_STORAGE_FILESYSTEM", "").strip()
        connection = os.environ.get("AZURE_STORAGE_CONNECTION_STRING", "").strip()
        account = os.environ.get("AZURE_STORAGE_ACCOUNT", "").strip()
        key = os.environ.get("AZURE_STORAGE_ACCOUNT_KEY", "").strip()
        if not filesystem:
            raise RiskLakeError(
                "Azure Data Lake writer needs AZURE_STORAGE_FILESYSTEM. "
                "The default demo uses the local filesystem and does not read this variable."
            )
        return cls(
            filesystem=filesystem,
            account=account,
            account_key=key,
            connection_string=connection,
        )

    def write_table(
        self,
        layer: str,
        dataset: str,
        frame: pd.DataFrame,
        *,
        partition: Mapping[str, str] | None = None,
        file_name: str = "part-000.parquet",
    ) -> str:
        relative = relative_table_path(layer, dataset, partition, file_name=file_name)
        file_client = self._filesystem().get_file_client(relative)
        file_client.upload_data(_table_bytes(frame, file_name), overwrite=True)
        account = self._account or "account"
        return f"https://{account}.dfs.core.windows.net/{self._filesystem_name}/{relative}"

    def _filesystem(self):
        if self._service is None:
            service_client = self._sdk()
            if self._connection_string:
                self._service = service_client.from_connection_string(self._connection_string)
            else:
                url = f"https://{self._account}.dfs.core.windows.net"
                self._service = service_client(account_url=url, credential=self._account_key)
        return self._service.get_file_system_client(self._filesystem_name)

    @staticmethod
    def _sdk():
        try:
            from azure.storage.filedatalake import DataLakeServiceClient
        except ImportError as exc:
            raise RiskLakeError(
                'Azure Data Lake support is not installed. Run: python -m pip install -e ".[azure]"'
            ) from exc
        return DataLakeServiceClient


def _table_bytes(frame: pd.DataFrame, file_name: str) -> bytes:
    buffer = io.BytesIO()
    if file_name.endswith(".parquet"):
        frame.to_parquet(buffer, index=False, engine="pyarrow")
    elif file_name.endswith(".csv"):
        frame.to_csv(buffer, index=False)
    else:
        raise RiskLakeError(f"unsupported lake file {file_name}")
    return buffer.getvalue()


def _account_from_connection_string(raw: str) -> str:
    for part in raw.split(";"):
        if part.startswith("AccountName="):
            return part.split("=", 1)[1].strip()
    return ""
