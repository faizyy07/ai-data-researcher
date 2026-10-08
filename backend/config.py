import os
from dataclasses import dataclass, field

@dataclass
class Settings:
    ai_provider: str = os.getenv("AI_PROVIDER", "gemini")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    # Free-tier model lineups change often: verify in AI Studio and override via env/UI.
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
    gemini_rpm: int = int(os.getenv("GEMINI_RPM", "8"))   # stay under free-tier RPM
    max_depth: int = int(os.getenv("MAX_INVESTIGATION_DEPTH", "2"))
    max_steps_per_round: int = 6

settings = Settings()
