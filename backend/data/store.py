"""DuckDB-backed dataset store with a locked-down, read-only query path."""
from __future__ import annotations
import threading, uuid
from dataclasses import dataclass, field
from pathlib import Path
import duckdb, polars as pl
from backend.data.ingest import load_file, sha256, LoadedTable
from backend.data.profiling import profile_tables
from backend.security.sql_validator import validate_readonly_sql

MAX_ROWS = 10_000

@dataclass
class Dataset:
    id: str
    filename: str
    path: str
    sha256: str
    tables: list[LoadedTable]
    profile: dict
    con: duckdb.DuckDBPyConnection = field(repr=False)
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

class DatasetStore:
    def __init__(self) -> None:
        self._items: dict[str, Dataset] = {}

    def add(self, path: str | Path) -> Dataset:
        p = Path(path)
        tables = load_file(p)
        con = duckdb.connect(":memory:")
        for t in tables:
            con.register(t.name, t.df.to_arrow())
        con.execute("SET enable_external_access=false")  # no filesystem/network
        con.execute("SET lock_configuration=true")       # settings frozen
        ds = Dataset(uuid.uuid4().hex[:12], p.name, str(p), sha256(p), tables,
                     profile_tables(tables), con)
        self._items[ds.id] = ds
        return ds

    def get(self, dataset_id: str) -> Dataset:
        if dataset_id not in self._items:
            raise KeyError(dataset_id)
        return self._items[dataset_id]

    def list(self) -> list[Dataset]:
        return list(self._items.values())

    def run_readonly_query(self, dataset_id: str, sql: str, max_rows: int = MAX_ROWS) -> pl.DataFrame:
        ds = self.get(dataset_id)
        safe = validate_readonly_sql(sql)
        with ds.lock:
            return ds.con.execute(f"SELECT * FROM ({safe}) LIMIT {int(max_rows)}").pl()
