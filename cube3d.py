import itertools
import math

from PySide6.QtCore import (
    Qt, QPointF, QRectF,
    QTimer, QElapsedTimer, Signal,
)
from PySide6.QtGui import (
    QColor, QPainter, QPen, QPolygonF, QFont,
    QQuaternion, QVector3D,
)
from PySide6.QtWidgets import QWidget


COLORS = {
    "W": "#F8FAFC",
    "Y": "#FACC15",
    "B": "#2563EB",
    "G": "#16A34A",
    "R": "#DC2626",
    "O": "#F97316",
}

# 각 면의 바깥 방향 / 화면 오른쪽 / 화면 위쪽
BASES = {
    "F": ((0, 0, 1), (1, 0, 0), (0, 1, 0)),
    "R": ((1, 0, 0), (0, 0, -1), (0, 1, 0)),
    "B": ((0, 0, -1), (-1, 0, 0), (0, 1, 0)),
    "L": ((-1, 0, 0), (0, 0, 1), (0, 1, 0)),
    "U": ((0, 1, 0), (1, 0, 0), (0, 0, -1)),
    "D": ((0, -1, 0), (1, 0, 0), (0, 0, 1)),
}


def add(a, b):
    return tuple(x + y for x, y in zip(a, b))


def scale(vector, amount):
    return tuple(value * amount for value in vector)


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def cross(a, b):
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def normalize(vector):
    length = math.sqrt(dot(vector, vector))
    return scale(vector, 1 / length)


def rotate(vector, axis, angle):
    cosine = math.cos(angle)
    sine = math.sin(angle)

    return add(
        add(
            scale(vector, cosine),
            scale(cross(axis, vector), sine),
        ),
        scale(
            axis,
            dot(axis, vector) * (1 - cosine),
        ),
    )


def orientation_quaternion(camera, up_hint):
    right = normalize(cross(up_hint, camera))
    up = normalize(cross(camera, right))
    return QQuaternion.fromAxes(
        QVector3D(*right),
        QVector3D(*up),
        QVector3D(*camera),
    ).normalized()


def vector_from_qt(vector):
    return (vector.x(), vector.y(), vector.z())


