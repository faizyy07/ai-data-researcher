from __future__ import annotations
import threading, time, uuid
from dataclasses import dataclass, field

@dataclass
class Run:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    dataset_id: str = ""
    question: str = ""
    status: str = "running"            # running | done | error
    events: list[dict] = field(default_factory=list)
    charts: dict = field(default_factory=dict)      # id -> Chart
    findings: list[dict] = field(default_factory=list)
    report: dict | None = None
    error: str | None = None
    _n: dict = field(default_factory=lambda: {"CHART": 0, "QUERY": 0, "INSIGHT": 0})
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def next_id(self, kind: str) -> str:
        with self._lock:
            self._n[kind] += 1
            return f"{kind}-{self._n[kind]:03d}"

    def event(self, step: str, status: str, message: str):
        with self._lock:
            self.events.append({"i": len(self.events), "t": time.time(), "step": step, "status": status, "message": message})

    def snapshot(self, since: int = 0) -> dict:
        return {"id": self.id, "status": self.status, "question": self.question, "error": self.error,
                "events": self.events[since:], "next": len(self.events),
                "charts": [c.public() for c in self.charts.values()],
                "findings": self.findings, "report": self.report}
