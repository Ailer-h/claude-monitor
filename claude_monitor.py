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
_DASHBOARD_STATE_PATH = Path.home() / ".claude" / "dashboard_state.json"

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


def _load_dashboard_state() -> dict:
    """session_id -> epoch timestamp of the last Notification hook firing."""
    try:
        return json.loads(_DASHBOARD_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _last_message_is_question(jsonl: Path) -> bool:
    """Return True if the last assistant message in the JSONL ends with a question."""
    try:
        with jsonl.open("rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 8192))
            tail = f.read().decode("utf-8", errors="replace")
        last_line = None
        for line in reversed(tail.splitlines()):
            line = line.strip()
            if line:
                last_line = line
                break
        if not last_line:
            return False
        entry = json.loads(last_line)
        if entry.get("type") != "assistant":
            return False
        msg = entry.get("message", {})
        if msg.get("stop_reason") != "end_turn":
            return False
        for block in reversed(msg.get("content", [])):
            if block.get("type") == "text":
                return "?" in block.get("text", "")[-500:]
        return False
    except Exception:
        return False


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
    jsonl_mtime = 0.0
    if jsonl:
        try:
            jsonl_mtime = jsonl.stat().st_mtime
        except Exception:
            pass

    # The Notification hook (hooks/notify_waiting.py) records a timestamp when
    # Claude is blocked on a permission prompt or idle-waiting nudge. It wins
    # over everything else unless newer JSONL activity shows the conversation
    # has already moved on (no separate "clear" signal needed).
    # Grace of 10 s: the Notification hook fires just before the JSONL is
    # flushed, so notify_ts can be slightly older than jsonl_mtime.
    NOTIFY_GRACE = 10
    notify_ts = _load_dashboard_state().get(session_id)
    if notify_ts and notify_ts + NOTIFY_GRACE >= jsonl_mtime:
        return STATUS_WAITING

    if jsonl_mtime and time.time() - jsonl_mtime < 15:
        return STATUS_WORKING

    # Process alive, JSONL is idle — check if Claude's last message was a
    # question; if so it is waiting for the user's answer, otherwise it is done.
    if jsonl and _last_message_is_question(jsonl):
        return STATUS_WAITING

    return STATUS_DONE


# ── Claude Desktop (Cowork) detection ────────────────────────────────────────


def _known_session_ids() -> set:
    """Return session IDs from ~/.claude/sessions/*.json (CLI/VSCode sessions)."""
    result = set()
    sessions_dir = Path.home() / ".claude" / "sessions"
    if not sessions_dir.exists():
        return result
    for f in sessions_dir.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            sid = data.get("sessionId")
            if sid:
                result.add(sid)
        except Exception:
            pass
    return result


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
    Child present → check for WAITING via notification hook, else WORKING.
    No child → DONE (idle).
    """
    main_pid = _desktop_main_pid()
    if not main_pid:
        return None

    child_found = False
    for proc in psutil.process_iter(["pid", "name", "cmdline", "ppid"]):
        try:
            if proc.info["ppid"] != main_pid:
                continue
            name = (proc.info["name"] or "").lower()
            cmd  = " ".join(proc.info["cmdline"] or [])
            if "claude" in name and "--output-format" in cmd:
                child_found = True
                break
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    if not child_found:
        return STATUS_DONE

    # Cowork sessions fire the Notification hook (loads user settings) but don't
    # write a file to ~/.claude/sessions/. Find "orphan" notifications — session
    # IDs in dashboard_state.json with no matching session file — and apply the
    # same JSONL-mtime check used for CLI/VSCode sessions.
    known_ids = _known_session_ids()
    dashboard = _load_dashboard_state()
    now = time.time()
    MAX_NOTIFY_AGE = 300  # ignore notifications older than 5 minutes
    NOTIFY_GRACE = 10
    for session_id, notify_ts in dashboard.items():
        if session_id in known_ids:
            continue
        if now - notify_ts > MAX_NOTIFY_AGE:
            continue
        jsonl = _find_session_jsonl(session_id, "")
        if not jsonl:
            continue
        try:
            jsonl_mtime = jsonl.stat().st_mtime
        except Exception:
            continue
        if notify_ts + NOTIFY_GRACE >= jsonl_mtime:
            return STATUS_WAITING

    return STATUS_WORKING


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
