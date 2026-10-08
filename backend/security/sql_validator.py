"""Application-level read-only SQL validator (secondary safety layer).

Primary defence is the connection itself (external access disabled, config
locked). This validator rejects anything that is not a single SELECT/WITH
statement before it ever reaches the engine.
"""
import re

class UnsafeQueryError(ValueError):
    pass

FORBIDDEN = {
    "insert", "update", "delete", "drop", "alter", "create", "truncate", "merge",
    "grant", "revoke", "copy", "attach", "detach", "install", "load", "pragma",
    "call", "export", "import", "set", "reset", "replace", "vacuum", "checkpoint",
    "execute", "prepare", "use",
}
FORBIDDEN_FUNC = re.compile(r"\b(read_\w+|glob|parquet_scan|csv_scan|json_scan|sniff_csv|query_table)\s*\(", re.I)

def _mask(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)
    sql = re.sub(r"--[^\n]*", " ", sql)
    return re.sub(r"'(?:[^']|'')*'", "''", sql)  # string literals

def validate_readonly_sql(sql: str) -> str:
    if not sql or not sql.strip():
        raise UnsafeQueryError("Query is empty.")
    masked = _mask(sql).strip().rstrip(";").strip()
    if ";" in masked:
        raise UnsafeQueryError("Only a single statement is allowed.")
    first = re.match(r"\(*\s*([a-zA-Z]+)", masked)
    if not first or first.group(1).lower() not in {"select", "with"}:
        raise UnsafeQueryError("Only SELECT queries are allowed.")
    for word in re.findall(r"[a-zA-Z_]+", masked):
        if word.lower() in FORBIDDEN:
            raise UnsafeQueryError(f"Keyword '{word.upper()}' is not allowed in read-only mode.")
    if FORBIDDEN_FUNC.search(masked):
        raise UnsafeQueryError("File/system table functions are not allowed.")
    return sql.strip().rstrip(";")
