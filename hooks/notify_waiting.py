"""Claude Code 'Notification' hook.

Registered globally in ~/.claude/settings.json so it fires for every
Claude Code session (permission prompts, idle-waiting nudges, etc).
Records the session as "waiting" so claude_monitor.py can show the red
status dot. Never raises or exits non-zero — a monitor failure must
never block the user's actual Claude Code session.
"""
import json
import os
import sys
import time
from pathlib import Path

STATE_PATH = Path.home() / ".claude" / "dashboard_state.json"


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return

    session_id = payload.get("session_id")
    if not session_id:
        return

    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        state = {}

    state[session_id] = time.time()

    try:
        tmp_path = STATE_PATH.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(state), encoding="utf-8")
        os.replace(tmp_path, STATE_PATH)
    except Exception:
        pass


if __name__ == "__main__":
    main()
