from typing import Literal, Optional
from pydantic import BaseModel, Field

ChartType = Literal["line", "bar", "scatter", "histogram"]

class AnalysisStep(BaseModel):
    title: str
    question: str
    sql: str = Field(description="Single read-only DuckDB SELECT. Aggregate in SQL; never return raw huge tables.")
    chart_type: ChartType
    x: str = Field(description="Column in the SQL result for the x axis (histogram: the value column)")
    y: Optional[str] = Field(default=None, description="Numeric column for y axis (not needed for histogram)")
    series: Optional[str] = Field(default=None, description="Optional column splitting into multiple series")
    rationale: str = ""

class Plan(BaseModel):
    objective: str
    relevant_metrics: list[str] = []
    relevant_dimensions: list[str] = []
    analyses: list[AnalysisStep]

class NumberRef(BaseModel):
    label: str
    value: float

Direction = Literal["increase", "decrease", "flat", "outlier", "top", "compare", "none"]

class Finding(BaseModel):
    claim: str
    chart_ids: list[str]
    direction: Direction
    numbers: list[NumberRef] = []
    confidence: Literal["low", "medium", "high"]
    what_in_chart: str = Field(description="What visible feature of the chart shows this")

class Analysis(BaseModel):
    findings: list[Finding]
    follow_ups: list[AnalysisStep] = []
    not_enough_evidence: list[str] = []

class Report(BaseModel):
    executive_summary: str
    ranked_finding_ids: list[str]
    hypotheses: list[str] = []
    limitations: list[str] = []
