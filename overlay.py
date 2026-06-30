import tkinter as tk
import ctypes
import os

from claude_monitor import STATUS_WORKING, STATUS_WAITING

# ── Geometry ──────────────────────────────────────────────────────────────────
OFFSET_X = 14
OFFSET_Y = 14
CW, CH   = 172, 42   # collapsed (fixed)
EW       = 400        # expanded width (fixed)
# expanded height computed dynamically from session count

ROW_H    = 26         # pixels per session row
HEADER_H = 28         # "Claude Usage" title
GAP      = 6          # spacing between sections
INFO_H   = 22         # usage % + reset text row
BAR_H    = 14         # progress bar row
PAD_BOT  = 10

def _expanded_height(n_sessions: int) -> int:
    n = max(n_sessions, 1)
    return HEADER_H + GAP + n * ROW_H + GAP + INFO_H + BAR_H + PAD_BOT

# ── Palette ───────────────────────────────────────────────────────────────────
BG        = "#1A1F2E"
BORDER    = "#2D3748"
GREEN     = "#10B981"
YELLOW    = "#F59E0B"
RED       = "#EF4444"
TEXT_PRI  = "#E2E8F0"
TEXT_DIM  = "#64748B"
BAR_BG    = "#2D3748"
FONT      = ("Segoe UI", 9)
FONT_BOLD = ("Segoe UI", 9, "bold")
FONT_SM   = ("Segoe UI", 8)

# ── Windows API ───────────────────────────────────────────────────────────────
GWL_EXSTYLE       = -20
WS_EX_LAYERED     = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW  = 0x00000080


def _get_cursor_pos() -> tuple[int, int]:
    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
    pt = POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def _status_color(status: str) -> str:
    if status == STATUS_WAITING:
        return RED
    if status == STATUS_WORKING:
        return YELLOW
    return GREEN


