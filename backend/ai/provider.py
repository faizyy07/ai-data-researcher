from __future__ import annotations
import base64
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, TypeVar
from pydantic import BaseModel, ValidationError
import json

T = TypeVar("T", bound=BaseModel)

class AIError(Exception):
    """User-facing AI failure."""

@dataclass
class Part:
    text: str | None = None
    image_png: bytes | None = None

class LLMProvider(ABC):
    name = "base"
    on_wait: Callable[[str], None] | None = None
    sent_log: list[dict]

    @abstractmethod
    def _generate(self, system: str, parts: list[Part]) -> str: ...

    def structured(self, system: str, parts: list[Part], model: type[T], label: str = "") -> T:
        schema = json.dumps(model.model_json_schema())
        sys = f"{system}\n\nRespond with ONLY JSON matching this JSON schema:\n{schema}"
        last_err = ""
        for attempt in range(2):
            p = parts + ([Part(text=f"Your previous reply was invalid: {last_err}. Return valid JSON only.")] if last_err else [])
            raw = self._generate(sys, p)
            try:
                txt = raw.strip()
                if txt.startswith("```"):
                    txt = txt.strip("`").removeprefix("json").strip()
                return model.model_validate_json(txt)
            except (ValidationError, ValueError) as e:
                last_err = str(e)[:300]
        raise AIError("The AI returned an unusable response twice. Try again.")

def b64(png: bytes) -> str:
    return base64.b64encode(png).decode()
