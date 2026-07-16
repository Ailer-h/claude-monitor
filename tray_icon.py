import threading
from PIL import Image, ImageDraw
import pystray

from claude_monitor import STATUS_DONE, STATUS_WORKING, STATUS_WAITING
from json_tools import get_dict
from overlay import (
    POS_TOP_LEFT, POS_TOP_RIGHT, POS_BOTTOM_LEFT, POS_BOTTOM_RIGHT, POS_DRAGGABLE,
)

_POSITION_LABELS = (
    ("Top Left", POS_TOP_LEFT),
    ("Top Right", POS_TOP_RIGHT),
    ("Bottom Left", POS_BOTTOM_LEFT),
    ("Bottom Right", POS_BOTTOM_RIGHT),
    ("Draggable", POS_DRAGGABLE),
)


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))

def _load_status_colors() -> dict:
    s = get_dict("style.json")
    return {
        STATUS_DONE:    _hex_to_rgb(s.get("GREEN")),
        STATUS_WORKING: _hex_to_rgb(s.get("YELLOW")),
        STATUS_WAITING: _hex_to_rgb(s.get("RED")),
        "no_sessions":  _hex_to_rgb(s.get("GREY")),
    }

_STATUS_COLORS = _load_status_colors()

def _make_icon_image(status: str, has_sessions: bool = True) -> Image.Image:
    key = status if has_sessions else "no_sessions"
    color = _STATUS_COLORS.get(key, _STATUS_COLORS[STATUS_DONE])
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    margin = 6
    d.ellipse([margin, margin, size - margin, size - margin], fill=color)
    return img


class TrayIcon:
    def __init__(self, overlay, monitor):
        self._overlay = overlay
        self._monitor = monitor
        self._last_status = None

        menu = pystray.Menu(
            pystray.MenuItem("Show / Hide", self._on_toggle, default=True),
            pystray.MenuItem("Position", self._build_position_menu()),
            pystray.MenuItem("Reload Style", self._on_reload_style),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._on_quit),
        )

        self._icon = pystray.Icon(
            name="claude_dashboard",
            icon=_make_icon_image(STATUS_DONE, has_sessions=False),
            title="Claude Dashboard",
            menu=menu,
        )

        # Refresh icon color when status changes
        threading.Thread(target=self._status_refresh_loop, daemon=True).start()

    def run(self):
        self._icon.run_detached()

    def reload_style(self):
        global _STATUS_COLORS
        _STATUS_COLORS = _load_status_colors()
        self._icon.icon = _make_icon_image(self._monitor.status, bool(self._monitor.sessions))

    def _build_position_menu(self):
        return pystray.Menu(*(
            pystray.MenuItem(
                label,
                (lambda mode: lambda icon, item: self._on_set_position(mode))(mode),
                checked=(lambda mode: lambda item: self._overlay._position_mode == mode)(mode),
                radio=True,
            )
            for label, mode in _POSITION_LABELS
        ))

    def _on_set_position(self, mode):
        self._overlay.after(0, self._overlay.set_position_mode, mode)

    def _on_toggle(self, icon, item):
        self._overlay.after(0, self._overlay.toggle_visible)

    def _on_reload_style(self, icon, item):
        self.reload_style()
        self._overlay.after(0, self._overlay.reload_style)

    def _on_quit(self, icon, item):
        icon.stop()
        self._overlay.after(0, self._overlay._root.destroy)

    def _status_refresh_loop(self):
        import time
        while True:
            status = self._monitor.status
            has_sessions = bool(self._monitor.sessions)
            key = (status, has_sessions)
            if key != self._last_status:
                self._last_status = key
                self._icon.icon = _make_icon_image(status, has_sessions)
            time.sleep(2)
