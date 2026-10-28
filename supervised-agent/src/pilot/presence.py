"""Who else has a matter open, kept in memory only.

A reviewer who loads a matter, or whose open room checks in, is noted here with the
revision they loaded. Other reviewers of the same matter see that note for
``WINDOW_SECONDS``. Nothing here is written to the store, the event log or an export,
and nothing survives a restart (docs/adr/0005-presence-in-memory.md at the repository
root). The names are simulated local roles: presence is not authentication.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

WINDOW_SECONDS = 120
PRESENCE_NOTICE = (
    "Simulated local roles that loaded this matter on this server in the last two minutes. "
    "This is not authentication, and it is not recorded."
)


@dataclass(frozen=True)
class _Seen:
    display_name: str
    role: str
    revision: int
    at: float


class PresenceBoard:
    """In-memory presence per matter. Thread-safe; the clock is injectable for tests."""

    def __init__(
        self,
        window_seconds: int = WINDOW_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.window_seconds = window_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._seen: dict[str, dict[str, _Seen]] = {}

    def _prune(self, now: float) -> None:
        """Drop every expired entry and every emptied matter. Call with the lock held."""

        for matter_id in list(self._seen):
            entries = self._seen[matter_id]
            for actor_id in [a for a, s in entries.items() if now - s.at > self.window_seconds]:
                del entries[actor_id]
            if not entries:
                del self._seen[matter_id]

    def seen(
        self, matter_id: str, actor_id: str, display_name: str, role: str, revision: int
    ) -> None:
        now = self._clock()
        with self._lock:
            self._prune(now)
            self._seen.setdefault(matter_id, {})[actor_id] = _Seen(
                display_name, role, revision, now
            )

    def others(self, matter_id: str, actor_id: str, current_revision: int) -> list[dict[str, Any]]:
        """Everyone else seen on this matter within the window, ordered by actor id."""

        now = self._clock()
        with self._lock:
            self._prune(now)
            entries = self._seen.get(matter_id, {})
            current = sorted(
                ((a, s) for a, s in entries.items() if a != actor_id), key=lambda item: item[0]
            )
        return [
            {
                "actor_id": other,
                "display_name": s.display_name,
                "role": s.role,
                "revision": s.revision,
                "seconds_ago": int(now - s.at),
                "behind": s.revision < current_revision,
            }
            for other, s in current
        ]
