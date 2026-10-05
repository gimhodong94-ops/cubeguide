"""A perspective 3D Rubik's cube widget with animated layer turns."""

import itertools
import math

from PySide6.QtCore import QPointF, QRectF, QElapsedTimer, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

from cube_engine import apply_move_to_faces


_COLORS = {
    "W": "#F8FAFC",
    "Y": "#FACC15",
    "B": "#2563EB",
    "G": "#16A34A",
    "R": "#DC2626",
    "O": "#F97316",
}

# Face normal, right, and up directions in cube coordinates.
_BASES = {
    "F": ((0, 0, 1), (1, 0, 0), (0, 1, 0)),
    "R": ((1, 0, 0), (0, 0, -1), (0, 1, 0)),
    "B": ((0, 0, -1), (-1, 0, 0), (0, 1, 0)),
    "L": ((-1, 0, 0), (0, 0, 1), (0, 1, 0)),
    "U": ((0, 1, 0), (1, 0, 0), (0, 0, -1)),
    "D": ((0, -1, 0), (1, 0, 0), (0, 0, 1)),
}


def _add(a, b):
    return tuple(x + y for x, y in zip(a, b))


def _scale(vector, amount):
    return tuple(value * amount for value in vector)


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _cross(a, b):
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _normalize(vector):
    length = math.sqrt(_dot(vector, vector))
    if length == 0:
        raise ValueError("Cannot normalize a zero-length vector.")
    return _scale(vector, 1 / length)


def _rotate(vector, axis, angle):
    cosine = math.cos(angle)
    sine = math.sin(angle)
    return _add(
        _add(
            _scale(vector, cosine),
            _scale(_cross(axis, vector), sine),
        ),
        _scale(axis, _dot(axis, vector) * (1 - cosine)),
    )


