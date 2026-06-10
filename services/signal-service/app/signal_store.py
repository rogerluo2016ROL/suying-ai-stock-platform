"""Signal history store — thread-safe, in-memory with cooldown."""

import threading, time
from datetime import datetime
from dataclasses import dataclass

@dataclass
class SignalRecord:
    code: str
    level: str
    icon: str
    score: float
    reason: str
    session: str  # pre/intra/post
    created_at: str

class SignalStore:
    def __init__(self):
        self._signals: list[SignalRecord] = []
        self._lock = threading.Lock()
        self._cooldowns: dict[str, float] = {}

    def record(self, code: str, level: str, icon: str, score: float,
               reason: str = "", session: str = "intra") -> SignalRecord | None:
        with self._lock:
            # Cooldown: same stock + same level → 10 min
            ck = f"{code}:{level}"
            now = time.time()
            if ck in self._cooldowns and now - self._cooldowns[ck] < 600:
                return None
            self._cooldowns[ck] = now

            sig = SignalRecord(code=code, level=level, icon=icon, score=score,
                               reason=reason, session=session,
                               created_at=datetime.now().isoformat())
            self._signals.insert(0, sig)
            if len(self._signals) > 500:
                self._signals = self._signals[:500]
            return sig

    def query(self, code: str = None, session: str = None, limit: int = 50) -> list[SignalRecord]:
        results = self._signals
        if code: results = [s for s in results if s.code == code]
        if session: results = [s for s in results if s.session == session]
        return results[:limit]

    def latest_for_code(self, code: str) -> SignalRecord | None:
        for s in self._signals:
            if s.code == code: return s
        return None

_store = SignalStore()
def get_store(): return _store
