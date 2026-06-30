import threading
from PIL import Image, ImageDraw
import pystray

from claude_monitor import STATUS_DONE, STATUS_WORKING, STATUS_WAITING

_STATUS_COLORS = {
    STATUS_DONE:    (16, 185, 129),   # emerald green
    STATUS_WORKING: (245, 158, 11),   # amber
    STATUS_WAITING: (239, 68, 68),    # red
}


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

    def _on_toggle(self, icon, item):
        self._overlay.after(0, self._overlay.toggle_visible)

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