class Cube3D(QWidget):
    """Draw and animate a perspective Rubik's cube."""

    animation_finished = Signal()
    camera_focus_finished = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(400, 330)

        self._state = None
        self._active_face = None
        self._hint_move = None
        self._move = None
        self._animation_end = None
        self._fraction = 0.0
        self._fraction_start = 0.0
        self._duration = 1800

        self._clock = QElapsedTimer()
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._advance_animation)

        self._camera = _normalize((4.3, 3.4, 6.0))
        self._up_hint = (0, 1, 0)
        self._camera_yaw = math.atan2(self._camera[0], self._camera[2])
        self._camera_pitch = math.asin(self._camera[1])
        self._camera_roll = 0.0
        self._zoom = 1.0
        self._drag_position = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)

        self._camera_clock = QElapsedTimer()
        self._camera_timer = QTimer(self)
        self._camera_timer.setInterval(16)
        self._camera_timer.timeout.connect(self._advance_camera)
        self._camera_start = (self._camera_yaw, self._camera_pitch)
        self._camera_target = self._camera_start
        self._camera_roll_start = self._camera_roll
        self._camera_roll_target = self._camera_roll
        self._camera_duration = 850
        self._animation_speed = 1.0
        self._camera_motion_kind = None
        self._focus_interrupted = False

    def set_state(self, state, active_face=None, hint_move=None):
        """Set a faces mapping: F/R/B/L/U/D -> nine color letters each."""
        self.stop_animation()
        self._state = (
            {face: list(values) for face, values in state.items()}
            if state is not None
            else None
        )
        self._active_face = active_face
        self._hint_move = hint_move
        self.update()

    def set_animation_speed(self, multiplier):
        """Set animation playback speed from 0.5x to 2x."""
        new_speed = max(0.5, min(2.0, float(multiplier)))
        old_speed = self._animation_speed
        if math.isclose(new_speed, old_speed):
            return

        if self._camera_timer.isActive():
            elapsed = min(self._camera_duration, self._camera_clock.elapsed())
            progress = elapsed / self._camera_duration
            eased = progress * progress * (3 - 2 * progress)
            self._camera_yaw = self._camera_start[0] + (
                self._camera_target[0] - self._camera_start[0]
            ) * eased
            self._camera_pitch = self._camera_start[1] + (
                self._camera_target[1] - self._camera_start[1]
            ) * eased
            self._camera_roll = self._camera_roll_start + (
                self._camera_roll_target - self._camera_roll_start
            ) * eased
            self._camera_start = (self._camera_yaw, self._camera_pitch)
            self._camera_roll_start = self._camera_roll
            remaining = max(1, self._camera_duration - elapsed)
            self._camera_duration = max(1, int(remaining * old_speed / new_speed))
            self._camera_clock.start()

        if self._timer.isActive() and self._move:
            elapsed = min(self._duration, self._clock.elapsed())
            progress = elapsed / self._duration
            self._fraction = self._fraction_start + (
                1 - self._fraction_start
            ) * progress
            remaining = max(1, self._duration - elapsed)
            self._duration = max(1, int(remaining * old_speed / new_speed))
            self._fraction_start = self._fraction
            self._clock.start()

        self._animation_speed = new_speed
        self._sync_camera()
        self.update()

    def focus_face(self, face, animate=True, duration=850):
        """Aim at a face, easing the camera there without changing its roll."""
        normal, right, up = _BASES[face]
        self._active_face = face
        target = _normalize(
            _add(normal, _add(_scale(right, 0.42), _scale(up, 0.36)))
        )
        target_yaw = math.atan2(target[0], target[2])
        target_pitch = math.asin(max(-1.0, min(1.0, target[1])))

        if not animate:
            self._camera_timer.stop()
            self._camera_motion_kind = None
            self._focus_interrupted = False
            self._camera_yaw = target_yaw
            self._camera_pitch = target_pitch
            self._camera_roll_start = self._camera_roll
            self._camera_roll_target = self._camera_roll
            self._sync_camera()
            self.update()
            self.camera_focus_finished.emit()
            return

        self._camera_start = (self._camera_yaw, self._camera_pitch)
        yaw_delta = (target_yaw - self._camera_yaw + math.pi) % (2 * math.pi) - math.pi
        self._camera_target = (self._camera_yaw + yaw_delta, target_pitch)
        self._camera_roll_start = self._camera_roll
        self._camera_roll_target = self._camera_roll
        if abs(yaw_delta) < 0.005 and abs(target_pitch - self._camera_pitch) < 0.005:
            self._camera_timer.stop()
            self._camera_motion_kind = None
            self._focus_interrupted = False
            self._camera_yaw, self._camera_pitch = self._camera_target
            self._sync_camera()
            self.update()
            self.camera_focus_finished.emit()
            return

        self._focus_interrupted = False
        self._camera_motion_kind = "focus"
        self._camera_duration = max(
            1,
            int(duration / self._animation_speed),
        )
        self._camera_clock.start()
        self._camera_timer.start()
        self.update()

    def _sync_camera(self):
        cosine = math.cos(self._camera_pitch)
        self._camera = _normalize((
            math.sin(self._camera_yaw) * cosine,
            math.sin(self._camera_pitch),
            math.cos(self._camera_yaw) * cosine,
        ))
        self._up_hint = _normalize(
            _rotate((0, 1, 0), self._camera, self._camera_roll)
        )

    def _advance_camera(self):
        fraction = min(1.0, self._camera_clock.elapsed() / self._camera_duration)
        eased = fraction * fraction * (3 - 2 * fraction)
        self._camera_yaw = self._camera_start[0] + (
            self._camera_target[0] - self._camera_start[0]
        ) * eased
        self._camera_pitch = self._camera_start[1] + (
            self._camera_target[1] - self._camera_start[1]
        ) * eased
        self._camera_roll = self._camera_roll_start + (
            self._camera_roll_target - self._camera_roll_start
        ) * eased
        self._sync_camera()
        self.update()
        if fraction >= 1.0:
            self._camera_timer.stop()
            self._camera_yaw, self._camera_pitch = self._camera_target
            self._camera_roll = self._camera_roll_target
            self._sync_camera()
            self.update()
            motion_kind = self._camera_motion_kind
            self._camera_motion_kind = None
            if motion_kind == "focus":
                self.camera_focus_finished.emit()

    def rotate_roll(self, degrees):
        """Ease the image around the current viewing direction."""
        self._camera_start = (self._camera_yaw, self._camera_pitch)
        self._camera_target = self._camera_start
        self._camera_roll_start = self._camera_roll
        self._camera_roll_target = self._camera_roll + math.radians(degrees)
        self._camera_motion_kind = "roll"
        self._camera_duration = max(1, int(260 / self._animation_speed))
        self._camera_clock.start()
        self._camera_timer.start()
        self.update()

    def reset_camera(self):
        focus_was_active = self._camera_motion_kind == "focus"
        self._camera_timer.stop()
        self._camera_motion_kind = None
        self._focus_interrupted = False
        self._camera = _normalize((4.3, 3.4, 6.0))
        self._camera_yaw = math.atan2(self._camera[0], self._camera[2])
        self._camera_pitch = math.asin(self._camera[1])
        self._camera_roll = 0.0
        self._camera_roll_start = 0.0
        self._camera_roll_target = 0.0
        self._sync_camera()
        self._zoom = 1.0
        self.update()
        if focus_was_active:
            self.camera_focus_finished.emit()

    def stop_animation(self):
        self._timer.stop()
        self._move = None
        self._animation_end = None
        self._fraction = 0.0
        self._fraction_start = 0.0

    def animate(self, state, move, duration=1800):
        """Animate one layer turn and retain its resulting state."""
        if (
            not move
            or move[0] not in _BASES
            or move[1:] not in ("", "'", "2")
        ):
            raise ValueError(f"Invalid cube move: {move!r}")

        self.set_state(state, move[0], move)
        self._move = move
        self._animation_end = {
            face: values[:]
            for face, values in self._state.items()
        }
        apply_move_to_faces(self._animation_end, move)
        self._duration = max(1, int(duration / self._animation_speed))
        self._fraction = 0.0
        self._fraction_start = 0.0
        self._clock.start()
        self._timer.start()
        self.update()

    def _advance_animation(self):
        progress = min(1.0, self._clock.elapsed() / self._duration)
        self._fraction = self._fraction_start + (
            1 - self._fraction_start
        ) * progress
        self.update()

        if self._fraction >= 1.0:
            self._timer.stop()
            self._state = self._animation_end
            self._animation_end = None
            self._move = None
            self._fraction = 0.0
            self._fraction_start = 0.0
            self.update()
            self.animation_finished.emit()

    def _camera_basis(self):
        right = _normalize(_cross(self._up_hint, self._camera))
        up = _normalize(_cross(self._camera, right))
        return right, up

    def _transform(self, vector, moving):
        if not moving:
            return vector

        suffix = self._move[1:]
        angle = {
            "": -math.pi / 2,
            "'": math.pi / 2,
            "2": -math.pi,
        }[suffix]
        eased = self._fraction * self._fraction * (3 - 2 * self._fraction)
        axis = _BASES[self._move[0]][0]
        return _rotate(vector, axis, angle * eased)

    def _make_surfaces(self):
        surfaces = []

        for cubie in itertools.product((-1, 0, 1), repeat=3):
            if cubie == (0, 0, 0):
                continue

            indicated_move = self._move or self._hint_move
            indicated_face = indicated_move[0] if indicated_move else None
            in_indicated_layer = bool(
                indicated_face
                and _dot(cubie, _BASES[indicated_face][0]) > 0.5
            )
            moving = bool(
                self._move
                and _dot(cubie, _BASES[self._move[0]][0]) > 0.5
            )

            for face, (normal, right, up) in _BASES.items():
                center = _add(cubie, _scale(normal, 0.472))
                vertices = [
                    _add(
                        center,
                        _add(_scale(right, x * 0.472), _scale(up, y * 0.472)),
                    )
                    for x, y in (
                        (-1, -1), (1, -1), (1, 1), (-1, 1)
                    )
                ]
                surfaces.append((
                    self._transform(center, moving),
                    self._transform(normal, moving),
                    [self._transform(vertex, moving) for vertex in vertices],
                    None,
                    False,
                    None,
                    None,
                ))

                if _dot(cubie, normal) != 1:
                    continue

                column = int(_dot(cubie, right)) + 1
                row = 1 - int(_dot(cubie, up))
                index = row * 3 + column
                sticker_center = _add(cubie, _scale(normal, 0.480))
                sticker_vertices = [
                    _add(
                        sticker_center,
                        _add(_scale(right, x * 0.397), _scale(up, y * 0.397)),
                    )
                    for x, y in (
                        (-1, -1), (1, -1), (1, 1), (-1, 1)
                    )
                ]
                highlighted = bool(
                    self._active_face
                    and _dot(cubie, _BASES[self._active_face][0]) > 0.5
                )
                arrow_direction = None
                if in_indicated_layer and indicated_move and face != indicated_face:
                    axis = _BASES[indicated_face][0]
                    direction = _cross(axis, cubie)
                    if indicated_move[1:] != "'":
                        direction = _scale(direction, -1)
                    arrow_direction = self._transform(direction, moving)

                surfaces.append((
                    self._transform(sticker_center, moving),
                    self._transform(normal, moving),
                    [self._transform(vertex, moving) for vertex in sticker_vertices],
                    self._state[face][index],
                    highlighted,
                    face if index == 4 else None,
                    arrow_direction,
                ))

        return surfaces

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#EEF2F7"))

        if not self._state:
            painter.setPen(QColor("#475569"))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "큐브 상태를 입력하면\n3D 미리보기가 표시됩니다.",
            )
            painter.end()
            return

        right, up = self._camera_basis()
        focal = min(self.width(), self.height()) * 1.68 * self._zoom
        center_x = self.width() / 2
        center_y = self.height() / 2
        distance = 8.7

        def project(point):
            depth = distance - _dot(point, self._camera)
            return QPointF(
                center_x + focal * _dot(point, right) / depth,
                center_y - focal * _dot(point, up) / depth,
            )

        eye = _scale(self._camera, distance)
        visible = []
        for surface in self._make_surfaces():
            center, normal, vertices, color, active, letter, arrow_direction = surface
            toward_eye = _add(eye, _scale(center, -1))
            if _dot(normal, toward_eye) <= 0.001:
                continue

            depth = distance - _dot(center, self._camera)
            visible.append((depth, surface))

        visible.sort(key=lambda item: item[0], reverse=True)

        for _, surface in visible:
            center, normal, vertices, color, active, letter, arrow_direction = surface
            polygon = QPolygonF([project(vertex) for vertex in vertices])

            if color is None:
                painter.setBrush(QColor("#202733"))
                painter.setPen(QPen(QColor("#0F172A"), 0.8))
            else:
                painter.setBrush(QColor(_COLORS.get(color, "#CBD5E1")))
                painter.setPen(QPen(
                    QColor("#EAB308" if active else "#0F172A"),
                    2.8 if active else 1.2,
                ))
            painter.drawPolygon(polygon)

            if letter:
                label_color = (
                    "#172033" if color in ("W", "Y", "O") else "#FFFFFF"
                )
                painter.setPen(QColor(label_color))
                label_font = QFont("Malgun Gothic")
                label_font.setWeight(QFont.Weight.Bold)
                label_font.setPixelSize(max(14, int(focal * 0.045)))
                painter.setFont(label_font)
                metrics = QFontMetricsF(label_font)
                point = project(center)
                painter.drawText(
                    QPointF(
                        point.x() - metrics.horizontalAdvance(letter) / 2,
                        point.y() + (metrics.ascent() - metrics.descent()) / 2,
                    ),
                    letter,
                )

            if arrow_direction is not None:
                self._draw_turn_arrow(
                    painter,
                    center,
                    vertices,
                    arrow_direction,
                    project,
                )

        painter.setPen(QColor("#64748B"))
        painter.setFont(QFont("Malgun Gothic", 10))
        painter.drawText(
            QRectF(5, self.height() - 47, self.width() - 10, 18),
            Qt.AlignmentFlag.AlignCenter,
            "청록 화살표: 현재 회전 방향 · 멈춰 있을 때는 다음 동작",
        )
        painter.drawText(
            QRectF(5, self.height() - 27, self.width() - 10, 18),
            Qt.AlignmentFlag.AlignCenter,
            "드래그: 시점 이동  ·  휠: 확대/축소  ·  양옆 버튼: 화면 90° 회전",
        )
        painter.end()

    def _draw_turn_arrow(self, painter, center, vertices, direction, project):
        """Draw a high contrast motion arrow on one moving side sticker."""
        projected_center = project(center)
        projected_tip = project(_add(center, _scale(_normalize(direction), 0.2)))
        dx = projected_tip.x() - projected_center.x()
        dy = projected_tip.y() - projected_center.y()
        magnitude = math.hypot(dx, dy)
        if magnitude < 0.001:
            return

        unit = QPointF(dx / magnitude, dy / magnitude)
        bounds = QPolygonF([project(vertex) for vertex in vertices]).boundingRect()
        tile_size = min(bounds.width(), bounds.height())
        length = max(11.0, min(25.0, tile_size * 0.72))
        start = projected_center - unit * (length * 0.34)
        tip = projected_center + unit * (length * 0.66)
        head_length = min(7.5, length * 0.4)
        head_half_width = min(5.5, length * 0.29)
        head_base = tip - unit * head_length
        perpendicular = QPointF(-unit.y(), unit.x())
        head = QPolygonF([
            tip,
            head_base + perpendicular * head_half_width,
            head_base - perpendicular * head_half_width,
        ])

        painter.save()
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(
            QColor("#111827"),
            7.0,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
            Qt.PenJoinStyle.RoundJoin,
        ))
        painter.drawLine(start, head_base)
        painter.setPen(QPen(
            QColor("#22D3EE"),
            3.2,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
            Qt.PenJoinStyle.RoundJoin,
        ))
        painter.drawLine(start, head_base)
        painter.setBrush(QColor("#22D3EE"))
        painter.setPen(QPen(QColor("#111827"), 2.4))
        painter.drawPolygon(head)
        painter.restore()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_position = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        if self._drag_position is None:
            return

        if self._camera_motion_kind == "focus":
            self._focus_interrupted = True
        self._camera_timer.stop()
        self._camera_motion_kind = None
        delta = event.position() - self._drag_position
        self._drag_position = event.position()
        self._camera_yaw -= delta.x() * 0.008
        self._camera_pitch = max(
            math.radians(-85),
            min(math.radians(85), self._camera_pitch + delta.y() * 0.008),
        )
        self._sync_camera()
        self.update()

    def mouseReleaseEvent(self, event):
        self._drag_position = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        if self._focus_interrupted:
            self._focus_interrupted = False
            self.camera_focus_finished.emit()

    def wheelEvent(self, event):
        multiplier = 1.12 if event.angleDelta().y() > 0 else 1 / 1.12
        self._zoom = max(0.65, min(1.55, self._zoom * multiplier))
        self.update()
