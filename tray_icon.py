import threading
from PIL import Image, ImageDraw
import pystray

from claude_monitor import STATUS_DONE, STATUS_WORKING, STATUS_WAITING
from json_tools import get_dict


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))

def _load_status_colors() -> dict:
    s = get_dict("style.json")
    return {
        STATUS_DONE:    _hex_to_rgb(s.get("GREEN")),
        STATUS_WORKING: _hex_to_rgb(s.get("YELLOW")),
        STATUS_WAITING: _hex_to_rgb(s.get("RED")),
    }

_STATUS_COLORS = _load_status_colors()

def _make_icon_image(status: str) -> Image.Image:
    color = _STATUS_COLORS.get(status, _STATUS_COLORS[STATUS_DONE])
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
            pystray.MenuItem("Reload Style", self._on_reload_style),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._on_quit),
        )

        self._icon = pystray.Icon(
            name="claude_dashboard",
            icon=_make_icon_image(STATUS_DONE),
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
        self._icon.icon = _make_icon_image(self._monitor.status)

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
            if status != self._last_status:
                self._last_status = status
                self._icon.icon = _make_icon_image(status)
            time.sleep(2)