class Overlay(tk.Toplevel):
    def __init__(self, root, monitor):
        super().__init__(root)
        self._root     = root
        self._monitor  = monitor
        self._expanded    = False
        self._visible     = True
        self._pinned      = False
        self._hwnd        = None
        self._pin_btn     = (0, 0, 0, 0)   # x1 y1 x2 y2, updated each draw

        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.attributes("-alpha", 0.93)
        self.configure(bg=BG)

        self.canvas = tk.Canvas(self, bg=BG, highlightthickness=0, bd=0,
                                width=CW, height=CH)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<Button-1>", self._on_canvas_click)

        self._set_geometry(CW, CH)
        self._draw()

        self.after(150, self._init_hwnd)
        self.after(500, self._update_loop)
        self.after(120, self._hover_loop)

    # ── Init ─────────────────────────────────────────────────────────────────

    def _init_hwnd(self):
        try:
            title = f"__claude_dash_{os.getpid()}__"
            self.title(title)
            self.update_idletasks()
            self._hwnd = ctypes.windll.user32.FindWindowW(None, title)
            if self._hwnd:
                style = ctypes.windll.user32.GetWindowLongW(self._hwnd, GWL_EXSTYLE)
                style |= WS_EX_LAYERED | WS_EX_TOOLWINDOW
                ctypes.windll.user32.SetWindowLongW(self._hwnd, GWL_EXSTYLE, style)
                self._set_click_through(True)
        except Exception:
            pass

    def _set_click_through(self, enable: bool):
        if not self._hwnd:
            return
        try:
            style = ctypes.windll.user32.GetWindowLongW(self._hwnd, GWL_EXSTYLE)
            if enable:
                style |= WS_EX_TRANSPARENT
            else:
                style &= ~WS_EX_TRANSPARENT
            ctypes.windll.user32.SetWindowLongW(self._hwnd, GWL_EXSTYLE, style)
        except Exception:
            pass

    # ── Visibility ────────────────────────────────────────────────────────────

    def toggle_visible(self):
        self._visible = not self._visible
        if self._visible:
            self.deiconify()
            self._draw()
        else:
            self.withdraw()

    # ── Expand / collapse ─────────────────────────────────────────────────────

    def _expand(self):
        self._expanded = True
        sessions = self._monitor.sessions
        eh = _expanded_height(len(sessions))
        self._set_geometry(EW, eh)
        self._draw()

    def _collapse(self):
        self._expanded = False
        self._set_geometry(CW, CH)
        self._draw()

    def _set_geometry(self, w, h):
        self.canvas.config(width=w, height=h)
        self.geometry(f"{w}x{h}+{OFFSET_X}+{OFFSET_Y}")

    # ── Hover polling ─────────────────────────────────────────────────────────

    def _hover_loop(self):
        if self._visible:
            try:
                mx, my = _get_cursor_pos()
                wx, wy = self.winfo_x(), self.winfo_y()
                w = self.winfo_width()
                h = self.winfo_height()
                inside = wx <= mx <= wx + w and wy <= my <= wy + h

                if inside and not self._expanded:
                    self._set_click_through(False)
                    self._expand()
                elif not inside and self._expanded and not self._pinned:
                    self._collapse()
                    self._set_click_through(True)
            except Exception:
                pass
        self.after(120, self._hover_loop)

    # ── Periodic redraw ───────────────────────────────────────────────────────

    def _update_loop(self):
        if self._visible:
            # Recalculate expanded height if session count changed
            if self._expanded:
                sessions = self._monitor.sessions
                eh = _expanded_height(len(sessions))
                if self.winfo_height() != eh:
                    self._set_geometry(EW, eh)
            self._draw()
        self.after(500, self._update_loop)

    # ── Drawing ───────────────────────────────────────────────────────────────

    def _draw(self):
        c = self.canvas
        c.delete("all")
        status   = self._monitor.status
        usage    = self._monitor.usage_pct
        reset_m  = self._monitor.reset_minutes
        sessions = self._monitor.sessions

        if self._expanded:
            self._draw_expanded(c, sessions, usage, reset_m)
        else:
            self._draw_collapsed(c, status, usage)

    # ── Collapsed ─────────────────────────────────────────────────────────────

    def _draw_collapsed(self, c, status, usage):
        W, H = CW, CH
        c.create_rectangle(0, 0, W, H, fill=BG, outline=BORDER)

        dot_x, dot_y, dot_r = 16, H // 2, 6
        c.create_oval(dot_x - dot_r, dot_y - dot_r,
                      dot_x + dot_r, dot_y + dot_r,
                      fill=_status_color(status), outline="")

        bx1, bx2 = 30, W - 10
        by1, by2 = H // 2 - 4, H // 2 + 4
        c.create_rectangle(bx1, by1, bx2, by2, fill=BAR_BG, outline="")
        if usage > 0:
            fx2 = bx1 + int((bx2 - bx1) * min(usage, 1.0))
            c.create_rectangle(bx1, by1, fx2, by2,
                               fill=self._bar_color(usage), outline="")

    # ── Expanded ──────────────────────────────────────────────────────────────

    def _draw_expanded(self, c, sessions, usage, reset_m):
        W = EW
        H = _expanded_height(len(sessions))

        c.create_rectangle(0, 0, W, H, fill=BG, outline=BORDER)

        # Title
        c.create_text(13, HEADER_H // 2 + 2, text="Claude Usage",
                      anchor="w", fill=TEXT_PRI, font=FONT_BOLD)

        # Pin button (top-right of header)
        btn_label = "Unpin" if self._pinned else "Pin"
        btn_x2 = W - 8
        btn_x1 = btn_x2 - 38
        btn_y1 = 6
        btn_y2 = HEADER_H - 6
        self._pin_btn = (btn_x1, btn_y1, btn_x2, btn_y2)
        btn_color = "#3B4A6B" if self._pinned else "#2D3748"
        c.create_rectangle(btn_x1, btn_y1, btn_x2, btn_y2,
                           fill=btn_color, outline=BORDER, width=1)
        c.create_text((btn_x1 + btn_x2) // 2, (btn_y1 + btn_y2) // 2,
                      text=btn_label, fill=TEXT_PRI, font=FONT_SM)

        # Session rows
        row_y_start = HEADER_H + GAP
        if not sessions:
            c.create_text(13, row_y_start + ROW_H // 2, text="No active sessions",
                          anchor="w", fill=TEXT_DIM, font=FONT)
        else:
            for i, sess in enumerate(sessions):
                self._draw_session_row(c, row_y_start + i * ROW_H, sess)

        # Usage info
        info_y = H - PAD_BOT - BAR_H - INFO_H + INFO_H // 2
        pct_str = f"{int(usage * 100)}%"
        if reset_m >= 60:
            reset_str = f"Reset in {reset_m // 60}h {reset_m % 60:02d}m"
        elif reset_m > 0:
            reset_str = f"Reset in {reset_m}m"
        else:
            reset_str = "Resetting soon"

        c.create_text(13, info_y, text=pct_str, anchor="w",
                      fill=TEXT_PRI, font=FONT_BOLD)
        c.create_text(48, info_y, text="·", anchor="w", fill=TEXT_DIM, font=FONT)
        c.create_text(58, info_y, text=reset_str, anchor="w",
                      fill=TEXT_DIM, font=FONT_SM)

        # Progress bar
        bx1, bx2 = 13, W - 13
        by1 = H - PAD_BOT - BAR_H
        by2 = H - PAD_BOT
        c.create_rectangle(bx1, by1, bx2, by2, fill=BAR_BG, outline="")
        if usage > 0:
            fx2 = bx1 + int((bx2 - bx1) * min(usage, 1.0))
            c.create_rectangle(bx1, by1, fx2, by2,
                               fill=self._bar_color(usage), outline="")

    def _draw_session_row(self, c, y, sess):
        """Single dot (status color) + session name + status label."""
        cy = y + ROW_H // 2
        dot_r = 5
        dot_x = 18

        color = _status_color(sess.status)
        c.create_oval(dot_x - dot_r, cy - dot_r,
                      dot_x + dot_r, cy + dot_r,
                      fill=color, outline="")

        label = {"done": "Idle", "working": "Working",
                 "waiting": "Waiting for input"}.get(sess.status, sess.status)

        c.create_text(dot_x + dot_r + 7, cy,
                      text=f"{sess.name}  –  {label}",
                      anchor="w", fill=TEXT_PRI, font=FONT)

    def _on_canvas_click(self, event):
        x1, y1, x2, y2 = self._pin_btn
        if x1 <= event.x <= x2 and y1 <= event.y <= y2:
            self._pinned = not self._pinned
            if not self._pinned:
                # Check if mouse is already outside; if so, collapse now
                try:
                    mx, my = _get_cursor_pos()
                    wx, wy = self.winfo_x(), self.winfo_y()
                    w, h = self.winfo_width(), self.winfo_height()
                    if not (wx <= mx <= wx + w and wy <= my <= wy + h):
                        self._collapse()
                        self._set_click_through(True)
                        return
                except Exception:
                    pass
            self._draw()

    @staticmethod
    def _bar_color(pct: float) -> str:
        if pct < 0.60:
            return GREEN
        if pct < 0.85:
            return YELLOW
        return RED