class Cube3D(QWidget):
    animation_finished = Signal()
    camera_focus_finished = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setMinimumSize(400, 330)

        centers = {
            "F": "W", "R": "G", "B": "Y",
            "L": "B", "U": "R", "D": "O",
        }
        self.faces = {
            face: [color] * 9
            for face, color in centers.items()
        }

        self.active_face = None
        self.move = None
        self.fraction = 0.0
        self.duration = 1800
        self.animation_elapsed = 0.0
        self.last_animation_tick = 0

        self.clock = QElapsedTimer()
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.setInterval(8)
        self.timer.timeout.connect(self.tick)

        self.camera = normalize((4.3, 3.4, 6.0))
        self.up_hint = (0, 1, 0)
        self.zoom = 1.0
        self.drag_position = None
        self.animation_speed = 1.0
        self.hint_move = None

        self.camera_clock = QElapsedTimer()
        self.camera_timer = QTimer(self)
        self.camera_timer.timeout.connect(self.tick_camera_focus)
        self.camera_start = self.camera
        self.camera_target = self.camera
        self.up_start = self.up_hint
        self.up_target = self.up_hint
        self.camera_start_orientation = orientation_quaternion(
            self.camera, self.up_hint
        )
        self.camera_target_orientation = self.camera_start_orientation
        self.camera_duration = 850
        self.camera_elapsed = 0.0
        self.last_camera_tick = 0
        self.camera_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.camera_timer.setInterval(8)

        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def stop_animation(self):
        self.timer.stop()
        self.camera_timer.stop()
        self.move = None
        self.fraction = 0.0

    def set_state(self, faces, active_face=None, hint_move=None):
        self.stop_animation()
        self.faces = {
            face: list(values)
            for face, values in faces.items()
        } if faces is not None else None
        self.active_face = active_face
        self.hint_move = hint_move
        self.update()

    def reset_camera(self):
        self.camera_timer.stop()
        self.camera = normalize((4.3, 3.4, 6.0))
        self.up_hint = (0, 1, 0)
        self.zoom = 1.0
        self.update()

    def set_animation_speed(self, multiplier):
        self.animation_speed = max(0.5, min(2.0, float(multiplier)))

    def focus_face(self, face, animate=True, duration=850):
        normal, right, up = BASES[face]
        self.active_face = face
        target = normalize(
            add(
                normal,
                add(
                    scale(right, 0.42),
                    scale(up, 0.36),
                ),
            )
        )
        self.zoom = 1.0

        if not animate:
            self.camera_timer.stop()
            self.camera = target
            self.up_hint = up
            self.update()
            self.camera_focus_finished.emit()
            return

        self.camera_start = self.camera
        self.camera_target = target
        self.up_start = self.up_hint
        self.up_target = up
        self.camera_start_orientation = orientation_quaternion(
            self.camera_start, self.up_start
        )
        self.camera_target_orientation = orientation_quaternion(
            self.camera_target, self.up_target
        )
        self.camera_duration = max(850, int(duration))

        orientation_dot = sum(
            first * second
            for first, second in zip(
                (
                    self.camera_start_orientation.scalar(),
                    self.camera_start_orientation.x(),
                    self.camera_start_orientation.y(),
                    self.camera_start_orientation.z(),
                ),
                (
                    self.camera_target_orientation.scalar(),
                    self.camera_target_orientation.x(),
                    self.camera_target_orientation.y(),
                    self.camera_target_orientation.z(),
                ),
            )
        )
        if abs(orientation_dot) > 0.999999:
            self.camera = target
            self.up_hint = up
            self.update()
            self.camera_focus_finished.emit()
            return

        self.camera_clock.start()
        self.camera_elapsed = 0.0
        self.last_camera_tick = 0
        self.camera_timer.start()
        self.update()

    def tick_camera_focus(self):
        elapsed = self.camera_clock.elapsed()
        self.camera_elapsed += min(
            max(0, elapsed - self.last_camera_tick),
            16,
        )
        self.last_camera_tick = elapsed
        fraction = min(
            1.0,
            self.camera_elapsed / self.camera_duration,
        )
        eased = fraction * fraction * (3 - 2 * fraction)
        orientation = QQuaternion.slerp(
            self.camera_start_orientation,
            self.camera_target_orientation,
            eased,
        ).normalized()
        self.camera = vector_from_qt(
            orientation.rotatedVector(QVector3D(0, 0, 1))
        )
        self.up_hint = vector_from_qt(
            orientation.rotatedVector(QVector3D(0, 1, 0))
        )
        self.update()

        if fraction >= 1.0:
            self.camera_timer.stop()
            self.camera = self.camera_target
            self.up_hint = self.up_target
            self.camera_focus_finished.emit()

    def camera_basis(self):
        right = normalize(cross(self.up_hint, self.camera))
        up = normalize(cross(self.camera, right))
        return right, up

    def animate(self, faces, move, duration=1800):
        self.set_state(faces, move[0], move)
        self.move = move
        self.duration = max(1, int(duration / self.animation_speed))
        self.fraction = 0.0
        self.animation_elapsed = 0.0
        self.last_animation_tick = 0

        self.clock.start()
        self.timer.start()
        self.update()

    def tick(self):
        elapsed = self.clock.elapsed()
        self.animation_elapsed += min(
            max(0, elapsed - self.last_animation_tick),
            16,
        )
        self.last_animation_tick = elapsed
        self.fraction = min(
            1.0,
            self.animation_elapsed / self.duration,
        )
        self.update()

        if self.fraction >= 1.0:
            self.timer.stop()
            self.animation_finished.emit()

    def transform(self, vector, moving):
        if not moving:
            return vector

        suffix = self.move[1:]
        final_angle = {
            "": -math.pi / 2,
            "'": math.pi / 2,
            "2": -math.pi,
        }[suffix]

        # 처음과 끝에서 부드럽게 움직입니다.
        t = self.fraction
        smooth = t * t * (3 - 2 * t)

        return rotate(
            vector,
            BASES[self.move[0]][0],
            final_angle * smooth,
        )

    def make_surfaces(self):
        if self.faces is None:
            return []

        if self.faces is None:
            return []

        surfaces = []

        for cubie in itertools.product(
            (-1, 0, 1), repeat=3
        ):
            if cubie == (0, 0, 0):
                continue

            moving = bool(
                self.move
                and dot(
                    cubie,
                    BASES[self.move[0]][0],
                ) > 0.5
            )
            indicated_move = self.move or self.hint_move
            indicated_normal = (
                BASES[indicated_move[0]][0]
                if indicated_move else None
            )
            indicated_layer = bool(
                indicated_move
                and dot(cubie, indicated_normal) > 0.5
            )

            for face, (normal, right, up) in BASES.items():
                center = add(
                    cubie,
                    scale(normal, 0.472),
                )

                vertices = [
                    add(
                        center,
                        add(
                            scale(right, x * 0.472),
                            scale(up, y * 0.472),
                        ),
                    )
                    for x, y in (
                        (-1, -1), (1, -1),
                        (1, 1), (-1, 1),
                    )
                ]

                surfaces.append((
                    self.transform(center, moving),
                    self.transform(normal, moving),
                    [
                        self.transform(v, moving)
                        for v in vertices
                    ],
                    None,
                    False,
                    None,
                    None,
                ))

                # 외부에 있는 면에만 스티커를 붙입니다.
                if dot(cubie, normal) != 1:
                    continue

                column = int(dot(cubie, right)) + 1
                row = 1 - int(dot(cubie, up))
                index = row * 3 + column

                center = add(
                    cubie,
                    scale(normal, 0.480),
                )

                vertices = [
                    add(
                        center,
                        add(
                            scale(right, x * 0.397),
                            scale(up, y * 0.397),
                        ),
                    )
                    for x, y in (
                        (-1, -1), (1, -1),
                        (1, 1), (-1, 1),
                    )
                ]

                highlighted = bool(
                    self.active_face
                    and dot(
                        cubie,
                        BASES[self.active_face][0],
                    ) > 0.5
                )

                surfaces.append((
                    self.transform(center, moving),
                    self.transform(normal, moving),
                    [
                        self.transform(v, moving)
                        for v in vertices
                    ],
                    self.faces[face][index],
                    highlighted,
                    face if index == 4 else None,
                    self._arrow_direction(
                        cubie,
                        normal,
                        indicated_move,
                        indicated_layer,
                        moving,
                    ),
                ))

        return surfaces

    def _arrow_direction(
        self, cubie, sticker_normal, move, in_layer, moving
    ):
        """Direction tangent to each visible side sticker of the turn layer."""
        if not move or not in_layer:
            return None

        axis = BASES[move[0]][0]
        if abs(dot(sticker_normal, axis)) > 0.5:
            return None

        sign = 1 if move.endswith("'") else -1
        motion = scale(cross(axis, cubie), sign)
        tangent = add(
            motion,
            scale(sticker_normal, -dot(motion, sticker_normal)),
        )
        length = math.sqrt(dot(tangent, tangent))
        if length < 1e-8:
            return None

        direction = scale(tangent, 1 / length)
        return self.transform(direction, moving)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(
            QPainter.RenderHint.Antialiasing
        )
        painter.fillRect(
            self.rect(), QColor("#F8FAFC")
        )

        right, up = self.camera_basis()
        focal = (
            min(self.width(), self.height())
            * 1.68 * self.zoom
        )
        cx = self.width() / 2
        cy = self.height() / 2
        distance = 8.7

        def project(point):
            depth = distance - dot(point, self.camera)

            return QPointF(
                cx + focal * dot(point, right) / depth,
                cy - focal * dot(point, up) / depth,
            )

        eye = scale(self.camera, distance)
        visible = []

        for surface in self.make_surfaces():
            center, normal, vertices, color, active, letter, arrow = surface

            toward_eye = add(eye, scale(center, -1))

            if dot(normal, toward_eye) <= 0.001:
                continue

            depth = distance - dot(center, self.camera)
            visible.append((depth, surface))

        # 먼 면부터 그려 앞면이 뒤쪽을 가리게 합니다.
        visible.sort(
            key=lambda item: item[0],
            reverse=True,
        )

        for _, surface in visible:
            center, normal, vertices, color, active, letter, arrow = surface

            polygon = QPolygonF([
                project(vertex)
                for vertex in vertices
            ])

            if color is None:
                painter.setBrush(QColor("#202733"))
                painter.setPen(
                    QPen(QColor("#0F172A"), 0.8)
                )
            else:
                painter.setBrush(
                    QColor(COLORS.get(color, "#CBD5E1"))
                )
                painter.setPen(
                    QPen(
                        QColor(
                            "#EAB308" if active
                            else "#0F172A"
                        ),
                        2.5 if active else 1.1,
                    )
                )

            painter.drawPolygon(polygon)

            if arrow is not None:
                self.draw_turn_arrow(
                    painter,
                    center,
                    arrow,
                    project,
                )

            if letter:
                point = project(center)

                text_color = (
                    "#172033"
                    if color in ("W", "Y", "O")
                    else "#FFFFFF"
                )
                painter.setPen(QColor(text_color))
                painter.setFont(
                    QFont(
                        "Malgun Gothic",
                        16,
                        QFont.Weight.Bold,
                    )
                )
                painter.drawText(
                    QRectF(
                        point.x() - 25,
                        point.y() - 20,
                        50, 40,
                    ),
                    Qt.AlignmentFlag.AlignCenter,
                    letter,
                )

        painter.setPen(QColor("#64748B"))
        painter.setFont(QFont("Malgun Gothic", 10))
        painter.drawText(
            QRectF(
                5,
                self.height() - 27,
                self.width() - 10,
                22,
            ),
            Qt.AlignmentFlag.AlignCenter,
            "드래그: 시점 변경 · 휠: 확대/축소",
        )
        painter.end()

    @staticmethod
    def draw_turn_arrow(painter, center, direction, project):
        """Draw a cyan arrow with a heavy dark outline on a sticker."""
        start = project(add(center, scale(direction, -0.205)))
        tip = project(add(center, scale(direction, 0.205)))
        dx = tip.x() - start.x()
        dy = tip.y() - start.y()
        length = math.hypot(dx, dy)
        if length < 1:
            return

        ux, uy = dx / length, dy / length
        px, py = -uy, ux
        head_length = min(10.0, length * 0.36)
        head_width = min(7.5, length * 0.27)
        base_x = tip.x() - ux * head_length
        base_y = tip.y() - uy * head_length
        head = QPolygonF([
            tip,
            QPointF(
                base_x + px * head_width,
                base_y + py * head_width,
            ),
            QPointF(
                base_x - px * head_width,
                base_y - py * head_width,
            ),
        ])

        painter.save()
        painter.setPen(QPen(
            QColor("#111827"),
            6.0,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
            Qt.PenJoinStyle.RoundJoin,
        ))
        painter.drawLine(start, QPointF(base_x, base_y))
        painter.setPen(QPen(QColor("#111827"), 2.4))
        painter.setBrush(QColor("#22D3EE"))
        painter.drawPolygon(head)
        painter.setPen(QPen(
            QColor("#22D3EE"),
            3.2,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
            Qt.PenJoinStyle.RoundJoin,
        ))
        painter.drawLine(start, QPointF(base_x, base_y))
        painter.restore()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_position = event.position()
            self.setCursor(
                Qt.CursorShape.ClosedHandCursor
            )

    def mouseMoveEvent(self, event):
        if self.drag_position is None:
            return

        delta = event.position() - self.drag_position
        self.drag_position = event.position()

        world_up = (0, 1, 0)
        yaw = -delta.x() * 0.008
        camera_after_yaw = normalize(
            rotate(self.camera, world_up, yaw)
        )
        up_after_yaw = normalize(
            rotate(self.up_hint, world_up, yaw)
        )

        current_pitch = math.asin(
            max(-1.0, min(1.0, camera_after_yaw[1]))
        )
        pitch_limit = math.pi / 2 - math.radians(0.5)
        next_pitch = max(
            -pitch_limit,
            min(pitch_limit, current_pitch - delta.y() * 0.008),
        )
        right = normalize(cross(world_up, camera_after_yaw))
        pitch_delta = next_pitch - current_pitch
        self.camera = normalize(
            rotate(camera_after_yaw, right, -pitch_delta)
        )
        self.up_hint = normalize(
            rotate(up_after_yaw, right, -pitch_delta)
        )
        self.update()

    def mouseReleaseEvent(self, event):
        self.drag_position = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def wheelEvent(self, event):
        multiplier = (
            1.12
            if event.angleDelta().y() > 0
            else 1 / 1.12
        )
        self.zoom = max(
            0.65,
            min(1.55, self.zoom * multiplier),
        )
        self.update()
