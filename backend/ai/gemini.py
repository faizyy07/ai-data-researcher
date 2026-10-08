from __future__ import annotations
import hashlib, logging, threading, time
import httpx
from backend.ai.provider import LLMProvider, Part, AIError, b64

log = logging.getLogger("gemini")
URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self, api_key: str, model: str, rpm: int = 8, transport: httpx.BaseTransport | None = None):
        if not api_key:
            raise AIError("No Gemini API key set. Add one in Settings.")
        self.api_key, self.model = api_key, model
        self.min_interval = 60.0 / max(rpm, 1)
        self._last = 0.0
        self._lock = threading.Lock()
        self._cache: dict[str, str] = {}
        self.sent_log: list[dict] = []   # privacy: exactly what left the machine
        self._client = httpx.Client(timeout=120, transport=transport)

    def _throttle(self):
        with self._lock:
            wait = self._last + self.min_interval - time.monotonic()
            if wait > 0:
                if self.on_wait: self.on_wait(f"Pacing requests for the free tier ({wait:.0f}s)")
                time.sleep(wait)
            self._last = time.monotonic()

    def _generate(self, system: str, parts: list[Part]) -> str:
        payload_parts = []
        for p in parts:
            if p.text is not None: payload_parts.append({"text": p.text})
            if p.image_png is not None:
                payload_parts.append({"inline_data": {"mime_type": "image/png", "data": b64(p.image_png)}})
        body = {"systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": payload_parts}],
                "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2}}
        key = hashlib.sha256((self.model + system + "".join(
            (p.text or "") + (hashlib.sha256(p.image_png).hexdigest() if p.image_png else "") for p in parts)).encode()).hexdigest()
        if key in self._cache:
            return self._cache[key]
        self.sent_log.append({"model": self.model, "chars": sum(len(p.text or "") for p in parts),
                              "images": sum(1 for p in parts if p.image_png), "t": time.time()})
        delay = 5.0
        for attempt in range(5):
            self._throttle()
            try:
                r = self._client.post(URL.format(model=self.model), json=body, headers={"x-goog-api-key": self.api_key})
            except httpx.HTTPError as e:
                raise AIError("Could not reach Gemini. Check your internet connection.") from e
            if r.status_code == 429 or r.status_code >= 500:
                if self.on_wait: self.on_wait(f"Gemini busy/rate-limited, retrying in {delay:.0f}s")
                time.sleep(delay); delay *= 2; continue
            if r.status_code in (400, 403) and "API key" in r.text:
                raise AIError("Gemini rejected the API key.")
            if r.status_code == 404:
                raise AIError(f"Model '{self.model}' not found. Pick another in Settings.")
            if r.status_code != 200:
                log.warning("gemini %s: %s", r.status_code, r.text[:300])
                raise AIError(f"Gemini returned an error ({r.status_code}).")
            try:
                text = "".join(p.get("text", "") for p in r.json()["candidates"][0]["content"]["parts"])
            except (KeyError, IndexError, ValueError) as e:
                raise AIError("Gemini returned an empty or blocked response.") from e
            self._cache[key] = text
            return text
        raise AIError("Gemini free-tier limit reached. Wait a minute and retry.")
