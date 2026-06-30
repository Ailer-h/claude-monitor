import threading
import tkinter as tk

from claude_monitor import ClaudeMonitor
from overlay import Overlay
from tray_icon import TrayIcon


def main():
    monitor = ClaudeMonitor()

    # Start polling on a background daemon thread
    threading.Thread(target=monitor.run, daemon=True).start()

    # tkinter must live on the main thread
    root = tk.Tk()
    root.withdraw()           # hide the root window
    root.resizable(False, False)

    overlay = Overlay(root, monitor)
    tray = TrayIcon(overlay, monitor)
    tray.run()                # non-blocking via run_detached()

    def _quit():
        tray._icon.stop()
        root.destroy()

    overlay._quit_fn = _quit

    try:
        root.mainloop()
    finally:
        pass


if __name__ == "__main__":
    main()
