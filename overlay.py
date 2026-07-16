import tkinter as tk
import ctypes
import os

from claude_monitor import STATUS_WORKING, STATUS_WAITING
from json_tools import get_dict, save_dict

# ── Geometry ──────────────────────────────────────────────────────────────────
OFFSET_X = 14
OFFSET_Y = 14
CW, CH   = 172, 42   # collapsed (fixed)
EW       = 400        # expanded width (fixed)
# expanded height computed dynamically from session count

# ── Position ──────────────────────────────────────────────────────────────────
POS_TOP_LEFT     = "top-left"
POS_TOP_RIGHT    = "top-right"
POS_BOTTOM_LEFT  = "bottom-left"
POS_BOTTOM_RIGHT = "bottom-right"
POS_DRAGGABLE    = "draggable"

HANDLE_SIZE   = 10  # grip box side length
HANDLE_MARGIN = 3   # gap from the top/right window edges

_CONFIG_PATH = "config.json"


def _load_position_config() -> tuple[str, int | None, int | None]:
    cfg = get_dict(_CONFIG_PATH)
    mode = cfg.get("POSITION_MODE", POS_TOP_LEFT)
    return mode, cfg.get("POS_X"), cfg.get("POS_Y")


def _save_position_config(mode: str, x: int | None, y: int | None) -> None:
    save_dict(_CONFIG_PATH, {"POSITION_MODE": mode, "POS_X": x, "POS_Y": y})

ROW_H         = 26    # pixels per session row
HEADER_H      = 28    # "Claude Usage" title
GAP           = 6     # spacing between sections
INFO_H        = 22    # usage % + reset text row
BAR_H         = 14    # progress bar row
SESSION_GAP   = 4     # vertical gap between the main bar and the session bar
SESSION_BAR_H = 2      # session-window progress bar row
PAD_BOT       = 10

SESSION_WINDOW_MIN = 5 * 60  # 5h session window, in minutes

# ── Mascot (Clawd) ───────────────────────────────────────────────────────────
# Pixel-grid rectangles lifted from the official Claude Code "clawd" mark
# (VS Code extension resources/clawd.svg), native viewBox 47x38.
CLAWD_W, CLAWD_H = 47, 38
CLAWD_RECTS = [
    (5.082, 0.938, 9.374, 10.077), (9.233, 0.938, 13.525, 10.077),
    (13.384, 0.938, 17.677, 10.077), (17.535, 0.938, 21.828, 10.077),
    (21.686, 0.938, 25.979, 10.077), (25.838, 0.938, 30.13, 10.077),
    (29.989, 0.938, 34.281, 10.077), (34.14, 0.938, 38.432, 10.077),
    (38.291, 0.938, 42.583, 10.077),
    (0.931, 9.938, 5.223, 19.077), (5.082, 9.938, 9.374, 19.077),
    (9.233, 14.508, 13.525, 19.077), (13.384, 9.938, 17.677, 19.077),
    (17.535, 9.938, 21.828, 19.077), (21.686, 9.938, 25.979, 19.077),
    (25.838, 9.938, 30.13, 19.077), (29.989, 9.938, 34.281, 19.077),
    (34.14, 14.508, 38.432, 19.077), (38.291, 9.938, 42.583, 19.077),
    (42.442, 9.938, 46.734, 19.077),
    (5.082, 18.939, 9.374, 28.077), (9.233, 18.939, 13.525, 28.077),
    (13.384, 18.939, 17.677, 28.077), (17.535, 18.939, 21.828, 28.077),
    (21.686, 18.939, 25.979, 28.077), (25.838, 18.939, 30.13, 28.077),
    (29.989, 18.939, 34.281, 28.077), (34.14, 18.939, 38.432, 28.077),
    (38.291, 18.939, 42.583, 28.077),
    (5.082, 27.939, 9.374, 37.077), (13.384, 27.939, 17.677, 37.077),
    (29.989, 27.939, 34.281, 37.077), (38.291, 27.939, 42.583, 37.077),
]

def _expanded_height(n_sessions: int) -> int:
    n = max(n_sessions, 1)
    return (HEADER_H + GAP + n * ROW_H + GAP + INFO_H + BAR_H
            + SESSION_GAP + SESSION_BAR_H + PAD_BOT)

# ── Palette ───────────────────────────────────────────────────────────────────

stylesheet = get_dict("style.json")

