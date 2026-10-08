"""Turn a query result into a Chart: ECharts option (UI), PNG (LLM), table + stats (verification)."""
from __future__ import annotations
import io
from dataclasses import dataclass, field
import numpy as np, polars as pl
from backend.models.schemas import AnalysisStep

MAX_POINTS = 600

class ChartError(Exception):
    pass

@dataclass
class Chart:
    id: str
    title: str
    question: str
    step: AnalysisStep
    query_id: str
    dataset_id: str
    sql: str
    table: dict          # {"columns": [...], "rows": [[...]]}  (chart data only)
    stats: dict
    option: dict         # Apache ECharts option
    png: bytes = field(repr=False, default=b"")

    def public(self) -> dict:
        return {"id": self.id, "title": self.title, "question": self.question, "query_id": self.query_id,
                "dataset_id": self.dataset_id, "sql": self.sql, "table": self.table, "stats": self.stats,
                "option": self.option, "chart_type": self.step.chart_type}

def _py(v):
    if hasattr(v, "isoformat"): return v.isoformat()
    return v

def _ordered_stats(xs: list, ys: np.ndarray) -> dict:
    n = len(ys)
    out: dict = {"n_points": n, "first": float(ys[0]), "last": float(ys[-1]), "mean": float(ys.mean()),
                 "min": float(ys.min()), "max": float(ys.max()), "total": float(ys.sum()),
                 "x_at_max": str(xs[int(ys.argmax())]), "x_at_min": str(xs[int(ys.argmin())])}
    out["pct_change_first_last"] = float((ys[-1] - ys[0]) / abs(ys[0]) * 100) if ys[0] else None
    if n >= 3:
        t = np.arange(n); slope = float(np.polyfit(t, ys, 1)[0])
        out["slope_per_step"] = slope
        rel = abs(slope) * n / (abs(ys.mean()) or 1.0)   # total drift relative to level
        out["trend"] = "flat" if rel < 0.05 else ("increase" if slope > 0 else "decrease")
        med = np.median(ys); mad = np.median(np.abs(ys - med)) or float(ys.std()) or 1.0
        z = 0.6745 * (ys - med) / mad
        out["outliers"] = [{"x": str(xs[i]), "value": float(ys[i])} for i in np.where(np.abs(z) > 3.5)[0][:10]]
    else:
        out["trend"] = "flat"; out["outliers"] = []
    if n >= 8:  # biggest mean shift
        best, idx = 0.0, None
        for i in range(3, n - 2):
            d = abs(ys[:i].mean() - ys[i:].mean()) / (ys.std() or 1)
            if d > best: best, idx = d, i
        if idx is not None and best > 1.0:
            out["change_point"] = {"x": str(xs[idx]), "before_mean": float(ys[:idx].mean()), "after_mean": float(ys[idx:].mean())}
    return out

def compute_stats(step: AnalysisStep, df: pl.DataFrame) -> dict:
    ct = step.chart_type
    if ct == "histogram":
        v = df[step.x].drop_nulls().cast(pl.Float64).to_numpy()
        if len(v) == 0: return {"n_points": 0}
        q1, q3 = np.percentile(v, [25, 75]); iqr = q3 - q1
        return {"n_points": int(len(v)), "mean": float(v.mean()), "median": float(np.median(v)), "min": float(v.min()),
                "max": float(v.max()), "std": float(v.std()),
                "outlier_count": int(((v < q1 - 1.5 * iqr) | (v > q3 + 1.5 * iqr)).sum()) if iqr else 0}
    if ct == "scatter":
        a = df[step.x].cast(pl.Float64, strict=False).to_numpy(); b = df[step.y].cast(pl.Float64, strict=False).to_numpy()
        m = ~(np.isnan(a) | np.isnan(b))
        r = float(np.corrcoef(a[m], b[m])[0, 1]) if m.sum() > 2 and a[m].std() and b[m].std() else None
        return {"n_points": int(m.sum()), "pearson_r": r, "x_mean": float(a[m].mean()) if m.any() else None,
                "y_mean": float(b[m].mean()) if m.any() else None, "note": "correlation, not causation"}
    groups = {"all": df} if not step.series else {str(k[0]) if isinstance(k, tuple) else str(k): g
                                                  for k, g in df.group_by(step.series, maintain_order=True)}
    per = {}
    for name, g in groups.items():
        y = g[step.y].cast(pl.Float64, strict=False).drop_nulls()
        if y.len() == 0: continue
        xs = g[step.x].to_list()[: y.len()]
        if ct == "line":
            per[name] = _ordered_stats(xs, y.to_numpy())
        else:  # bar: ranking
            ys = y.to_numpy(); order = np.argsort(-ys)
            tot = float(ys.sum())
            per[name] = {"n_points": len(ys), "total": tot, "max": float(ys.max()), "min": float(ys.min()), "mean": float(ys.mean()),
                         "ranking": [{"x": str(xs[i]), "value": float(ys[i]), "share_pct": float(ys[i] / tot * 100) if tot else None}
                                     for i in order[:10]],
                         "top_share_pct": float(ys[order[0]] / tot * 100) if tot else None}
    return {"series": per, **(per["all"] if "all" in per else {})}

