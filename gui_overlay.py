"""
gui_overlay.py — วงกลมเวทมนตร์ (Magic Circle) Overlay ของราฟาเอล

PyQt6 translucent frameless overlay ที่แสดงวงกลมเรขาคณิตเรืองแสง
สไตล์ anime — วงกลมซ้อน, hexagram, rune marks, particle effects
เปลี่ยนสถานะ animation ตาม state: IDLE, LISTENING, ANALYZING, SPEAKING
"""

from __future__ import annotations

import math
import random
import logging
from enum import Enum
from typing import Optional

from PyQt6.QtCore import (
    Qt,
    QTimer,
    QPointF,
    QRectF,
    pyqtSignal,
    pyqtProperty,
    QPropertyAnimation,
    QEasingCurve,
    QSize,
)
from PyQt6.QtGui import (
    QPainter,
    QPen,
    QColor,
    QBrush,
    QFont,
    QRadialGradient,
    QPainterPath,
    QMouseEvent,
    QPaintEvent,
    QScreen,
    QPixmap,
    QIcon,
)
from PyQt6.QtWidgets import (
    QWidget,
    QApplication,
    QMenu,
    QSystemTrayIcon,
)

import sys
import winreg
from pathlib import Path

import config

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
#  Enums & Data
# ═══════════════════════════════════════════════════════════

class AssistantState(Enum):
    """สถานะของผู้ช่วย — มีผลต่อ animation"""
    IDLE = "idle"             # สงบ หมุนช้า
    LISTENING = "listening"   # กำลังฟัง เต้นจังหวะ
    ANALYZING = "analyzing"   # ประมวลผล หมุนเร็ว
    SPEAKING = "speaking"     # กำลังพูด สั่นตามเสียง


class Particle:
    """อนุภาคเล็กๆ ที่ลอยรอบวงกลมเวทมนตร์"""

    def __init__(self, radius: float) -> None:
        self.angle = random.uniform(0, 2 * math.pi)
        self.radius = radius + random.uniform(-20, 20)
        self.speed = random.uniform(0.005, 0.02)
        self.size = random.uniform(1.0, 3.0)
        self.alpha = random.randint(80, 200)
        self.drift = random.uniform(-0.3, 0.3)  # การเคลื่อนที่ radial

    def update(self) -> None:
        self.angle += self.speed
        self.radius += self.drift * 0.1
        self.alpha = max(30, min(220, self.alpha + random.randint(-5, 5)))

    @property
    def x(self) -> float:
        return math.cos(self.angle) * self.radius

    @property
    def y(self) -> float:
        return math.sin(self.angle) * self.radius


# ═══════════════════════════════════════════════════════════
#  Themes Preset Data
# ═══════════════════════════════════════════════════════════

THEMES: dict[str, dict[str, str]] = {
    "raphael": {
        "name": "ราฟาเอล (ทองอำพัน/แดงชาด)",
        "primary": "#FFB300",
        "dim": "#7A4E00",
        "glow": "#FFA000",
        "accent": "#FF2E4C",
        "listening": "#FFE066",
        "analyzing": "#FF2A4D",
        "speaking": "#FF9100",
    },
    "rimuru": {
        "name": "ริมุรุ (ฟ้าครามสไลม์)",
        "primary": "#00FFFF",
        "dim": "#006677",
        "glow": "#00B4D8",
        "accent": "#48CAE4",
        "listening": "#90E0EF",
        "analyzing": "#0077B6",
        "speaking": "#0096C7",
    },
    "demon_lord": {
        "name": "จอมมาร (ม่วงรัตติกาล/มาเจนต้า)",
        "primary": "#BA68C8",
        "dim": "#4A148C",
        "glow": "#AB47BC",
        "accent": "#FF4081",
        "listening": "#E1BEE7",
        "analyzing": "#7B1FA2",
        "speaking": "#EA80FC",
    },
    "forest": {
        "name": "เอลฟ์ (เขียวมรกต/มิ้นต์)",
        "primary": "#00E676",
        "dim": "#004D40",
        "glow": "#00C853",
        "accent": "#69F0AE",
        "listening": "#B9F6CA",
        "analyzing": "#1DE9B6",
        "speaking": "#00BFA5",
    },
    "solar": {
        "name": "สุริยัน (แดงเพลิง/ส้มแสด)",
        "primary": "#FF3D00",
        "dim": "#BF360C",
        "glow": "#FF6E40",
        "accent": "#FFD600",
        "listening": "#FFAB40",
        "analyzing": "#DD2C00",
        "speaking": "#FF6D00",
    },
}