BG           = stylesheet.get("BG")
BORDER       = stylesheet.get("BORDER")
GREEN        = stylesheet.get("GREEN")
YELLOW       = stylesheet.get("YELLOW")
RED          = stylesheet.get("RED")
GREY         = stylesheet.get("GREY")
TEXT_PRI     = stylesheet.get("TEXT_PRI")
TEXT_DIM     = stylesheet.get("TEXT_DIM")
BAR_BG       = stylesheet.get("BAR_BG")
SESSION_BAR  = stylesheet.get("SESSION_BAR")
FONT         = (stylesheet.get("FONT").get("font-face"), stylesheet.get("FONT").get("font-size"))
FONT_BOLD    = (stylesheet.get("FONT_BOLD").get("font-face"), stylesheet.get("FONT_BOLD").get("font-size"), "bold")
FONT_SM      = (stylesheet.get("FONT_SM").get("font-face"), stylesheet.get("FONT_SM").get("font-size"))
ALPHA_IDLE   = stylesheet.get("ALPHA_IDLE")
ALPHA_ACTIVE = stylesheet.get("ALPHA_ACTIVE")

# ── Windows API ───────────────────────────────────────────────────────────────
GWL_EXSTYLE       = -20
WS_EX_LAYERED     = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW  = 0x00000080


def reload_stylesheet() -> None:
    global BG, BORDER, GREEN, YELLOW, RED, GREY, TEXT_PRI, TEXT_DIM, BAR_BG, SESSION_BAR
    global FONT, FONT_BOLD, FONT_SM, ALPHA_IDLE, ALPHA_ACTIVE
    s = get_dict("style.json")
    BG           = s.get("BG")
    BORDER       = s.get("BORDER")
    GREEN        = s.get("GREEN")
    YELLOW       = s.get("YELLOW")
    RED          = s.get("RED")
    GREY         = s.get("GREY")
    TEXT_PRI     = s.get("TEXT_PRI")
    TEXT_DIM     = s.get("TEXT_DIM")
    BAR_BG       = s.get("BAR_BG")
    SESSION_BAR  = s.get("SESSION_BAR")
    FONT         = (s.get("FONT").get("font-face"), s.get("FONT").get("font-size"))
    FONT_BOLD    = (s.get("FONT_BOLD").get("font-face"), s.get("FONT_BOLD").get("font-size"), "bold")
    FONT_SM      = (s.get("FONT_SM").get("font-face"), s.get("FONT_SM").get("font-size"))
    ALPHA_IDLE   = s.get("ALPHA_IDLE")
    ALPHA_ACTIVE = s.get("ALPHA_ACTIVE")

def _get_cursor_pos() -> tuple[int, int]:
    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
    pt = POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def _draw_clawd(c, x0: float, y0: float, scale: float, color: str | None = None) -> None:
    fill = color or SESSION_BAR
    for x1, y1, x2, y2 in CLAWD_RECTS:
        c.create_rectangle(x0 + x1 * scale, y0 + y1 * scale,
                           x0 + x2 * scale, y0 + y2 * scale,
                           fill=fill, outline="")