def _option(step: AnalysisStep, df: pl.DataFrame, title: str) -> dict:
    base = {"title": {"text": title}, "tooltip": {"trigger": "axis"}, "toolbox": {"feature": {"saveAsImage": {}, "dataZoom": {}}},
            "dataZoom": [{"type": "inside"}], "animationDuration": 400}
    ct = step.chart_type
    if ct == "histogram":
        v = df[step.x].drop_nulls().cast(pl.Float64).to_numpy()
        counts, edges = np.histogram(v, bins=min(30, max(5, int(np.sqrt(len(v))))))
        return {**base, "xAxis": {"type": "category", "data": [f"{e:.4g}" for e in edges[:-1]]}, "yAxis": {"type": "value"},
                "series": [{"type": "bar", "data": counts.tolist()}]}
    if ct == "scatter":
        pts = [[_py(a), _py(b)] for a, b in zip(df[step.x].to_list(), df[step.y].to_list())]
        return {**base, "tooltip": {"trigger": "item"}, "xAxis": {"type": "value", "name": step.x, "scale": True},
                "yAxis": {"type": "value", "name": step.y, "scale": True}, "series": [{"type": "scatter", "data": pts}]}
    kind = "line" if ct == "line" else "bar"
    xs = [str(_py(v)) for v in (df[step.x].unique(maintain_order=True).to_list())]
    series = []
    if step.series:
        for k, g in df.group_by(step.series, maintain_order=True):
            m = dict(zip([str(_py(v)) for v in g[step.x].to_list()], g[step.y].to_list()))
            series.append({"name": str(k[0]), "type": kind, "smooth": kind == "line", "showSymbol": False, "data": [m.get(x) for x in xs]})
    else:
        series.append({"type": kind, "smooth": kind == "line", "showSymbol": False, "data": df[step.y].to_list()})
    return {**base, "legend": {"show": bool(step.series)}, "xAxis": {"type": "category", "data": xs},
            "yAxis": {"type": "value", "name": step.y}, "series": series}

def render_png(step: AnalysisStep, df: pl.DataFrame, title: str) -> bytes:
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=110)
    ct = step.chart_type
    if ct == "histogram":
        ax.hist(df[step.x].drop_nulls().cast(pl.Float64).to_numpy(), bins=30, color="#4f6bed")
    elif ct == "scatter":
        ax.scatter(df[step.x].to_list(), df[step.y].to_list(), s=10, color="#4f6bed")
    else:
        groups = df.group_by(step.series, maintain_order=True) if step.series else [(("",), df)]
        multi = bool(step.series)
        for k, g in groups:
            xs = [str(_py(v)) for v in g[step.x].to_list()]
            if ct == "line": ax.plot(xs, g[step.y].to_list(), label=str(k[0]))
            else: ax.bar(xs, g[step.y].to_list(), label=str(k[0]), alpha=0.7 if multi else 1.0)
        if multi: ax.legend(fontsize=7)
        if len(df[step.x].unique()) > 12:
            ax.set_xticks(ax.get_xticks()[:: max(1, len(ax.get_xticks()) // 12)])
        plt.setp(ax.get_xticklabels(), rotation=45, ha="right", fontsize=7)
    ax.set_title(title, fontsize=10); ax.set_xlabel(step.x); ax.set_ylabel(step.y or "count"); ax.grid(alpha=0.25)
    fig.tight_layout(); buf = io.BytesIO(); fig.savefig(buf, format="png"); plt.close(fig)
    return buf.getvalue()

def build_chart(chart_id: str, step: AnalysisStep, df: pl.DataFrame, query_id: str, dataset_id: str) -> Chart:
    need = [c for c in [step.x, step.y, step.series] if c]
    missing = [c for c in need if c not in df.columns]
    if missing: raise ChartError(f"Query result is missing column(s): {', '.join(missing)}")
    if df.height == 0: raise ChartError("The query returned no rows.")
    if step.chart_type in ("line", "bar", "scatter") and not step.y: raise ChartError("A y column is required for this chart type.")
    if step.chart_type != "histogram" and df.height > MAX_POINTS:
        raise ChartError(f"Result has {df.height} rows; aggregate further in SQL (max {MAX_POINTS}).")
    if step.chart_type == "line":
        df = df.sort(step.x)
    cols = list(dict.fromkeys(need))
    small = df.select(cols)
    if step.chart_type == "histogram": small = small.head(5000)
    table = {"columns": cols, "rows": [[_py(v) for v in r] for r in small.rows()][:MAX_POINTS if step.chart_type != "histogram" else 0]}
    stats = compute_stats(step, df)
    return Chart(chart_id, step.title, step.question, step, query_id, dataset_id, step.sql, table, stats,
                 _option(step, df, step.title), render_png(step, df, step.title))
