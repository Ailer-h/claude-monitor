import json
import os
import time
import threading
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

try:
    import requests as _requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

STATUS_DONE    = "done"
STATUS_WORKING = "working"
STATUS_WAITING = "waiting"

_USAGE_URL = "https://claude.ai/api/oauth/usage"
_USAGE_TTL = 30
_CREDS_PATH = Path.home() / ".claude" / ".credentials.json"

_ENTRYPOINT_NAMES = {
    "claude-vscode":    "Claude Code (VSCode)",
    "claude-coworker":  "Claude Cowork",
    "claude-desktop":   "Claude Desktop",
    "claude-cli":       "Claude CLI",
    "claude-in-chrome": "Claude in Chrome",
    "claude-in-slack":  "Claude in Slack",
    "claude-in-teams":  "Claude in Teams",
    "cli":              "Claude CLI",
}

_PRIORITY = {STATUS_WAITING: 2, STATUS_WORKING: 1, STATUS_DONE: 0}


@dataclass
class SessionInfo:
    name: str
    status: str


def _load_token() -> str | None:
    try:
        creds = json.loads(_CREDS_PATH.read_text(encoding="utf-8"))
        return creds["claudeAiOauth"]["accessToken"]
    except Exception:
        return None


def _path_to_project_dir(cwd: str) -> str:
    r = cwd
    if len(r) >= 2 and r[1] == ":":
        r = r[0].lower() + "-" + r[2:]
    return r.replace("\\", "-").replace("/", "-").replace(" ", "-")


def _find_session_jsonl(session_id: str, cwd: str) -> Path | None:
    projects_dir = Path.home() / ".claude" / "projects"
    direct = projects_dir / _path_to_project_dir(cwd) / f"{session_id}.jsonl"
    if direct.exists():
        return direct
    for jsonl in projects_dir.glob(f"*/{session_id}.jsonl"):
        return jsonl
    return None


def _session_status_from_jsonl(session: dict) -> str:
    """Determine Claude Code session state via PID liveness + JSONL mtime."""
    pid = session.get("pid")
    session_id = session.get("sessionId", "")
    cwd = session.get("cwd", "")

    alive = False
    if pid and HAS_PSUTIL:
        try:
            proc = psutil.Process(pid)
            alive = proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    if not alive:
        return STATUS_DONE

    jsonl = _find_session_jsonl(session_id, cwd)
    if not jsonl:
        return STATUS_WAITING

    try:
        age = time.time() - jsonl.stat().st_mtime
        if age < 15:
            return STATUS_WORKING
    except Exception:
        pass

    # No recent JSONL writes → idle.
    # WAITING (red) requires an explicit dashboard_state.json hook signal.
    return STATUS_DONE


# ── Claude Desktop (Cowork) detection ────────────────────────────────────────



def _desktop_main_pid() -> int | None:
    """Return the main Claude Desktop process PID, or None if not running."""
    if not HAS_PSUTIL:
        return None
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            name = (proc.info["name"] or "").lower()
            cmd  = proc.info["cmdline"] or []
            if name == "claude.exe" and len(cmd) == 1 and "windowsapps" in cmd[0].lower():
                return proc.pid
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return None


def _cowork_status() -> str | None:
    """
    Return the Cowork session status, or None if Claude Desktop is not running.

    Cowork spawns an embedded claude.exe child (with --output-format stream-json)
    for the duration of each task and terminates it when done.
    Child present → WORKING; no child → DONE (idle).
    """
    main_pid = _desktop_main_pid()
    if not main_pid:
        return None

    for proc in psutil.process_iter(["pid", "name", "cmdline", "ppid"]):
        try:
            if proc.info["ppid"] != main_pid:
                continue
            name = (proc.info["name"] or "").lower()
            cmd  = " ".join(proc.info["cmdline"] or [])
            if "claude" in name and "--output-format" in cmd:
                return STATUS_WORKING
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    return STATUS_DONE


class ClaudeMonitor:
    def __init__(self):
        self._lock          = threading.Lock()
        self._sessions: list[SessionInfo] = []
        self._usage_pct     = 0.0
        self._reset_minutes = 0
        self._last_api_call = 0.0

    # ── Public properties ─────────────────────────────────────────────────────

    @property
    def sessions(self) -> list[SessionInfo]:
        with self._lock:
            return list(self._sessions)

    @property
    def status(self) -> str:
        with self._lock:
            if not self._sessions:
                return STATUS_DONE
            return max(self._sessions, key=lambda s: _PRIORITY[s.status]).status

    @property
    def usage_pct(self) -> float:
        with self._lock:
            return self._usage_pct

    @property
    def reset_minutes(self) -> int:
        with self._lock:
            return self._reset_minutes

    # ── Background loop ───────────────────────────────────────────────────────

    def run(self):
        while True:
            try:
                self._update()
            except Exception:
                pass
            time.sleep(5)

    def _update(self):
        sessions = self._detect_all_sessions()

        now = time.time()
        if now - self._last_api_call >= _USAGE_TTL:
            usage_pct, reset_min = self._fetch_usage()
            self._last_api_call = now
        else:
            with self._lock:
                usage_pct = self._usage_pct
                reset_min = max(0, self._reset_minutes - 1)

        with self._lock:
            self._sessions      = sessions
            self._usage_pct     = usage_pct
            self._reset_minutes = reset_min

    # ── Session detection ─────────────────────────────────────────────────────

    def _detect_all_sessions(self) -> list[SessionInfo]:
        result: list[SessionInfo] = []
        own_pid = os.getpid()

        # 1. Claude Code sessions (VSCode, CLI, etc.) via ~/.claude/sessions/
        sessions_dir = Path.home() / ".claude" / "sessions"
        if sessions_dir.exists():
            for f in sessions_dir.glob("*.json"):
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    pid = data.get("pid")
                    if pid == own_pid:
                        continue
                    entrypoint = data.get("entrypoint", "")
                    raw_name   = data.get("name", entrypoint)
                    display    = _ENTRYPOINT_NAMES.get(entrypoint, raw_name)
                    status     = _session_status_from_jsonl(data)
                    result.append(SessionInfo(name=display, status=status))
                except Exception:
                    pass

        # 2. Claude Desktop / Cowork
        cowork_st = _cowork_status()
        if cowork_st is not None:
            result.append(SessionInfo(name="Claude Cowork", status=cowork_st))

        # Sort: worst status first, then alphabetically
        result.sort(key=lambda s: (-_PRIORITY[s.status], s.name))
        return result

    # ── Usage API ─────────────────────────────────────────────────────────────

    def _fetch_usage(self) -> tuple[float, int]:
        if not HAS_REQUESTS:
            return 0.0, 0
        token = _load_token()
        if not token:
            return 0.0, 0
        try:
            r = _requests.get(
                _USAGE_URL,
                headers={
                    "Authorization": f"Bearer {token}",
                    "anthropic-client-platform": "claude_cli",
                },
                timeout=8,
            )
            if r.status_code != 200:
                return 0.0, 0
            bucket = r.json().get("five_hour") or {}
            pct = min((bucket.get("utilization") or 0.0) / 100.0, 1.0)
            reset_min = self._minutes_until(bucket.get("resets_at"))
            return pct, reset_min
        except Exception:
            return 0.0, 0

    @staticmethod
    def _minutes_until(iso_str: str | None) -> int:
        if not iso_str:
            return 0
        try:
            dt    = datetime.fromisoformat(iso_str)
            delta = dt - datetime.now(timezone.utc)
            return max(0, int(delta.total_seconds() / 60))
        except Exception:
            return 0
