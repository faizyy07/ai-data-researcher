"""Claim verifier: a finding is accepted only if its numbers and direction match computed chart evidence."""
from __future__ import annotations
import re
from backend.charts.builder import Chart
from backend.models.schemas import Finding

def _flatten(o, out: list[float]):
    if isinstance(o, bool): return
    if isinstance(o, (int, float)): out.append(float(o))
    elif isinstance(o, dict): [_flatten(v, out) for v in o.values()]
    elif isinstance(o, (list, tuple)): [_flatten(v, out) for v in o]

def chart_numbers(c: Chart) -> list[float]:
    out: list[float] = []
    _flatten(c.stats, out); _flatten(c.table["rows"], out)
    return out

def _close(a: float, b: float) -> bool:
    return abs(abs(a) - abs(b)) <= max(0.01, 0.005 * abs(b))

def _series_stats(c: Chart) -> list[dict]:
    s = c.stats.get("series")
    return list(s.values()) if isinstance(s, dict) and s else [c.stats]

def verify_finding(f: Finding, charts: dict[str, Chart]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if not f.chart_ids:
        return False, ["No chart cited."]
    cited = []
    for cid in f.chart_ids:
        if cid not in charts: reasons.append(f"Unknown chart {cid}.")
        else: cited.append(charts[cid])
    if reasons: return False, reasons
    pool = [n for c in cited for n in chart_numbers(c)]
    for ref in f.numbers:
        if not any(_close(ref.value, n) for n in pool):
            reasons.append(f"Number {ref.value} ('{ref.label}') not found in cited chart data.")
    ss = [s for c in cited for s in _series_stats(c)]
    d = f.direction
    if d in ("increase", "decrease"):
        ok = any(s.get("trend") == d or (s.get("pct_change_first_last") or 0) * (1 if d == "increase" else -1) > 5 for s in ss)
        if not ok: reasons.append(f"Chart statistics do not show a {d}.")
    elif d == "flat":
        if not any(s.get("trend") == "flat" for s in ss): reasons.append("Chart statistics do not show a flat series.")
    elif d == "outlier":
        if not any(s.get("outliers") or s.get("outlier_count") for s in ss): reasons.append("No outliers detected in the cited chart.")
    # numbers written in the claim text itself must also be grounded
    for m in re.findall(r"-?\d[\d,]*\.?\d*", f.claim):
        try: v = float(m.replace(",", ""))
        except ValueError: continue
        if len(m.replace(",", "").replace(".", "")) >= 2 and not any(_close(v, n) for n in pool) \
                and not any(_close(v, r.value) for r in f.numbers) and not (1900 <= v <= 2100):
            reasons.append(f"Number {m} in claim text is not in the chart data.")
    return (not reasons), reasons

def summary_numbers_grounded(text: str, grounded: list[float]) -> list[str]:
    bad = []
    for m in re.findall(r"-?\d[\d,]*\.?\d*", text):
        try: v = float(m.replace(",", ""))
        except ValueError: continue
        if len(m.replace(",", "").replace(".", "")) >= 2 and not (1900 <= v <= 2100) and not any(_close(v, n) for n in grounded):
            bad.append(m)
    return bad
