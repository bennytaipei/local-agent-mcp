"""On-disk slot registry. Source of truth for Floor-managed slots."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path

from local_agent_mcp.contract import Harness

SLOT_STATUSES = ("starting", "running", "idle", "dead")


@dataclass
class Slot:
    slot_id: str
    harness: Harness
    cwd: str
    first_prompt: str
    ticket: str | None = None
    branch: str | None = None
    harness_session_id: str | None = None
    pid: int | None = None
    tty: str | None = None
    status: str = "starting"
    last_error: str | None = None
    last_reply: str | None = None
    log_path: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Slot:
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})

    def public(self) -> dict:
        path = self.log_path or ""
        log_bytes = 0
        if path:
            try:
                log_bytes = Path(path).stat().st_size
            except OSError:
                log_bytes = 0
        return {
            "slot_id": self.slot_id,
            "harness": self.harness,
            "cwd": self.cwd,
            "ticket": self.ticket,
            "branch": self.branch,
            "harness_session_id": self.harness_session_id,
            "pid": self.pid,
            "tty": self.tty,
            "status": self.status,
            "last_error": self.last_error,
            "transcript_path": path,
            "log_bytes": log_bytes,
        }


class Registry:
    def __init__(self, home: Path):
        self.home = Path(home)
        self.home.mkdir(parents=True, exist_ok=True)
        self.path = self.home / "slots.json"
        self.lock_path = self.home / "slots.lock"
        self.events_path = self.home / "events.jsonl"
        (self.home / "slots").mkdir(parents=True, exist_ok=True)

    def slot_dir(self, slot_id: str) -> Path:
        d = self.home / "slots" / slot_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    @contextmanager
    def _lock(self) -> Iterator[None]:
        self.lock_path.touch(exist_ok=True)
        fd = os.open(self.lock_path, os.O_RDWR)
        try:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def _read(self) -> dict[str, Slot]:
        if not self.path.exists():
            return {}
        raw = json.loads(self.path.read_text(encoding="utf-8") or "{}")
        return {k: Slot.from_dict(v) for k, v in raw.items()}

    def _write(self, slots: dict[str, Slot]) -> None:
        payload = {k: v.to_dict() for k, v in slots.items()}
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self.path)

    def all(self) -> list[Slot]:
        with self._lock():
            return list(self._read().values())

    def get(self, slot_id: str) -> Slot | None:
        with self._lock():
            return self._read().get(slot_id)

    def put(self, slot: Slot) -> Slot:
        slot.updated_at = time.time()
        with self._lock():
            slots = self._read()
            slots[slot.slot_id] = slot
            self._write(slots)
        return slot

    def emit(self, kind: str, slot_id: str, **fields: object) -> None:
        """Heartbeat log for Floor/Dock activity (interim). Not an MCP tool.

        Common fields (callers should pass when known): harness, status, excerpt.
        Kinds: launch | status | beat | steer | done | state | error.
        """
        rec = {"ts": time.time(), "kind": kind, "slot_id": slot_id or "", **fields}
        # keep excerpt short for chat sitreps
        if "excerpt" in rec and isinstance(rec["excerpt"], str) and len(rec["excerpt"]) > 160:
            rec["excerpt"] = rec["excerpt"][:157] + "..."
        self.events_path.parent.mkdir(parents=True, exist_ok=True)
        with self.events_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, default=str) + "\n")
