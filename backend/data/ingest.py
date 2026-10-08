"""File ingestion. Source files are opened read-only and never modified."""
from __future__ import annotations
import hashlib, re
from dataclasses import dataclass
from pathlib import Path
import polars as pl

class IngestError(Exception):
    """User-facing ingestion failure (no stack traces leak to the UI)."""

@dataclass
class LoadedTable:
    name: str
    source_sheet: str | None
    df: pl.DataFrame

SUPPORTED = {".csv", ".tsv", ".xlsx"}

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def sanitize_name(raw: str) -> str:
    n = re.sub(r"[^0-9a-zA-Z_]+", "_", raw.strip()).strip("_").lower() or "table"
    return f"t_{n}" if n[0].isdigit() else n

def _clean_columns(df: pl.DataFrame) -> pl.DataFrame:
    seen: dict[str, int] = {}
    names = []
    for i, c in enumerate(df.columns):
        base = (c or "").strip() or f"column_{i+1}"
        seen[base] = seen.get(base, 0) + 1
        names.append(base if seen[base] == 1 else f"{base}_{seen[base]}")
    return df.rename(dict(zip(df.columns, names)))

def load_file(path: str | Path) -> list[LoadedTable]:
    p = Path(path)
    if not p.exists() or not p.is_file():
        raise IngestError(f"File not found: {p.name}")
    ext = p.suffix.lower()
    if ext == ".xls":
        raise IngestError("Legacy .xls is not supported yet. Please re-save as .xlsx or .csv.")
    if ext not in SUPPORTED:
        raise IngestError(f"Unsupported file type '{ext}'. Use CSV, TSV or XLSX.")
    if p.stat().st_size == 0:
        raise IngestError("The file is empty.")
    stem = sanitize_name(p.stem)
    tables: list[LoadedTable] = []
    try:
        if ext in {".csv", ".tsv"}:
            df = pl.read_csv(p, separator="\t" if ext == ".tsv" else ",",
                             infer_schema_length=10_000, try_parse_dates=True)
            tables.append(LoadedTable(stem, None, df))
        else:
            sheets = pl.read_excel(p, sheet_id=0, infer_schema_length=10_000)
            multi = len(sheets) > 1
            for sheet, df in sheets.items():
                name = f"{stem}_{sanitize_name(sheet)}" if multi else stem
                tables.append(LoadedTable(name, sheet, df))
    except Exception as e:  # noqa: BLE001 - converted to a friendly message
        raise IngestError(f"Could not read '{p.name}'. It may be malformed or corrupted ({type(e).__name__}).") from e
    tables = [LoadedTable(t.name, t.source_sheet, _clean_columns(t.df)) for t in tables if t.df.width > 0]
    tables = [t for t in tables if t.df.height > 0]
    if not tables:
        raise IngestError("No data rows were found in the file.")
    return tables