# ═══════════════════════════════════════════════════════════
#  Magic Circle Overlay Widget
# ═══════════════════════════════════════════════════════════

class MagicCircleOverlay(QWidget):
    """วงกลมเวทมนตร์แบบ overlay — translucent, frameless, stays on top"""

    # Signals
    clicked = pyqtSignal()                # คลิกที่ overlay (เริ่มฟัง)
    state_label_text = pyqtSignal(str)    # สำหรับแสดงสถานะ

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        # ─── Window Setup ───
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool  # ไม่แสดงใน taskbar
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(config.OVERLAY_SIZE, config.OVERLAY_SIZE)

        # ─── State ───
        self._state = AssistantState.IDLE
        self._frame = 0
        self._glow_intensity = 0.5   # 0.0 - 1.0
        self._pulse_phase = 0.0
        self._speaking_amplitude = 0.0  # สำหรับ sync กับเสียง (0.0-1.0)
        self._smooth_amplitude = 0.0    # damped amplitude เพื่อความนุ่มนวล 60 FPS

        # ─── Rotation angles (วงกลมแต่ละวงหมุนคนละทิศ) ───
        self._angle_outer = 0.0
        self._angle_middle = 0.0
        self._angle_inner = 0.0
        self._angle_runes = 0.0

        # ─── Particles ───
        self._particles: list[Particle] = [
            Particle(config.OVERLAY_SIZE * 0.4) for _ in range(25)
        ]

        # ─── Colors ───
        self._color_primary = QColor(config.COLOR_PRIMARY)
        self._color_dim = QColor(config.COLOR_PRIMARY_DIM)
        self._color_glow = QColor(config.COLOR_GLOW)
        self._color_accent = QColor(config.COLOR_ACCENT)
        self._color_listening = QColor(getattr(config, "COLOR_LISTENING", "#FFE066"))
        self._color_analyzing = QColor(getattr(config, "COLOR_ANALYZING", "#FF2A4D"))
        self._color_speaking = QColor(getattr(config, "COLOR_SPEAKING", "#FF9100"))

        # ─── Drag support ───
        self._drag_pos: Optional[QPointF] = None
        self._drag_start_pos: Optional[QPointF] = None
        self._is_dragging: bool = False

        # ─── Current Theme ───
        self._current_theme_key = "raphael"

        # ─── System Tray ───
        self._init_system_tray()

        # ─── Animation Timer ───
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)
        self._timer.start(config.OVERLAY_FPS)

        # ─── ตำแหน่งเริ่มต้น ───
        self._move_to_default_position()

        logger.info("MagicCircleOverlay created — size=%d", config.OVERLAY_SIZE)

    # ─── Position ───

    def _move_to_default_position(self) -> None:
        """ย้ายไปตำแหน่งเริ่มต้น (มุมบนขวา)"""
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = geo.right() - self.width() - config.OVERLAY_MARGIN
            y = geo.top() + config.OVERLAY_MARGIN
            self.move(x, y)



    def set_theme(self, theme_key: str) -> bool:
        """สลับธีมสีของวงแหวนเวทมนตร์และ UI ทั้งหมด"""
        key = theme_key.lower().strip()
        matched_key = None
        if key in THEMES:
            matched_key = key
        else:
            for k, data in THEMES.items():
                if k in key or data["name"].lower() in key:
                    matched_key = k
                    break
                if "ทอง" in key and k == "raphael":
                    matched_key = k
                    break
                if ("ฟ้า" in key or "สไลม์" in key) and k == "rimuru":
                    matched_key = k
                    break
                if ("ม่วง" in key or "จอมมาร" in key) and k == "demon_lord":
                    matched_key = k
                    break
                if ("เขียว" in key or "เอลฟ์" in key) and k == "forest":
                    matched_key = k
                    break
                if ("แดง" in key or "สุริยัน" in key) and k == "solar":
                    matched_key = k
                    break

        if not matched_key:
            logger.warning("Unknown theme key: '%s'", theme_key)
            return False

        t = THEMES[matched_key]
        self._current_theme_key = matched_key
        self._color_primary = QColor(t["primary"])
        self._color_dim = QColor(t["dim"])
        self._color_glow = QColor(t["glow"])
        self._color_accent = QColor(t["accent"])
        self._color_listening = QColor(t["listening"])
        self._color_analyzing = QColor(t["analyzing"])
        self._color_speaking = QColor(t["speaking"])

        self._update_tray_icon()

        logger.info("Theme switched to '%s' (%s)", matched_key, t["name"])
        self.update()
        return True

    # ─── State Management ───

    @property
    def state(self) -> AssistantState:
        return self._state

    def set_state(self, new_state: AssistantState) -> None:
        """เปลี่ยนสถานะ animation"""
        if self._state != new_state:
            old = self._state
            self._state = new_state
            if new_state != AssistantState.SPEAKING:
                self._speaking_amplitude = 0.0
            logger.info("State: %s → %s", old.value, new_state.value)
            self.update()

    def set_speaking_amplitude(self, amplitude: float) -> None:
        """ตั้งค่า amplitude สำหรับ animation ขณะพูด (0.0-1.0)"""
        self._speaking_amplitude = max(0.0, min(1.0, amplitude))

    def _get_current_theme_color(self) -> QColor:
        """คืนค่าสีหลักตามสถานะของราฟาเอล (Anime Slime Dynamic Colors)"""
        if self._state == AssistantState.ANALYZING:
            return self._color_analyzing  # สีแดงชาดของดวงตาราฟาเอลขณะคำนวณ
        elif self._state == AssistantState.LISTENING:
            return self._color_listening  # สีเหลืองทองสดใสขณะฟัง
        elif self._state == AssistantState.SPEAKING:
            return self._color_speaking   # สีส้มทองเปล่งประกายขณะพูด
        return self._color_primary        # สีทองอำพันปกติ

    # ─── Animation Tick ───

    def _on_tick(self) -> None:
        """อัพเดต animation ทุก frame"""
        self._frame += 1
        self._pulse_phase += 0.08
        self._smooth_amplitude += (self._speaking_amplitude - self._smooth_amplitude) * 0.35

        # ─── ความเร็วหมุนและแสงเรืองตาม state ───
        if self._state == AssistantState.IDLE:
            speed = 0.35
            self._glow_intensity = 0.8 + 0.18 * math.sin(self._pulse_phase * 0.6)
        elif self._state == AssistantState.LISTENING:
            speed = 0.7
            self._glow_intensity = 0.9 + 0.15 * math.sin(self._pulse_phase * 1.8)
        elif self._state == AssistantState.ANALYZING:
            speed = 2.2
            self._glow_intensity = 0.95 + 0.05 * math.sin(self._pulse_phase * 3.0)
        elif self._state == AssistantState.SPEAKING:
            synth_wave = math.sin(self._pulse_phase * 2.8) * 0.25 + 0.25
            effective_amp = max(self._smooth_amplitude, synth_wave * 0.45)
            speed = 1.0 + 3.2 * effective_amp
            self._glow_intensity = 0.75 + 0.5 * effective_amp
        else:
            speed = 0.35
            self._glow_intensity = 0.8

        # หมุนวงกลมแต่ละวงคนละทิศ
        self._angle_outer += speed
        self._angle_middle -= speed * 0.7
        self._angle_inner += speed * 1.3
        self._angle_runes -= speed * 0.4

        # อัพเดต particles
        for p in self._particles:
            p.update()

        self.update()  # trigger repaint

    # ─── Paint ───

    def paintEvent(self, event: QPaintEvent) -> None:
        """วาดวงกลมเวทมนตร์ทั้งหมด"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        center_x = self.width() / 2
        # เลื่อนศูนย์กลางวงกลมขึ้นเล็กน้อย เพื่อเว้นพื้นที่ด้านล่างให้ข้อความอย่างชัดเจน ไม่ทับซ้อนกับวงกลม
        center_y = self.height() / 2 - 18

        # ปรับขนาดวงเวทย์ตามจังหวะเสียงพูด ให้ขยาย-หดเหมือนมีชีวิต (Voice Scale Modulation)
        scale_mod = 1.0
        if self._state == AssistantState.SPEAKING:
            synth_wave = math.sin(self._pulse_phase * 2.8) * 0.25 + 0.25
            effective_amp = max(self._smooth_amplitude, synth_wave * 0.45)
            scale_mod = 1.0 + 0.12 * effective_amp
        elif self._state == AssistantState.LISTENING:
            scale_mod = 1.0 + 0.03 * math.sin(self._pulse_phase * 1.5)

        base_radius = min(center_x, self.height() / 2) * 0.70 * scale_mod

        # ย้ายจุดศูนย์กลาง
        painter.translate(center_x, center_y)

        # ─── Layer 1: Background Glow ───
        self._draw_background_glow(painter, base_radius)

        # ─── Layer 1.5: Voice Ripple Waves (เฉพาะขณะพูด — Audio Visualizer Waves) ───
        if self._state == AssistantState.SPEAKING:
            self._draw_voice_ripples(painter, base_radius)

        # ─── Layer 2: Outer Circle ───
        painter.save()
        painter.rotate(self._angle_outer)
        self._draw_circle_ring(painter, base_radius * 0.95, width=2.0, alpha=180)
        self._draw_circle_ring(painter, base_radius * 0.90, width=1.0, alpha=100)
        self._draw_tick_marks(painter, base_radius * 0.92, count=60, length=5)
        painter.restore()

        # ─── Layer 3: Middle Hexagram ───
        painter.save()
        painter.rotate(self._angle_middle)
        self._draw_hexagram(painter, base_radius * 0.75, alpha=160)
        self._draw_circle_ring(painter, base_radius * 0.70, width=1.5, alpha=140)
        painter.restore()

        # ─── Layer 4: Inner Circle + Triangle ───
        painter.save()
        painter.rotate(self._angle_inner)
        self._draw_circle_ring(painter, base_radius * 0.50, width=2.0, alpha=200)
        self._draw_triangle(painter, base_radius * 0.45, alpha=150)
        painter.restore()

        # ─── Layer 5: Rune Text ───
        painter.save()
        painter.rotate(self._angle_runes)
        self._draw_rune_text(painter, base_radius * 0.82)
        painter.restore()

        # ─── Layer 6: Center Core ───
        self._draw_center_core(painter, base_radius * 0.15)

        # ─── Layer 7: Particles ───
        self._draw_particles(painter)

        # ─── Layer 8: State Label (อยู่ใต้ขอบวงกลมอย่างชัดเจน) ───
        self._draw_state_label(painter, base_radius)

        painter.end()

    # ─── Drawing Helpers ───

    def _draw_background_glow(self, painter: QPainter, radius: float) -> None:
        """วาดพื้นหลังวงเวทย์: แผ่นพลังงานโปร่งแสงเข้ม + radial amber glow เพื่อให้เห็นชัดบนทุกพื้นหลัง"""
        theme_color = self._get_current_theme_color()
        tr, tg, tb = theme_color.red(), theme_color.green(), theme_color.blue()
        gr, gg, gb = self._color_glow.red(), self._color_glow.green(), self._color_glow.blue()

        # 1. Dark anime magical summoning disc (ทำให้เห็นชัดทั้งบนจอขาวและจอดำ)
        disc_gradient = QRadialGradient(QPointF(0, 0), radius * 1.05)
        disc_gradient.setColorAt(0.0, QColor(24, 14, 4, 215))
        disc_gradient.setColorAt(0.70, QColor(18, 10, 2, 190))
        disc_gradient.setColorAt(0.92, QColor(10, 5, 0, 130))
        disc_gradient.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(QBrush(disc_gradient))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(0, 0), radius * 1.05, radius * 1.05)

        # 2. Glowing aura
        glow_alpha = int(90 * self._glow_intensity)
        gradient = QRadialGradient(QPointF(0, 0), radius)
        gradient.setColorAt(0.0, QColor(tr, tg, tb, glow_alpha))
        gradient.setColorAt(0.45, QColor(gr, gg, gb, int(glow_alpha * 0.5)))
        gradient.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(QBrush(gradient))
        painter.drawEllipse(QPointF(0, 0), radius, radius)

    def _draw_voice_ripples(self, painter: QPainter, radius: float) -> None:
        """คลื่นพลังเวทย์แผ่ออกไปรอบๆ ตามจังหวะเสียงพูด (Voice Reactive Ripple Rings)"""
        synth_wave = math.sin(self._pulse_phase * 2.8) * 0.25 + 0.25
        effective_amp = max(self._smooth_amplitude, synth_wave * 0.45)
        sr, sg, sb = self._color_speaking.red(), self._color_speaking.green(), self._color_speaking.blue()
        for ring_idx in range(3):
            phase_offset = ring_idx * (math.pi * 0.4)
            ripple_progress = (self._pulse_phase * 1.5 + phase_offset) % math.pi
            ripple_radius = radius * (1.0 + 0.20 * math.sin(ripple_progress) * (1.0 + effective_amp * 0.8))
            ripple_alpha = int(160 * math.cos(ripple_progress * 0.5) * effective_amp)
            if ripple_alpha > 5:
                pen = QPen(QColor(sr, sg, sb, ripple_alpha), 1.5 + 2.5 * effective_amp)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(QPointF(0, 0), ripple_radius, ripple_radius)

    def _draw_circle_ring(
        self, painter: QPainter, radius: float, width: float = 1.5, alpha: int = 180, color: Optional[QColor] = None
    ) -> None:
        """วาดวงกลมเรืองแสง (3 ชั้น: glow → core → highlight)"""
        intensity = self._glow_intensity
        base_color = color or self._get_current_theme_color()
        r, g, b = base_color.red(), base_color.green(), base_color.blue()

        # ชั้นที่ 1: Outer glow (หนา, โปร่ง)
        glow_pen = QPen(
            QColor(r, g, b, min(255, int(alpha * 0.35 * intensity))),
            width * 3.5,
        )
        painter.setPen(glow_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(0, 0), radius, radius)

        # ชั้นที่ 2: Core (ปานกลาง)
        core_pen = QPen(
            QColor(r, g, b, min(255, int(alpha * intensity))),
            width,
        )
        painter.setPen(core_pen)
        painter.drawEllipse(QPointF(0, 0), radius, radius)

        # ชั้นที่ 3: Highlight (บาง, สว่างขาวอมทอง)
        highlight_pen = QPen(
            QColor(255, 250, 225, min(255, int(alpha * 0.9 * intensity))),
            max(1.0, width * 0.6),
        )
        painter.setPen(highlight_pen)
        painter.drawEllipse(QPointF(0, 0), radius, radius)

    def _draw_tick_marks(
        self, painter: QPainter, radius: float, count: int, length: float
    ) -> None:
        """วาดขีดเล็กๆ รอบวงกลม"""
        theme_color = self._get_current_theme_color()
        alpha = int(100 * self._glow_intensity)
        pen = QPen(QColor(theme_color.red(), theme_color.green(), theme_color.blue(), alpha), 1)
        painter.setPen(pen)

        for i in range(count):
            angle_rad = (2 * math.pi * i) / count
            x1 = math.cos(angle_rad) * radius
            y1 = math.sin(angle_rad) * radius
            inner = radius - length if i % 5 == 0 else radius - length * 0.5
            x2 = math.cos(angle_rad) * inner
            y2 = math.sin(angle_rad) * inner
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

    def _draw_hexagram(self, painter: QPainter, radius: float, alpha: int) -> None:
        """วาด hexagram (ดาวหกแฉก) — สัญลักษณ์เวทมนตร์"""
        theme_color = self._get_current_theme_color()
        intensity = self._glow_intensity
        r, g, b = theme_color.red(), theme_color.green(), theme_color.blue()

        # Glow layer
        glow_pen = QPen(QColor(r, g, b, int(alpha * 0.15 * intensity)), 4)
        painter.setPen(glow_pen)
        self._draw_star_polygon(painter, radius, 6, skip=1)

        # Core layer
        core_pen = QPen(QColor(r, g, b, int(alpha * intensity)), 1.5)
        painter.setPen(core_pen)
        self._draw_star_polygon(painter, radius, 6, skip=1)

    def _draw_star_polygon(
        self, painter: QPainter, radius: float, points: int, skip: int
    ) -> None:
        """วาดรูปดาวจากจุดบนวงกลม"""
        vertices = []
        for i in range(points):
            angle = (2 * math.pi * i) / points - math.pi / 2
            vertices.append(QPointF(
                math.cos(angle) * radius,
                math.sin(angle) * radius,
            ))

        # เชื่อมจุดข้าม skip จุด สร้างรูปดาว
        for i in range(points):
            j = (i + skip + 1) % points
            painter.drawLine(vertices[i], vertices[j])

    def _draw_triangle(self, painter: QPainter, radius: float, alpha: int) -> None:
        """วาดสามเหลี่ยมตรงกลาง — ประดับด้วยสีแดงชาด ดวงตาของราฟาเอล"""
        accent = self._color_accent
        r, g, b = accent.red(), accent.green(), accent.blue()
        intensity = self._glow_intensity

        path = QPainterPath()
        for i in range(3):
            angle = (2 * math.pi * i) / 3 - math.pi / 2
            point = QPointF(
                math.cos(angle) * radius,
                math.sin(angle) * radius,
            )
            if i == 0:
                path.moveTo(point)
            else:
                path.lineTo(point)
        path.closeSubpath()

        # Glow
        painter.setPen(QPen(QColor(r, g, b, int(alpha * 0.25 * intensity)), 3))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

        # Core
        painter.setPen(QPen(QColor(r, g, b, int(alpha * intensity)), 1.5))
        painter.drawPath(path)

    def set_overlay_size(self, size: int) -> None:
        """เปลี่ยนขนาดของ overlay และคำนวณตำแหน่งใหม่"""
        old_right = self.x() + self.width()
        old_top = self.y()
        self.setFixedSize(size, size)
        self._particles = [Particle(size * 0.4) for _ in range(20)]
        self.move(old_right - size, old_top)
        self.update()

    def _draw_rune_text(self, painter: QPainter, radius: float) -> None:
        """วาดตัวอักษร rune เรียงรอบวงกลม (scale ตามขนาดวง)"""
        theme_color = self._get_current_theme_color()
        runes = "᚛ᚐᚁᚂᚃᚄᚅᚆᚇᚈᚉᚊᚋᚌᚍᚎᚏᚐᚑᚒᚓᚔᚕᚖᚗᚘᚙᚚ᚜"
        alpha = int(120 * self._glow_intensity)

        font_size = max(6, int(radius * 0.075))
        font = QFont("Segoe UI Symbol", font_size)
        painter.setFont(font)
        painter.setPen(QColor(theme_color.red(), theme_color.green(), theme_color.blue(), alpha))

        count = len(runes)
        for i, ch in enumerate(runes):
            angle_deg = (360.0 * i) / count
            angle_rad = math.radians(angle_deg)

            x = math.cos(angle_rad) * radius
            y = math.sin(angle_rad) * radius

            painter.save()
            painter.translate(x, y)
            painter.rotate(angle_deg + 90)
            painter.drawText(QPointF(-3, 3), ch)
            painter.restore()

    def _draw_center_core(self, painter: QPainter, radius: float) -> None:
        """วาดแกนกลาง — ลูกแก้วพลังงานจิตวิญญาณแห่งปัญญา (ดวงตาสีแดงชาดของราฟาเอล)"""
        intensity = self._glow_intensity
        theme_color = self._get_current_theme_color()
        accent = self._color_accent
        tr, tg, tb = theme_color.red(), theme_color.green(), theme_color.blue()
        gr, gg, gb = self._color_glow.red(), self._color_glow.green(), self._color_glow.blue()
        ar, ag, ab = accent.red(), accent.green(), accent.blue()

        # Pulse effect with voice reactivity
        synth_wave = math.sin(self._pulse_phase * 2.8) * 0.25 + 0.25
        effective_amp = max(self._smooth_amplitude, synth_wave * 0.45) if self._state == AssistantState.SPEAKING else 0.0
        pulse = 1.0 + 0.15 * math.sin(self._pulse_phase) + 0.35 * effective_amp
        r = radius * pulse

        # Outer glow
        gradient = QRadialGradient(QPointF(0, 0), r * 2.2)
        gradient.setColorAt(0.0, QColor(tr, tg, tb, min(255, int((180 + 75 * effective_amp) * intensity))))
        gradient.setColorAt(0.4, QColor(gr, gg, gb, min(255, int((80 + 60 * effective_amp) * intensity))))
        gradient.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(QBrush(gradient))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(0, 0), r * 2.2, r * 2.2)

        # Core sphere — ลูกแก้วพลังงานแกนกลาง (ดวงตาสีแดงชาดของราฟาเอล)
        core_gradient = QRadialGradient(QPointF(-r * 0.3, -r * 0.3), r)
        core_gradient.setColorAt(0.0, QColor(255, 235, 235, int(255 * intensity)))
        core_gradient.setColorAt(0.45, QColor(ar, ag, ab, int(220 * intensity)))
        core_gradient.setColorAt(1.0, QColor(140, 10, 20, int(160 * intensity)))
        painter.setBrush(QBrush(core_gradient))
        painter.setPen(QPen(QColor(ar, ag, ab, int(200 * intensity)), 1))
        painter.drawEllipse(QPointF(0, 0), r, r)

    def _draw_particles(self, painter: QPainter) -> None:
        """วาดอนุภาคเรืองแสงลอยรอบ"""
        theme_color = self._get_current_theme_color()
        tr, tg, tb = theme_color.red(), theme_color.green(), theme_color.blue()
        for p in self._particles:
            color = QColor(tr, tg, tb, p.alpha)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(color))
            painter.drawEllipse(QPointF(p.x, p.y), p.size, p.size)

    def _draw_state_label(self, painter: QPainter, base_radius: float) -> None:
        """แสดง label สถานะใต้วงกลม แยกออกจากตัววงเวทย์อย่างชัดเจน ไม่ซ้อนทับกัน"""
        theme_color = self._get_current_theme_color()
        labels = {
            AssistantState.IDLE: "ราฟาเอล",
            AssistantState.LISTENING: "● กำลังฟังคำสั่ง...",
            AssistantState.ANALYZING: "⚡ กำลังวิเคราะห์...",
            AssistantState.SPEAKING: "🔮 กำลังตอบกลับ...",
        }
        text = labels.get(self._state, "ราฟาเอล")

        # เริ่มต้นใต้ขอบนอกสุดของวงกลม (base_radius * 0.95 คือขอบวงกลม)
        start_y = base_radius * 0.95 + 8
        w = self.width() * 0.96

        alpha = min(255, int(240 * self._glow_intensity))
        font_size = max(8, int(self.width() * 0.046))
        font = QFont("Segoe UI", font_size)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(theme_color.red(), theme_color.green(), theme_color.blue(), alpha))
        painter.drawText(
            QRectF(-w / 2, start_y, w, 22),
            Qt.AlignmentFlag.AlignCenter,
            text,
        )

        # คำแนะนำเล็กๆ ใต้ชื่อ
        if self._state == AssistantState.IDLE:
            sub_size = max(7, font_size - 2)
            sub_font = QFont("Segoe UI", sub_size)
            painter.setFont(sub_font)
            painter.setPen(QColor(255, 230, 160, int(180 * self._glow_intensity)))
            painter.drawText(
                QRectF(-w / 2, start_y + 20, w, 18),
                Qt.AlignmentFlag.AlignCenter,
                "พูด 'ราฟาเอล' หรือคลิก",
            )

    # ─── Mouse Events (Drag + Click) ───

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.globalPosition()
            self._drag_pos = event.globalPosition()
            self._is_dragging = False
        elif event.button() == Qt.MouseButton.RightButton:
            self._show_context_menu(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_pos and event.buttons() & Qt.MouseButton.LeftButton:
            total_moved = (event.globalPosition() - self._drag_start_pos).manhattanLength()
            if total_moved > 6:
                self._is_dragging = True

            delta = event.globalPosition() - self._drag_pos
            self.move(
                int(self.x() + delta.x()),
                int(self.y() + delta.y()),
            )
            self._drag_pos = event.globalPosition()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            if not getattr(self, "_is_dragging", False):
                # เป็นการคลิกจริงๆ (ไม่ใช่การลากย้ายตำแหน่ง)
                self.clicked.emit()
            self._drag_pos = None
            self._is_dragging = False

    def _get_menu_stylesheet(self) -> str:
        p = self._color_primary.name()
        return f"""
            QMenu {{
                background-color: rgba(18, 14, 24, 240);
                color: #FFFFFF;
                border: 1.5px solid {p};
                padding: 6px;
                font-family: 'Segoe UI';
                font-size: 12px;
                border-radius: 8px;
            }}
            QMenu::item {{
                padding: 6px 24px 6px 12px;
                border-radius: 4px;
            }}
            QMenu::item:selected {{
                background-color: rgba(255, 255, 255, 30);
                color: {p};
            }}
            QMenu::separator {{
                height: 1px;
                background: rgba(255, 255, 255, 40);
                margin: 4px 6px;
            }}
        """

    def _show_context_menu(self, event: QMouseEvent) -> None:
        """แสดงเมนูคลิกขวา พร้อมตัวเลือกธีมสีและปรับขนาด"""
        menu = QMenu(self)
        menu.setStyleSheet(self._get_menu_stylesheet())

        # เมนูเปลี่ยนธีมสี
        theme_menu = menu.addMenu("🎨 สลับธีมสี (Themes)")
        for k, data in THEMES.items():
            act = theme_menu.addAction(f"● {data['name']}")
            act.triggered.connect(lambda checked=False, tk=k: self.set_theme(tk))

        size_menu = menu.addMenu("📐 ปรับขนาดวงเวทย์")
        size_small = size_menu.addAction(" เล็กกะทัดรัด (180 px)")
        size_small.triggered.connect(lambda: self.set_overlay_size(180))
        size_normal = size_menu.addAction(" พอดีจอ (220 px)")
        size_normal.triggered.connect(lambda: self.set_overlay_size(220))
        size_large = size_menu.addAction(" ใหญ่เต็มตา (280 px)")
        size_large.triggered.connect(lambda: self.set_overlay_size(280))

        reset_pos = menu.addAction("📍 กลับตำแหน่งเริ่มต้น")
        reset_pos.triggered.connect(self._move_to_default_position)

        clear_chat = menu.addAction("🧹 ล้างประวัติสนทนา")
        clear_chat.triggered.connect(lambda: self.state_label_text.emit("clear_chat"))

        menu.addSeparator()

        autostart_act = menu.addAction("⚙️ เริ่มทำงานพร้อม Windows")
        autostart_act.setCheckable(True)
        autostart_act.setChecked(self._is_autostart_on())
        autostart_act.triggered.connect(self._toggle_autostart)

        menu.addSeparator()

        quit_action = menu.addAction("❌ ปิดราฟาเอล")
        quit_action.triggered.connect(QApplication.quit)

        menu.exec(event.globalPosition().toPoint())

    # ─── System Tray Methods ───

    def _init_system_tray(self) -> None:
        """สร้างไอคอน System Tray ตรงมุมขวาล่างของ Taskbar"""
        self._tray_icon = QSystemTrayIcon(self)
        self._update_tray_icon()

        tray_menu = QMenu()
        tray_menu.setStyleSheet(self._get_menu_stylesheet())

        toggle_act = tray_menu.addAction("👁️ ซ่อน / แสดงวงเวทย์")
        toggle_act.triggered.connect(self._toggle_visibility)

        theme_menu = tray_menu.addMenu("🎨 เปลี่ยนธีมสี")
        for k, data in THEMES.items():
            act = theme_menu.addAction(f"● {data['name']}")
            act.triggered.connect(lambda checked=False, tk=k: self.set_theme(tk))

        tray_menu.addSeparator()

        clear_act = tray_menu.addAction("🧹 ล้างประวัติสนทนา")
        clear_act.triggered.connect(lambda: self.state_label_text.emit("clear_chat"))

        autostart_act = tray_menu.addAction("⚙️ เริ่มทำงานพร้อม Windows")
        autostart_act.setCheckable(True)
        autostart_act.setChecked(self._is_autostart_on())
        autostart_act.triggered.connect(self._toggle_autostart)

        tray_menu.addSeparator()

        quit_act = tray_menu.addAction("❌ ปิดราฟาเอล")
        quit_act.triggered.connect(QApplication.quit)

        self._tray_icon.setContextMenu(tray_menu)
        self._tray_icon.activated.connect(self._on_tray_activated)
        self._tray_icon.show()

    def _update_tray_icon(self) -> None:
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(self._color_primary, 3))
        painter.setBrush(QBrush(QColor(24, 14, 4, 210)))
        painter.drawEllipse(3, 3, 26, 26)
        painter.setPen(QPen(self._color_accent, 2))
        painter.drawEllipse(9, 9, 14, 14)
        painter.end()
        self._tray_icon.setIcon(QIcon(pixmap))
        self._tray_icon.setToolTip("ราฟาเอล (Raphael Desktop AI)")

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._toggle_visibility()

    def _toggle_visibility(self) -> None:
        if self.isVisible():
            self.hide()
        else:
            self.show()

    def _is_autostart_on(self) -> bool:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ) as key:
                winreg.QueryValueEx(key, "TheGreatSageRaphael")
                return True
        except Exception:
            return False

    def _toggle_autostart(self, enable: bool) -> None:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE) as key:
                if enable:
                    cmd = f'"{sys.executable}" "{Path(__file__).parent / "main.py"}"'
                    winreg.SetValueEx(key, "TheGreatSageRaphael", 0, winreg.REG_SZ, cmd)
                    logger.info("Windows autostart enabled")
                else:
                    try:
                        winreg.DeleteValue(key, "TheGreatSageRaphael")
                    except FileNotFoundError:
                        pass
                    logger.info("Windows autostart disabled")
        except Exception as e:
            logger.warning("Failed to toggle autostart: %s", e)