def _status_color(status: str, has_sessions: bool = True) -> str:
    if not has_sessions:
        return GREY
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
        self._quit_fn     = None            # set by caller to also stop the tray
        self._pin_btn     = (0, 0, 0, 0)   # x1 y1 x2 y2, updated each draw
        self._hide_btn    = (0, 0, 0, 0)
        self._quit_btn    = (0, 0, 0, 0)

        self._position_mode, self._pos_x, self._pos_y = _load_position_config()
        if self._pos_x is None or self._pos_y is None:
            self._pos_x, self._pos_y = OFFSET_X, OFFSET_Y
        self._drag_offset = (0, 0)
        self._cur_w, self._cur_h = CW, CH

        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.attributes("-alpha", ALPHA_IDLE)
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

    def reload_style(self):
        reload_stylesheet()
        self.configure(bg=BG)
        self.canvas.configure(bg=BG)
        alpha = ALPHA_ACTIVE if self._expanded else ALPHA_IDLE
        self.attributes("-alpha", alpha)
        self._draw()

    # ── Expand / collapse ─────────────────────────────────────────────────────

    def _expand(self):
        self._expanded = True
        self.attributes("-alpha", ALPHA_ACTIVE)
        sessions = self._monitor.sessions
        eh = _expanded_height(len(sessions))
        self._set_geometry(EW, eh)
        self._draw()

    def _collapse(self):
        self._expanded = False
        self.attributes("-alpha", ALPHA_IDLE)
        self._set_geometry(CW, CH)
        self._draw()

    def _set_geometry(self, w, h):
        if self._position_mode == POS_DRAGGABLE:
            # Keep the top-right corner anchored: shift the left edge left/right
            # as the width changes instead of growing from the top-left corner.
            self._pos_x += self._cur_w - w
        self.canvas.config(width=w, height=h)
        self._cur_w, self._cur_h = w, h
        x, y = self._compute_position(w, h)
        self._pos_x, self._pos_y = x, y
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _compute_position(self, w, h):
        if self._position_mode == POS_DRAGGABLE:
            return self._pos_x, self._pos_y

        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        if self._position_mode == POS_TOP_RIGHT:
            return sw - w - OFFSET_X, OFFSET_Y
        if self._position_mode == POS_BOTTOM_LEFT:
            return OFFSET_X, sh - h - OFFSET_Y
        if self._position_mode == POS_BOTTOM_RIGHT:
            return sw - w - OFFSET_X, sh - h - OFFSET_Y
        return OFFSET_X, OFFSET_Y  # top-left (default)

    # ── Position mode (called from the tray) ─────────────────────────────────

    def set_position_mode(self, mode):
        self._position_mode = mode
        self._set_geometry(self._cur_w, self._cur_h)
        _save_position_config(self._position_mode, self._pos_x, self._pos_y)
        self._draw()

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
            self._draw_collapsed(c, status, usage, reset_m, bool(sessions))

        if self._position_mode == POS_DRAGGABLE:
            self._draw_drag_handle(c)

    # ── Drag handle ───────────────────────────────────────────────────────────

    def _drag_handle_bounds(self):
        x2 = self._cur_w - HANDLE_MARGIN
        x1 = x2 - HANDLE_SIZE
        y1 = HANDLE_MARGIN
        y2 = y1 + HANDLE_SIZE
        return x1, y1, x2, y2

    def _draw_drag_handle(self, c):
        x1, y1, x2, y2 = self._drag_handle_bounds()
        c.create_rectangle(x1, y1, x2, y2, fill=BAR_BG, outline=BORDER, width=1)
        for i in range(2):
            for j in range(2):
                cx = x1 + 3 + i * 4
                cy = y1 + 3 + j * 4
                c.create_oval(cx - 1, cy - 1, cx + 1, cy + 1, fill=TEXT_DIM, outline="")

    def _start_drag(self, event):
        self._drag_offset = (event.x, event.y)
        self.canvas.bind("<B1-Motion>", self._on_drag_motion)
        self.canvas.bind("<ButtonRelease-1>", self._on_drag_release)

    def _on_drag_motion(self, event):
        dx, dy = self._drag_offset
        self._pos_x = self.winfo_pointerx() - dx
        self._pos_y = self.winfo_pointery() - dy
        self.geometry(f"+{self._pos_x}+{self._pos_y}")

    def _on_drag_release(self, event):
        self.canvas.unbind("<B1-Motion>")
        self.canvas.unbind("<ButtonRelease-1>")
        _save_position_config(self._position_mode, self._pos_x, self._pos_y)

    # ── Collapsed ─────────────────────────────────────────────────────────────

    def _draw_collapsed(self, c, status, usage, reset_m, has_sessions):
        W, H = CW, CH
        c.create_rectangle(0, 0, W, H, fill=BG, outline=BORDER)

        COLLAPSED_BAR_H = 8
        block_h = COLLAPSED_BAR_H + SESSION_GAP + SESSION_BAR_H
        by1 = (H - block_h) // 2
        by2 = by1 + COLLAPSED_BAR_H
        sby1 = by2 + SESSION_GAP
        sby2 = sby1 + SESSION_BAR_H

        dot_x, dot_y, dot_r = 16, (by1 + by2) // 2, 6
        c.create_oval(dot_x - dot_r, dot_y - dot_r,
                      dot_x + dot_r, dot_y + dot_r,
                      fill=_status_color(status, has_sessions), outline="")

        bx1, bx2 = 30, W - 10
        c.create_rectangle(bx1, by1, bx2, by2, fill=BAR_BG, outline="")
        if usage > 0:
            fx2 = bx1 + int((bx2 - bx1) * min(usage, 1.0))
            c.create_rectangle(bx1, by1, fx2, by2,
                               fill=self._bar_color(usage), outline="")

        # Session-window bar (how much of the 5h window is left)
        c.create_rectangle(bx1, sby1, bx2, sby2, fill=BAR_BG, outline="")
        remaining = reset_m / SESSION_WINDOW_MIN
        remaining = max(0.0, min(remaining, 1.0))
        if remaining > 0:
            fx2 = bx1 + int((bx2 - bx1) * remaining)
            c.create_rectangle(bx1, sby1, fx2, sby2,
                               fill=SESSION_BAR, outline="")

    # ── Expanded ──────────────────────────────────────────────────────────────

    def _draw_expanded(self, c, sessions, usage, reset_m):
        W = EW
        H = _expanded_height(len(sessions))

        c.create_rectangle(0, 0, W, H, fill=BG, outline=BORDER)

        # Mascot + title (share one vertical center so they align)
        title_y = HEADER_H // 2 + 2
        MASCOT_SCALE = 0.5
        mascot_w = CLAWD_W * MASCOT_SCALE
        mascot_h = CLAWD_H * MASCOT_SCALE
        mascot_x = 13
        mascot_y = title_y - mascot_h / 2
        _draw_clawd(c, mascot_x, mascot_y, MASCOT_SCALE)

        c.create_text(mascot_x + mascot_w + 7, title_y, text="Claude Usage",
                      anchor="w", fill=TEXT_PRI, font=FONT_BOLD)

        # Header buttons (top-right): [Quit] [Hide] [Pin/Unpin]
        BTN_W = 38
        BTN_GAP = 10
        btn_y1 = 6
        btn_y2 = HEADER_H - 6
        mid_y = (btn_y1 + btn_y2) // 2

        BTN_FILL        = BAR_BG          # #1a1a1a — resting state
        BTN_FILL_ACTIVE = "#2a2a2a"       # slightly lifted for pinned state

        # Leave room for the drag handle in the top-right corner, if shown
        handle_reserve = (HANDLE_MARGIN + HANDLE_SIZE + 6) if self._position_mode == POS_DRAGGABLE else 0

        # Pin button (rightmost)
        pin_x2 = W - 8 - handle_reserve
        pin_x1 = pin_x2 - BTN_W
        self._pin_btn = (pin_x1, btn_y1, pin_x2, btn_y2)
        pin_color = BTN_FILL_ACTIVE if self._pinned else BTN_FILL
        c.create_rectangle(pin_x1, btn_y1, pin_x2, btn_y2,
                           fill=pin_color, outline=BORDER, width=1)
        c.create_text((pin_x1 + pin_x2) // 2, mid_y,
                      text="Unpin" if self._pinned else "Pin",
                      fill=TEXT_PRI, font=FONT_SM)

        # Hide button
        hide_x2 = pin_x1 - BTN_GAP
        hide_x1 = hide_x2 - BTN_W
        self._hide_btn = (hide_x1, btn_y1, hide_x2, btn_y2)
        c.create_rectangle(hide_x1, btn_y1, hide_x2, btn_y2,
                           fill=BTN_FILL, outline=BORDER, width=1)
        c.create_text((hide_x1 + hide_x2) // 2, mid_y,
                      text="Hide", fill=TEXT_PRI, font=FONT_SM)

        # Quit button
        quit_x2 = hide_x1 - BTN_GAP
        quit_x1 = quit_x2 - BTN_W
        self._quit_btn = (quit_x1, btn_y1, quit_x2, btn_y2)
        c.create_rectangle(quit_x1, btn_y1, quit_x2, btn_y2,
                           fill=BTN_FILL, outline=BORDER, width=1)
        c.create_text((quit_x1 + quit_x2) // 2, mid_y,
                      text="Quit", fill=TEXT_PRI, font=FONT_SM)

        # Session rows
        row_y_start = HEADER_H + GAP
        if not sessions:
            c.create_text(13, row_y_start + ROW_H // 2, text="No active sessions",
                          anchor="w", fill=TEXT_DIM, font=FONT)
        else:
            for i, sess in enumerate(sessions):
                self._draw_session_row(c, row_y_start + i * ROW_H, sess)

        # Progress bar geometry (anchored above the session bar, from the bottom)
        bx1, bx2 = 13, W - 13
        by1 = H - PAD_BOT - SESSION_GAP - SESSION_BAR_H - BAR_H
        by2 = by1 + BAR_H

        # Usage info (kept anchored directly above the main bar)
        info_y = by1 - INFO_H + INFO_H // 2
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
        c.create_rectangle(bx1, by1, bx2, by2, fill=BAR_BG, outline="")
        if usage > 0:
            fx2 = bx1 + int((bx2 - bx1) * min(usage, 1.0))
            c.create_rectangle(bx1, by1, fx2, by2,
                               fill=self._bar_color(usage), outline="")

        # Session-window progress bar (how much of the 5h window is left)
        sby1 = by2 + SESSION_GAP
        sby2 = sby1 + SESSION_BAR_H
        c.create_rectangle(bx1, sby1, bx2, sby2, fill=BAR_BG, outline="")
        remaining = reset_m / SESSION_WINDOW_MIN
        remaining = max(0.0, min(remaining, 1.0))
        if remaining > 0:
            fx2 = bx1 + int((bx2 - bx1) * remaining)
            c.create_rectangle(bx1, sby1, fx2, sby2,
                               fill=SESSION_BAR, outline="")

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
        # Drag handle
        if self._position_mode == POS_DRAGGABLE:
            x1, y1, x2, y2 = self._drag_handle_bounds()
            if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                self._start_drag(event)
                return

        # Quit button
        qx1, qy1, qx2, qy2 = self._quit_btn
        if qx1 <= event.x <= qx2 and qy1 <= event.y <= qy2:
            if self._quit_fn:
                self._quit_fn()
            else:
                self._root.destroy()
            return

        # Hide button
        hx1, hy1, hx2, hy2 = self._hide_btn
        if hx1 <= event.x <= hx2 and hy1 <= event.y <= hy2:
            self.toggle_visible()
            return

        # Pin button
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
