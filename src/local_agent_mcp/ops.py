"""Ops Floor contract v0 operations. No war-room / Jira / extra tools."""

from __future__ import annotations

import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

from local_agent_mcp import tty
from local_agent_mcp.contract import (
    AUTH_FAILED,
    HARNESSES,
    INJECT_FAILED,
    INJECT_OK,
    SESSION_DEAD,
    UNSUPPORTED_HARNESS,
    WRONG_SLOT,
    error_payload,
)
from local_agent_mcp.harness import (
    classify_log,
    discover_omp_session,
    enriched_env,
    extract_reply_text,
    extract_session_id,
    grok_model,
    launch_argv,
    resume_argv,
    which_harness,
)
from local_agent_mcp.registry import Registry, Slot

DEFAULT_TIMEOUT_S = 30.0
SPAWN_GRACE_S = 0.4
POLL_S = 0.2
BEAT_INTERVAL_S = 15.0
_BEAT_TS: dict[str, float] = {}


def default_home() -> Path:
    raw = os.environ.get("LOCAL_AGENT_MCP_HOME", "").strip()
    if raw:
        return Path(raw).expanduser()
    xdg = os.environ.get("XDG_DATA_HOME", "").strip()
    if xdg:
        return Path(xdg) / "local-agent-mcp"
    return Path.home() / ".local" / "share" / "local-agent-mcp"


def pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        waited, _ = os.waitpid(pid, os.WNOHANG)
        if waited == pid:
            return False
    except ChildProcessError:
        pass
    except OSError:
        pass
    try:
        os.kill(pid, 0)
    except (OSError, ProcessLookupError):
        return False
    return True


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _read_int(path: Path) -> int | None:
    raw = _read_text(path).strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _checkout_branch(cwd: Path, branch: str) -> str | None:
    git = cwd / ".git"
    if not git.exists():
        return f"branch {branch!r} set but cwd is not a git repo"
    proc = subprocess.run(
        ["git", "-C", str(cwd), "checkout", branch],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        return f"git checkout {branch!r} failed: {err}"
    return None


class Ops:
    def __init__(self, home: Path | None = None, env: dict[str, str] | None = None):
        self.home = Path(home) if home else default_home()
        self.registry = Registry(self.home)
        self.env = enriched_env(env)

    @classmethod
    def from_env(cls) -> Ops:
        return cls()

    def _excerpt(self, text: str | None, limit: int = 120) -> str:
        raw = (text or "").strip().replace("\n", " ")
        if len(raw) > limit:
            return raw[: limit - 3] + "..."
        return raw

    def _emit_beat(self, slot: Slot, *, kind: str = "beat") -> None:
        """Periodic/status activity line for Floor-visible interim path."""
        self.registry.emit(
            kind,
            slot.slot_id,
            harness=slot.harness,
            status=slot.status,
            excerpt=self._excerpt(slot.last_reply or slot.first_prompt),
            pid=slot.pid,
            ticket=slot.ticket,
        )

    def _refresh(self, slot: Slot) -> Slot:
        old_status = slot.status
        slot_dir = self.registry.slot_dir(slot.slot_id)
        pid = _read_int(slot_dir / "pid") or slot.pid
        slot.pid = pid
        log = _read_text(slot_dir / "stdout.log")
        if log:
            sid = extract_session_id(log, slot.harness_session_id or slot.slot_id)
            if sid:
                slot.harness_session_id = sid
            reply = extract_reply_text(log)
            if reply:
                slot.last_reply = reply
        auth = classify_log(log)
        if auth:
            slot.last_error = AUTH_FAILED
        if slot.harness in ("grok", "claude"):
            slot.harness_session_id = slot.harness_session_id or slot.slot_id
        if slot.harness == "omp" and not slot.harness_session_id:
            found = discover_omp_session(Path(slot.cwd), slot.created_at)
            if found:
                slot.harness_session_id = found
        exit_code = _read_int(slot_dir / "exit_code")
        alive = exit_code is None and pid_alive(pid)
        if not alive and exit_code is None and pid:
            # process gone without an exit record (killed / reaped): mark exited
            try:
                (slot_dir / "exit_code").write_text("-1", encoding="utf-8")
                exit_code = -1
            except OSError:
                pass
        if alive:
            slot.status = "running"
        elif auth:
            slot.status = "dead"
            slot.last_error = AUTH_FAILED
        elif exit_code == 0:
            slot.status = "idle" if slot.harness_session_id else "dead"
        elif exit_code is None:
            slot.status = (
                "starting"
                if slot.status == "starting" and not log.strip()
                else ("idle" if slot.harness_session_id else "dead")
            )
        else:
            slot.status = "idle" if slot.harness_session_id and not auth else "dead"
            if not slot.last_error:
                slot.last_error = INJECT_FAILED
        if slot.tty and slot.status == "running" and not tty.alive(slot.slot_id):
            slot.status = "idle" if slot.harness_session_id else "dead"
        if slot.status != old_status and slot.status in ("idle", "dead"):
            self.registry.emit(
                "state",
                slot.slot_id,
                harness=slot.harness,
                status=slot.status,
                last_error=slot.last_error,
                excerpt=self._excerpt(slot.last_reply or slot.first_prompt),
            )
        elif slot.status == "running":
            now = time.time()
            last = _BEAT_TS.get(slot.slot_id, 0.0)
            if now - last >= BEAT_INTERVAL_S or slot.status != old_status:
                self._emit_beat(slot, kind="beat")
                _BEAT_TS[slot.slot_id] = now
        self.registry.put(slot)
        return slot

    def list_sessions(self) -> dict:
        sessions = []
        for slot in self.registry.all():
            slot = self._refresh(slot)
            sessions.append(slot.public())
        return {"ok": True, "sessions": sessions}

    def launch_session(
        self,
        cwd: str,
        harness: str,
        first_prompt: str,
        ticket: str | None = None,
        branch: str | None = None,
    ) -> dict:
        if harness not in HARNESSES:
            self.registry.emit("launch", "", error=UNSUPPORTED_HARNESS, harness=harness)
            return error_payload(UNSUPPORTED_HARNESS, harness=harness)
        cwd_path = Path(cwd).expanduser()
        if not cwd_path.is_dir():
            return {
                "ok": False,
                "error": INJECT_FAILED,
                "message": f"cwd does not exist: {cwd}",
            }
        binary = which_harness(harness, self.env)
        if not binary:
            return error_payload(
                UNSUPPORTED_HARNESS,
                harness=harness,
                message=f"{harness} binary not found on PATH",
            )
        if branch:
            err = _checkout_branch(cwd_path, branch)
            if err:
                return {
                    "ok": False,
                    "error": INJECT_FAILED,
                    "message": err,
                    "branch": branch,
                }

        slot_id = str(uuid.uuid4())
        prompt = first_prompt
        if ticket:
            prompt = f"[ticket: {ticket}]\n{first_prompt}"
        slot_dir = self.registry.slot_dir(slot_id)
        log_path = slot_dir / "stdout.log"
        prompt_file = slot_dir / "first_prompt.txt"
        prompt_file.write_text(prompt, encoding="utf-8")
        slot = Slot(
            slot_id=slot_id,
            harness=harness,  # type: ignore[arg-type]
            cwd=str(cwd_path.resolve()),
            first_prompt=first_prompt,
            ticket=ticket,
            branch=branch,
            harness_session_id=slot_id if harness in ("grok", "claude") else None,
            status="starting",
            log_path=str(log_path),
        )
        self.registry.put(slot)
        argv = launch_argv(
            harness,
            binary,
            cwd=slot.cwd,
            slot_id=slot_id,
            prompt=prompt,
            prompt_file=prompt_file if harness == "grok" else None,
            model=grok_model(self.env) if harness == "grok" else None,
        )
        launched = self._spawn(slot, argv)
        if not launched["ok"]:
            return launched
        slot = self.registry.get(slot_id) or slot
        self.registry.emit(
            "launch",
            slot_id,
            harness=harness,
            cwd=slot.cwd,
            status=slot.status,
            excerpt=self._excerpt(first_prompt),
            ticket=ticket,
            pid=slot.pid,
        )
        return {
            "ok": True,
            "slot_id": slot_id,
            "harness": harness,
            "status": slot.status,
            "pid": slot.pid,
        }

    def _spawn(self, slot: Slot, argv: list[str], *, use_tty: bool = False) -> dict:
        slot_dir = self.registry.slot_dir(slot.slot_id)
        (slot_dir / "exit_code").unlink(missing_ok=True)
        env = dict(self.env)
        src_root = str(Path(__file__).resolve().parents[1])
        env["PYTHONPATH"] = os.pathsep.join([src_root, env.get("PYTHONPATH", "")])
        if use_tty:
            if tty.spawn(slot.slot_id, argv, cwd=slot.cwd, env=env):
                slot.tty = f"screen:{tty.session_name(slot.slot_id)}"
                slot.status = "running"
                self.registry.put(slot)
                return {"ok": True}
            return error_payload(
                INJECT_FAILED, slot_id=slot.slot_id, message="TTY spawn failed"
            )

        supervisor = [
            sys.executable,
            "-m",
            "local_agent_mcp.supervisor",
            "--slot-dir",
            str(slot_dir),
            "--cwd",
            slot.cwd,
            "--",
            *argv,
        ]
        try:
            proc = subprocess.Popen(
                supervisor,
                cwd=slot.cwd,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError as exc:
            slot.status = "dead"
            slot.last_error = INJECT_FAILED
            self.registry.put(slot)
            return error_payload(INJECT_FAILED, slot_id=slot.slot_id, message=str(exc))

        slot.pid = proc.pid
        slot.status = "running"
        self.registry.put(slot)
        deadline = time.time() + SPAWN_GRACE_S
        while time.time() < deadline:
            if proc.poll() is not None:
                break
            time.sleep(0.05)
        proc.poll()
        slot = self._refresh(slot)
        if (
            slot.last_error == AUTH_FAILED
            or slot.status == "dead"
            and classify_log(_read_text(slot_dir / "stdout.log"))
        ):
            slot.last_error = AUTH_FAILED
            slot.status = "dead"
            self.registry.put(slot)
            return error_payload(AUTH_FAILED, slot_id=slot.slot_id)
        if slot.status == "dead":
            return error_payload(
                INJECT_FAILED,
                slot_id=slot.slot_id,
                message=slot.last_error or "session failed to start",
            )
        return {"ok": True, "slot_id": slot.slot_id}

    def steer(self, slot_id: str, payload: str) -> dict:
        """One follow-up payload per call. Prefer non-interactive; TTY if CLI cannot."""
        slot = self.registry.get(slot_id)
        if slot is None:
            return error_payload(WRONG_SLOT, slot_id=slot_id)
        slot = self._refresh(slot)
        if slot.status == "dead" and not slot.harness_session_id:
            return error_payload(SESSION_DEAD, slot_id=slot_id)

        if slot.status == "running":
            if slot.tty or tty.alive(slot.slot_id):
                if tty.stuff(slot.slot_id, payload):
                    self.registry.emit("steer", slot_id, via="tty")
                    return error_payload(INJECT_OK, slot_id=slot_id, via="tty")
                return error_payload(
                    INJECT_FAILED,
                    slot_id=slot_id,
                    message="TTY attach failed",
                )
            return error_payload(
                INJECT_FAILED,
                slot_id=slot_id,
                message="session busy (no TTY); await then steer",
            )

        binary = which_harness(slot.harness, self.env)
        if not binary:
            return error_payload(
                UNSUPPORTED_HARNESS, harness=slot.harness, slot_id=slot_id
            )
        sid = slot.harness_session_id or slot.slot_id
        slot_dir = self.registry.slot_dir(slot.slot_id)
        prompt_file = slot_dir / "steer_prompt.txt"
        prompt_file.write_text(payload, encoding="utf-8")
        argv = resume_argv(
            slot.harness,
            binary,
            cwd=slot.cwd,
            harness_session_id=sid,
            prompt=payload,
            prompt_file=prompt_file if slot.harness == "grok" else None,
            model=grok_model(self.env) if slot.harness == "grok" else None,
        )
        launched = self._spawn(slot, argv)
        if not launched.get("ok"):
            err = launched.get("error")
            if err == AUTH_FAILED:
                return launched
            if (
                err == INJECT_FAILED
                and tty.alive(slot.slot_id)
                and tty.stuff(slot.slot_id, payload)
            ):
                self.registry.emit("steer", slot_id, via="tty")
                return error_payload(INJECT_OK, slot_id=slot_id, via="tty")
            return launched if err else error_payload(INJECT_FAILED, slot_id=slot_id)
        self.registry.emit("steer", slot_id, via="cli")
        return error_payload(
            INJECT_OK, slot_id=slot_id, via="cli", pid=self.registry.get(slot_id).pid
        )  # type: ignore[union-attr]

    def inject(self, slot_id: str, payload: str) -> dict:
        return self.steer(slot_id, payload)

    def read_status(self, slot_id: str) -> dict:
        slot = self.registry.get(slot_id)
        if slot is None:
            return error_payload(WRONG_SLOT, slot_id=slot_id)
        slot = self._refresh(slot)
        log = _read_text(self.registry.slot_dir(slot.slot_id) / "stdout.log")
        tail = "\n".join(log.splitlines()[-40:])
        self.registry.emit(
            "status",
            slot_id,
            harness=slot.harness,
            status=slot.status,
            excerpt=self._excerpt(slot.last_reply or slot.first_prompt),
            pid=slot.pid,
        )
        return {
            "ok": True,
            "slot_id": slot.slot_id,
            "harness": slot.harness,
            "cwd": slot.cwd,
            "ticket": slot.ticket,
            "branch": slot.branch,
            "status": slot.status,
            "pid": slot.pid,
            "harness_session_id": slot.harness_session_id,
            "last_error": slot.last_error,
            "last_reply": slot.last_reply or "",
            "log_tail": tail,
        }

    def read_census_reply(self, slot_id: str) -> dict:
        status = self.read_status(slot_id)
        if not status.get("ok"):
            return status
        slot = self.registry.get(slot_id)
        assert slot is not None
        slot = self._refresh(slot)
        reply = slot.last_reply or ""
        marker = "CENSUS_REPLY"
        if marker in reply:
            reply = reply.split(marker, 1)[-1].strip()
        return {
            "ok": True,
            "slot_id": slot_id,
            "status": slot.status,
            "census_reply": reply,
        }

    def await_done(self, slot_id: str, timeout_s: float = DEFAULT_TIMEOUT_S) -> dict:
        return self.done_when(slot_id, when="idle", timeout_s=timeout_s)

    def done_when(
        self, slot_id: str, when: str, timeout_s: float = DEFAULT_TIMEOUT_S
    ) -> dict:
        slot = self.registry.get(slot_id)
        if slot is None:
            return error_payload(WRONG_SLOT, slot_id=slot_id)
        deadline = time.time() + max(0.0, float(timeout_s))
        last: Slot | None = None
        while True:
            last = self._refresh(self.registry.get(slot_id) or slot)
            log = _read_text(self.registry.slot_dir(slot_id) / "stdout.log")
            if _matches(last, log, when):
                self.registry.emit(
                    "done",
                    slot_id,
                    when=when,
                    harness=last.harness,
                    status=last.status,
                    excerpt=self._excerpt(last.last_reply or last.first_prompt),
                    pid=last.pid,
                )
                out = {
                    "ok": True,
                    "slot_id": slot_id,
                    "status": last.status,
                    "when": when,
                    "matched": True,
                }
                if last.last_error == AUTH_FAILED:
                    out["error"] = AUTH_FAILED
                    out["ok"] = False
                return out
            if last.status == "dead":
                err = last.last_error or SESSION_DEAD
                if err == AUTH_FAILED:
                    return error_payload(AUTH_FAILED, slot_id=slot_id)
                return error_payload(SESSION_DEAD, slot_id=slot_id, status="dead")
            if time.time() >= deadline:
                return {
                    "ok": False,
                    "slot_id": slot_id,
                    "status": last.status,
                    "when": when,
                    "matched": False,
                    "error": INJECT_FAILED,
                    "message": "timeout",
                }
            time.sleep(POLL_S)


def _matches(slot: Slot, log: str, when: str) -> bool:
    if when in ("idle", "done"):
        return slot.status == "idle"
    if when == "dead":
        return slot.status == "dead"
    if when == "running":
        return slot.status == "running"
    if when and when in (slot.last_reply or ""):
        return True
    return bool(when and when in log)
