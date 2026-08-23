"""The fullscreen, transparent, click-through-capable overlay window: draws the ink
canvas, the avatar face (eyes tracking the mouse), and the status badge, and owns all
input-mode toggling (draw / hand-control / pass-through).
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPoint, QPointF, QRect, Qt, QTimer
from PySide6.QtGui import (
    QBrush,
    QColor,
    QCursor,
    QFont,
    QGuiApplication,
    QMouseEvent,
    QPainter,
    QPen,
)
from PySide6.QtWidgets import QWidget

from . import input_injector, native
from .agent_brain import StubAgentBrain
from .global_hotkey import GlobalHotkeys
from .hand_tracker import HandFrame, HandGesture, HandTrackerThread

VK_D = 0x44
VK_Q = 0x51
VK_H = 0x48

FACE_SIZE = 140
EYE_OFFSET_X = 25
EYE_OFFSET_Y = 5
EYE_RADIUS = 17
PUPIL_RADIUS = 7
PUPIL_RANGE = 8.0

COLOR_PASS_THROUGH = QColor(0x80, 0x80, 0x80)
COLOR_DRAW_MODE = QColor(0x32, 0xCD, 0x32)  # LimeGreen
COLOR_HAND_CONTROL = QColor(0x00, 0xFF, 0xFF)  # Cyan
COLOR_ERROR = QColor(0xFF, 0x45, 0x00)  # OrangeRed


class OverlayWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setMouseTracking(True)

        self._draw_mode = False
        self._hand_control_enabled = False
        self._was_pinching = False
        self._native_ready = False
        self._status_text = "Pass-through"
        self._status_color = COLOR_PASS_THROUGH
        self._pupil_offset = QPointF(0, 0)
        self._strokes: list[list[QPointF]] = []
        self._current_stroke: list[QPointF] | None = None

        self._hotkeys = GlobalHotkeys()
        self._hand_tracker: HandTrackerThread | None = None
        # Not wired to anything yet -- see agent_brain.py.
        self._agent_brain = StubAgentBrain()

        self._cover_virtual_desktop()

        self._eye_timer = QTimer(self)
        self._eye_timer.timeout.connect(self._update_eye_look)
        self._eye_timer.start(16)

    # ---- geometry -------------------------------------------------------

    def _cover_virtual_desktop(self) -> None:
        """Spans every monitor. Qt's screen geometries are already in one shared global
        coordinate space, so no manual per-monitor offset math is needed here (unlike the
        raw Win32 approach) -- just union all screens' rects."""
        virtual_rect = QRect()
        for screen in QGuiApplication.screens():
            virtual_rect = virtual_rect.united(screen.geometry())
        self.setGeometry(virtual_rect)
        self._virtual_origin = virtual_rect.topLeft()

        # Everything drawn below (face, badge) is anchored to the primary monitor
        # specifically, not this window's full virtual-desktop bounding box -- on a
        # multi-monitor setup those only coincide with a symmetric arrangement.
        primary_rect = QGuiApplication.primaryScreen().geometry()
        self._primary_local = primary_rect.translated(
            -self._virtual_origin.x(), -self._virtual_origin.y()
        )

    # ---- startup / click-through -----------------------------------------

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._native_ready:
            return
        self._native_ready = True

        app = QGuiApplication.instance()
        app.installNativeEventFilter(self._hotkeys)
        # Click-through first, hotkeys after: _set_click_through() resets the status
        # text via _update_mode_visuals(), which would otherwise immediately overwrite
        # a "hotkey unavailable" warning from _register_hotkeys().
        self._set_click_through(True)
        self._register_hotkeys()

    def _hwnd(self) -> int:
        return int(self.winId())

    def _set_click_through(self, click_through: bool) -> None:
        native.set_click_through(self._hwnd(), click_through)
        self._draw_mode = not click_through
        self._update_mode_visuals()
        self.update()

    # ---- hotkeys ----------------------------------------------------------

    def _register_hotkeys(self) -> None:
        # Hotkey registration can fail if another app already owns the exact combo --
        # that must never take the whole overlay down with it, just surface a message.
        if self._hotkeys.register(native.MOD_CONTROL | native.MOD_ALT, VK_D, self._toggle_draw_mode) is None:
            self._status_text = "Ctrl+Alt+D unavailable (in use by another app)"

        if self._hotkeys.register(native.MOD_CONTROL | native.MOD_ALT, VK_Q, self._kill_switch) is None:
            self._status_text = "Ctrl+Alt+Q unavailable (in use by another app)"

        if self._hotkeys.register(native.MOD_CONTROL | native.MOD_ALT, VK_H, self._toggle_hand_control) is None:
            self._status_text = "Ctrl+Alt+H unavailable (in use by another app)"

        self.update()

    def _kill_switch(self) -> None:
        # Always available, in every mode, no confirmation dialog to fight through -- an
        # overlay that can inject input needs an instant, unconditional way to shut down.
        QGuiApplication.instance().quit()

    def _toggle_draw_mode(self) -> None:
        self._set_click_through(click_through=self._draw_mode)

    # ---- hand control -------------------------------------------------------

    def _toggle_hand_control(self) -> None:
        self._hand_control_enabled = not self._hand_control_enabled

        if self._hand_control_enabled:
            self._hand_tracker = HandTrackerThread()
            self._hand_tracker.frame_received.connect(self._on_hand_frame)
            self._hand_tracker.failed.connect(self._on_hand_tracker_failed)
            self._hand_tracker.start()
        elif self._hand_tracker is not None:
            self._hand_tracker.stop()
            self._hand_tracker = None
            self._was_pinching = False

        self._update_mode_visuals()
        self.update()

    def _on_hand_tracker_failed(self, message: str) -> None:
        self._hand_control_enabled = False
        self._was_pinching = False
        if self._hand_tracker is not None:
            self._hand_tracker.stop()
            self._hand_tracker = None
        self._status_text = f"Hand tracker: {message}"
        self._status_color = COLOR_ERROR
        self.update()

    def _on_hand_frame(self, frame: HandFrame) -> None:
        """Turns one hand-tracking frame into cursor movement and, on a pinch, a click.
        This is the only place gestures reach input_injector -- nothing here runs unless
        hand control was explicitly armed via Ctrl+Alt+H."""
        if not self._hand_control_enabled:
            return
        if not frame.hand_present:
            self._was_pinching = False
            return

        # Mirror X: moving your hand to your right, as you face the camera, should move
        # the cursor right on screen -- matching a mirror/selfie view, not the raw frame.
        mirrored_x = 1.0 - frame.cursor_x

        primary = QGuiApplication.primaryScreen().geometry()
        x = primary.left() + int(_clamp01(mirrored_x) * primary.width())
        y = primary.top() + int(_clamp01(frame.cursor_y) * primary.height())

        input_injector.move_to(x, y)

        is_pinching = frame.gesture == HandGesture.PINCH
        if is_pinching and not self._was_pinching:
            input_injector.click_at(x, y)
        self._was_pinching = is_pinching

    # ---- mode visuals ---------------------------------------------------------

    def _update_mode_visuals(self) -> None:
        if self._hand_control_enabled:
            self._status_text = "Hand Control ON (Ctrl+Alt+H to stop)"
            self._status_color = COLOR_HAND_CONTROL
        elif self._draw_mode:
            self._status_text = "Draw Mode (Ctrl+Alt+D to release)"
            self._status_color = COLOR_DRAW_MODE
        else:
            self._status_text = "Pass-through"
            self._status_color = COLOR_PASS_THROUGH

    # ---- eye tracking -----------------------------------------------------------

    def _update_eye_look(self) -> None:
        """Points both pupils toward the current mouse position. Uses QCursor.pos()
        (Qt's own global cursor query) rather than a Win32 poll -- unlike WPF, Qt can
        report the live cursor position without the window needing mouse focus."""
        cursor_local = QCursor.pos() - self._virtual_origin
        face_center = self._primary_local.center()

        angle = math.atan2(cursor_local.y() - face_center.y(), cursor_local.x() - face_center.x())
        self._pupil_offset = QPointF(math.cos(angle) * PUPIL_RANGE, math.sin(angle) * PUPIL_RANGE)
        self.update()

    # ---- drawing (Draw Mode only) -----------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._draw_mode and event.button() == Qt.LeftButton:
            self._current_stroke = [event.position()]
            self._strokes.append(self._current_stroke)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._draw_mode and self._current_stroke is not None:
            self._current_stroke.append(event.position())
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._current_stroke = None

    # ---- painting ---------------------------------------------------------------

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        self._paint_strokes(painter)
        self._paint_face(painter)
        self._paint_status_badge(painter)

    def _paint_strokes(self, painter: QPainter) -> None:
        pen = QPen(QColor(0x14, 0x14, 0x14), 3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(pen)
        for stroke in self._strokes:
            for a, b in zip(stroke, stroke[1:]):
                painter.drawLine(a, b)

    def _paint_face(self, painter: QPainter) -> None:
        center = self._primary_local.center()
        rect = QRect(0, 0, FACE_SIZE, FACE_SIZE)
        rect.moveCenter(center)

        painter.setBrush(QBrush(QColor(0x7C, 0x3A, 0xED, 0xF0)))
        painter.setPen(QPen(self._status_color, 3))
        painter.drawEllipse(rect)

        for side in (-1, 1):
            eye_center = QPointF(center.x() + side * EYE_OFFSET_X, center.y() + EYE_OFFSET_Y)

            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor("white")))
            painter.drawEllipse(eye_center, EYE_RADIUS, EYE_RADIUS)

            pupil_center = eye_center + self._pupil_offset
            painter.setBrush(QBrush(QColor(0x20, 0x20, 0x20)))
            painter.drawEllipse(pupil_center, PUPIL_RADIUS, PUPIL_RADIUS)

    def _paint_status_badge(self, painter: QPainter) -> None:
        painter.setFont(QFont("Consolas", 10))
        metrics = painter.fontMetrics()
        padding = 8
        dot_and_gap = 16
        text_width = metrics.horizontalAdvance(self._status_text)

        badge_rect = QRect(0, 0, text_width + dot_and_gap + padding * 2, metrics.height() + padding)
        badge_rect.moveTopRight(QPoint(self._primary_local.right() - 12, self._primary_local.top() + 12))

        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(0x20, 0x20, 0x20, 0xEE)))
        painter.drawRoundedRect(badge_rect, 6, 6)

        dot_center = QPointF(badge_rect.left() + padding + 5, badge_rect.center().y())
        painter.setBrush(QBrush(self._status_color))
        painter.drawEllipse(dot_center, 5, 5)

        painter.setPen(QPen(QColor("white")))
        text_rect = QRect(
            badge_rect.left() + padding + dot_and_gap,
            badge_rect.top(),
            text_width + padding,
            badge_rect.height(),
        )
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, self._status_text)

    # ---- shutdown ---------------------------------------------------------------

    def closeEvent(self, event) -> None:
        self._hotkeys.unregister_all()
        if self._hand_tracker is not None:
            self._hand_tracker.stop()
        super().closeEvent(event)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))
