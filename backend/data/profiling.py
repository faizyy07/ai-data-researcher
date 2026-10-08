"""Deterministic dataset profiling + semantic role inference."""
from __future__ import annotations
import re
import polars as pl
from backend.data.ingest import LoadedTable

NAME_HINTS = [
    ("identifier", r"(^id$|_id$|^id_|\bid\b|uuid|guid|key$|code$|number$|^no$)"),
    ("date", r"(date|time|month|year|day|quarter|period|created|updated)"),
    ("revenue", r"(revenue|sales|turnover|income|amount|price|total)"),
    ("cost", r"(cost|expense|cogs|spend)"),
    ("profit", r"(profit|margin|ebit)"),
    ("quantity", r"(qty|quantity|units|count|volume|orders)"),
    ("geographic", r"(region|country|state|city|province|territory|zip|postal|area|market)"),
    ("customer", r"(customer|client|segment|account)"),
    ("product", r"(product|sku|item|category|brand)"),
]

def _hint(name: str) -> str | None:
    n = name.lower()
    for role, rx in NAME_HINTS:
        if re.search(rx, n):
            return role
    return None

def _looks_like_date_strings(s: pl.Series) -> bool:
    sample = s.drop_nulls().head(200)
    if sample.len() == 0:
        return False
    try:
        parsed = sample.str.to_datetime(strict=False, time_unit="us")
    except pl.exceptions.ComputeError:  # no inferable date format => not a date column
        return False
    return parsed.null_count() / sample.len() < 0.05

def profile_column(df: pl.DataFrame, col: str) -> dict:
    s = df[col]
    n = df.height
    nulls = s.null_count()
    uniq = s.n_unique()
    dtype = s.dtype
    p: dict = {
        "name": col, "dtype": str(dtype), "rows": n, "missing": nulls,
        "missing_pct": round(100 * nulls / n, 2) if n else 0.0,
        "unique": uniq, "cardinality_ratio": round(uniq / n, 4) if n else 0.0,
    }
    hint = _hint(col)
    kind = "other"
    if dtype == pl.Date or dtype == pl.Datetime or (dtype == pl.String and _looks_like_date_strings(s)):
        kind = "date"
    elif dtype == pl.Boolean:
        kind = "boolean"
    elif dtype.is_numeric():
        kind = "numeric"
        v = s.drop_nulls().cast(pl.Float64)
        if v.len():
            q = v.quantile
            q1, q3 = q(0.25), q(0.75)
            iqr = (q3 - q1) if q1 is not None and q3 is not None else 0
            lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
            p["stats"] = {
                "min": v.min(), "max": v.max(), "mean": v.mean(), "median": v.median(),
                "std": v.std(), "p01": q(0.01), "p05": q(0.05), "p25": q1,
                "p75": q3, "p95": q(0.95), "p99": q(0.99),
                "outliers_iqr": int(((v < lo) | (v > hi)).sum()) if iqr else 0,
            }
    elif dtype == pl.String:
        kind = "categorical" if uniq <= max(50, 0.05 * n) else "text"
        top = s.drop_nulls().value_counts(sort=True).head(5)
        p["top_values"] = [{"value": r[0], "count": r[1]} for r in top.rows()]
    p["kind"] = kind
    # Semantic role
    role = None
    if hint == "identifier" and uniq > 0.5 * max(n - nulls, 1) and kind != "date":
        role = "identifier"
    elif kind == "numeric" and hint == "identifier" and uniq == n - nulls:
        role = "identifier"
    elif kind == "date":
        role = "date"
    elif kind == "numeric":
        role = hint if hint in {"revenue", "cost", "profit", "quantity"} else "metric"
        if dtype.is_integer() and uniq <= 12 and role == "metric":
            role = "dimension"
    elif kind in {"categorical", "boolean"}:
        role = hint if hint in {"geographic", "customer", "product"} else "dimension"
    elif kind == "text":
        role = "identifier" if hint == "identifier" else "text"
    p["semantic_role"] = role
    p["is_dimension"] = role in {"dimension", "geographic", "customer", "product"}
    p["is_metric"] = role in {"metric", "revenue", "cost", "profit", "quantity"}
    return p

def _pk_candidates(df: pl.DataFrame, cols: list[dict]) -> list[str]:
    return [c["name"] for c in cols if c["missing"] == 0 and c["unique"] == df.height
            and c["kind"] in {"numeric", "categorical", "text"} and df.height > 1]

def _relationships(tables: list[LoadedTable], profiles: dict[str, list[dict]]) -> list[dict]:
    rels = []
    for a in tables:
        for b in tables:
            if a.name == b.name:
                continue
            for ca in profiles[a.name]:
                for cb in profiles[b.name]:
                    if ca["kind"] not in {"numeric", "categorical", "text"} or ca["dtype"] != cb["dtype"]:
                        continue
                    # a.ca (child) -> b.cb (parent, unique)
                    if cb["unique"] != b.df.height or cb["missing"] or ca["name"] != cb["name"] and not (
                        _hint(ca["name"]) == "identifier" and _hint(cb["name"]) == "identifier"):
                        continue
                    child = set(a.df[ca["name"]].drop_nulls().unique().to_list())
                    parent = set(b.df[cb["name"]].unique().to_list())
                    if child and len(child & parent) / len(child) >= 0.95:
                        rels.append({"from": f"{a.name}.{ca['name']}", "to": f"{b.name}.{cb['name']}",
                                     "containment": round(len(child & parent) / len(child), 4)})
    return rels

def profile_tables(tables: list[LoadedTable]) -> dict:
    out_tables, col_map = [], {}
    for t in tables:
        cols = [profile_column(t.df, c) for c in t.df.columns]
        col_map[t.name] = cols
        dups = t.df.height - t.df.n_unique()
        out_tables.append({
            "name": t.name, "sheet": t.source_sheet, "rows": t.df.height, "columns": cols,
            "duplicate_rows": dups, "primary_key_candidates": _pk_candidates(t.df, cols),
            "dimensions": [c["name"] for c in cols if c["is_dimension"]],
            "metrics": [c["name"] for c in cols if c["is_metric"]],
            "date_columns": [c["name"] for c in cols if c["kind"] == "date"],
            "identifiers": [c["name"] for c in cols if c["semantic_role"] == "identifier"],
        })
    return {"tables": out_tables, "relationships": _relationships(tables, col_map)}
