"""In-memory alert store."""

import threading, time
from datetime import datetime
from dataclasses import dataclass, field

@dataclass
class Alert:
    id: str
    level: str       # urgent/important/info
    title: str
    message: str
    code: str = ""
    channel: str = "app"  # app/wecom/dingtalk/email
    read: bool = False
    created_at: str = ""

class AlertStore:
    def __init__(self):
        self._alerts: list[Alert] = []
        self._counter = 0
        self._lock = threading.Lock()
        self._cooldowns: dict[str, float] = {}

    def create(self, level: str, title: str, message: str, code: str = "",
               channel: str = "app") -> Alert:
        with self._lock:
            # Cooldown: same stock+level within 5 min → skip
            ck = f"{code}:{level}"
            now = time.time()
            if ck in self._cooldowns and now - self._cooldowns[ck] < 300:
                return None
            self._cooldowns[ck] = now

            self._counter += 1
            alert = Alert(
                id=f"ALT{self._counter:04d}", level=level, title=title,
                message=message, code=code, channel=channel,
                created_at=datetime.now().isoformat(),
            )
            self._alerts.insert(0, alert)
            if len(self._alerts) > 200:
                self._alerts = self._alerts[:200]
            return alert

    def list_all(self, limit: int = 50) -> list[Alert]:
        return self._alerts[:limit]

    def unread_count(self) -> int:
        return sum(1 for a in self._alerts if not a.read)

    def mark_read(self, alert_id: str):
        for a in self._alerts:
            if a.id == alert_id:
                a.read = True

    def mark_all_read(self):
        for a in self._alerts:
            a.read = True


_store = AlertStore()
def get_store(): return _store
