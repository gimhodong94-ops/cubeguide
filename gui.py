import sys
from collections import Counter

import itertools
import math

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QThread, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF, QShortcut, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QMainWindow,
    QWidget,
    QLabel,
    QPushButton,
    QCheckBox,
    QGridLayout,
    QHBoxLayout,
    QBoxLayout,
    QVBoxLayout,
    QTabWidget,
    QMessageBox,
    QSizePolicy,
    QScrollArea,
    QFrame,
)

from cube_engine import (
    build_kociemba_string,
    safe_solve_with_kociemba,
    apply_move_to_faces,
)


FACE_ORDER = ("F", "R", "B", "L", "U", "D")

FACE_NAMES = {
    "F": "앞면",
    "R": "오른쪽 면",
    "B": "뒷면",
    "L": "왼쪽 면",
    "U": "윗면",
    "D": "아랫면",
}

COLOR_NAMES = {
    "W": "흰색",
    "Y": "노란색",
    "B": "파란색",
    "G": "초록색",
    "R": "빨간색",
    "O": "주황색",
}

COLOR_HEX = {
    "W": "#F8FAFC",
    "Y": "#FACC15",
    "B": "#2563EB",
    "G": "#16A34A",
    "R": "#DC2626",
    "O": "#F97316",
}

# 예시 중앙 색입니다.
# 실물 큐브가 다르면 화면에서 중앙 색을 수정하세요.
CENTERS = {
    "F": "W",
    "R": "G",
    "B": "Y",
    "L": "B",
    "U": "R",
    "D": "O",
}

# 각 면을 바깥에서 직접 바라본 그림의 위쪽 이웃
TOP_NEIGHBOR = {
    "F": "U",
    "R": "U",
    "B": "U",
    "L": "U",
    "U": "B",
    "D": "F",
}

NET_POSITIONS = {
    "U": (0, 1),
    "L": (1, 0),
    "F": (1, 1),
    "R": (1, 2),
    "B": (1, 3),
    "D": (2, 1),
}

# A face's outward normal, right direction, and up direction. These bases let
# the input helper recognize which stickers belong to each edge or corner.
FACE_BASES = {
    "F": ((0, 0, 1), (1, 0, 0), (0, 1, 0)),
    "R": ((1, 0, 0), (0, 0, -1), (0, 1, 0)),
    "B": ((0, 0, -1), (-1, 0, 0), (0, 1, 0)),
    "L": ((-1, 0, 0), (0, 0, 1), (0, 1, 0)),
    "U": ((0, 1, 0), (1, 0, 0), (0, 0, -1)),
    "D": ((0, -1, 0), (1, 0, 0), (0, 0, 1)),
}


def cubie_sticker_groups():
    groups = {}
    for face, (normal, right, up) in FACE_BASES.items():
        for index in range(9):
            row, column = divmod(index, 3)
            position = tuple(
                normal[axis]
                + right[axis] * (column - 1)
                + up[axis] * (1 - row)
                for axis in range(3)
            )
            groups.setdefault(position, []).append((face, index))
    return groups


CUBIE_STICKERS = cubie_sticker_groups()


class StickerButton(QPushButton):
    """Sticker button with a right-drag gesture for the radial color picker."""

    radial_started = Signal(object, object)
    radial_moved = Signal(object)
    radial_finished = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._radial_drag = False

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self._radial_drag = True
            self.radial_started.emit(self, event.globalPosition().toPoint())
            self.grabMouse()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._radial_drag:
            self.radial_moved.emit(event.globalPosition().toPoint())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._radial_drag and event.button() == Qt.MouseButton.RightButton:
            self.radial_finished.emit(event.globalPosition().toPoint())
            self._radial_drag = False
            self.releaseMouse()
            event.accept()
            return
        super().mouseReleaseEvent(event)


class RadialColorPicker(QWidget):
    """Translucent six-color picker centered on a sticker under the cursor."""

    RADIUS = 108

    def __init__(self, parent=None):
        super().__init__(
            parent,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedSize(self.RADIUS * 2, self.RADIUS * 2)
        self._center_global = QPoint()
        self._hovered = None

    def open_at(self, global_position):
        self._center_global = QPoint(global_position)
        self._hovered = None
        origin = self._center_global - QPoint(self.RADIUS, self.RADIUS)
        self.move(origin)
        self.show()
        self.raise_()
        self.update()

    def color_at(self, global_position):
        dx = global_position.x() - self._center_global.x()
        dy = global_position.y() - self._center_global.y()
        distance = math.hypot(dx, dy)
        if distance < 18 or distance > self.RADIUS - 8:
            return None
        degrees = math.degrees(math.atan2(dx, -dy)) % 360
        sector = int(degrees // 60) % 6
        return tuple(COLOR_NAMES)[sector]

    def set_pointer(self, global_position):
        color = self.color_at(global_position)
        if color != self._hovered:
            self._hovered = color
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        center = QPoint(self.RADIUS, self.RADIUS)
        radius = self.RADIUS - 8
        colors = tuple(COLOR_NAMES)
        short_names = {"W": "흰", "Y": "노", "B": "파", "G": "초", "R": "빨", "O": "주"}

        for sector, color in enumerate(colors):
            points = [QPointF(center)]
            for degree in range(sector * 60, (sector + 1) * 60 + 1, 5):
                radians = math.radians(degree)
                points.append(QPointF(
                    center.x() + radius * math.sin(radians),
                    center.y() - radius * math.cos(radians),
                ))
            polygon = QPolygonF(points)
            fill = QColor(COLOR_HEX[color])
            fill.setAlpha(205 if color == self._hovered else 145)
            painter.setBrush(fill)
            painter.setPen(QPen(QColor("#FFFFFF"), 2.2))
            painter.drawPolygon(polygon)

            label_angle = math.radians(sector * 60 + 30)
            label_radius = radius * 0.68
            label_x = center.x() + label_radius * math.sin(label_angle)
            label_y = center.y() - label_radius * math.cos(label_angle)
            painter.setPen(QColor("#172033" if color in ("W", "Y", "O") else "#FFFFFF"))
            painter.drawText(
                QRectF(label_x - 18, label_y - 17, 36, 34),
                Qt.AlignmentFlag.AlignCenter,
                short_names[color],
            )

        center_fill = QColor("#FFFFFF")
        center_fill.setAlpha(235)
        painter.setBrush(center_fill)
        painter.setPen(QPen(QColor("#64748B"), 1.5))
        painter.drawEllipse(center, 15, 15)
        painter.end()


def copy_faces(faces):
    return {face: faces[face][:] for face in FACE_ORDER}


def sticker_style(color, highlighted=False, size=None):
    background = COLOR_HEX.get(color, "#E2E8F0")
    foreground = (
        "#172033"
        if color in (None, "W", "Y", "O")
        else "#FFFFFF"
    )
    border = (
        "3px solid #172033"
        if highlighted
        else "1px solid #94A3B8"
    )

    dimensions = (
        f"min-width: {size}px; max-width: {size}px;"
        f"min-height: {size}px; max-height: {size}px;"
        if size is not None
        else ""
    )
    return (
        f"background: {background};"
        f"color: {foreground};"
        f"border: {border};"
        "border-radius: 6px;"
        "padding: 0;"
        "font-weight: bold;"
        f"{dimensions}"
    )


def configure_application_style(app):
    app.setStyleSheet("""
        QWidget {
            color: #172033;
            font-family: "Malgun Gothic";
            font-size: 13px;
        }
        QMainWindow {
            background: #F1F5F9;
        }
        QTabWidget::pane {
            background: #F8FAFC;
            border: 1px solid #D9E2EF;
            border-top: 0;
        }
        QTabBar::tab {
            color: #64748B;
            background: #E8EEF6;
            border: 0;
            border-top-left-radius: 8px;
            border-top-right-radius: 8px;
            padding: 12px 22px;
            margin-right: 4px;
        }
        QTabBar::tab:selected {
            color: #1D4ED8;
            background: #FFFFFF;
            font-weight: 700;
        }
        QPushButton {
            color: #243247;
            background: #FFFFFF;
            border: 1px solid #CBD5E1;
            border-radius: 8px;
            padding: 8px 12px;
            min-height: 20px;
        }
        QPushButton:hover {
            background: #F1F5F9;
            border-color: #94A3B8;
        }
        QPushButton:pressed {
            background: #E2E8F0;
        }
        QPushButton:disabled {
            color: #94A3B8;
            background: #F1F5F9;
            border-color: #E2E8F0;
        }
        QCheckBox {
            spacing: 8px;
            padding: 4px 0;
        }
        QCheckBox::indicator {
            width: 17px;
            height: 17px;
        }
        QScrollArea {
            background: transparent;
            border: 0;
        }
        QFrame#card {
            background: #FFFFFF;
            border: 1px solid #E2E8F0;
            border-radius: 12px;
        }
        QLabel#pageTitle {
            color: #0F172A;
            font-size: 21px;
            font-weight: 700;
        }
        QLabel#mutedText {
            color: #64748B;
        }
        QLabel#stepTitle {
            color: #1D4ED8;
            font-size: 19px;
            font-weight: 700;
        }
    """)


class SolverThread(QThread):
    """해법 계산을 GUI와 별도로 실행합니다."""

    def __init__(self, cube_string, parent=None):
        super().__init__(parent)
        self.cube_string = cube_string
        self.solution = ""
        self.error = ""

    def run(self):
        try:
            self.solution = safe_solve_with_kociemba(
                self.cube_string
            )
        except Exception as exc:
            self.error = str(exc)


class CubeGuide(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("3×3 큐브 가이드")
        self.setMinimumSize(840, 620)
        self.resize(1180, 820)

        self.faces = {
            face: [
                CENTERS[face] if index == 4 else None
                for index in range(9)
            ]
            for face in FACE_ORDER
        }

        self.selected_color = "W"
        self.worker = None
        self.moves = []
        self.states = []
        self.step = 0
        self.auto_filled_stickers = set()
        self.color_buttons = {}
        self.radial_picker = RadialColorPicker(self)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.setCentralWidget(self.tabs)

        self.make_input_page()
        self.make_guide_page()

        self.space_shortcut = QShortcut(QKeySequence("Space"), self)
        self.space_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self.space_shortcut.activated.connect(self.advance_with_space)

        self.tabs.setTabEnabled(1, False)
        self.update_input()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "input_content_layout"):
            direction = (
                QBoxLayout.Direction.LeftToRight
                if event.size().width() >= 960
                else QBoxLayout.Direction.TopToBottom
            )
            self.input_content_layout.setDirection(direction)

    def make_net(self, editable):
        panel = QWidget()
        layout = QGridLayout(panel)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(8)
        panel.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        buttons = {}

        for face in FACE_ORDER:
            face_panel = QWidget()
            face_layout = QVBoxLayout(face_panel)
            face_layout.setContentsMargins(2, 2, 2, 2)
            face_layout.setSpacing(7)

            title = QLabel(f"{FACE_NAMES[face]} · {face}")
            title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            title.setStyleSheet("font-size: 12px; font-weight: 700; color: #475569;")
            face_layout.addWidget(title)

            grid = QGridLayout()
            grid.setSpacing(5)

            for index in range(9):
                button = StickerButton() if editable else QPushButton()
                button.setFixedSize(40, 40)

                if editable:
                    button.radial_started.connect(self.begin_radial_color)
                    button.radial_moved.connect(self.move_radial_color)
                    button.radial_finished.connect(
                        lambda position, b=button: self.finish_radial_color(b, position)
                    )
                    button.clicked.connect(
                        lambda checked=False,
                        f=face,
                        i=index: self.paint_sticker(f, i)
                    )
                    button.setProperty("face", face)
                    button.setProperty("sticker_index", index)

                grid.addWidget(
                    button,
                    index // 3,
                    index % 3,
                )
                buttons[(face, index)] = button

            face_layout.addLayout(grid)
            face_panel.setFixedWidth(140)

            row, column = NET_POSITIONS[face]
            layout.addWidget(face_panel, row, column)

        return panel, buttons

    def make_input_page(self):
        self.input_page = QWidget()
        self.input_page.setObjectName("appPage")
        layout = QVBoxLayout(self.input_page)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(7)

        explanation = QLabel(
            "① 실제 큐브의 앞면 F와 윗면 U를 정하세요. 각 면은 바깥에서 직접 본 모습으로 입력합니다.\n"
            "② 색을 선택해 칸을 클릭하거나, 칸에서 우클릭한 채 원하는 색 방향으로 드래그하세요."
        )
        explanation.setWordWrap(True)
        explanation.setObjectName("mutedText")
        explanation.setStyleSheet("line-height: 145%;")
        heading = QLabel("큐브 색상 입력")
        heading.setObjectName("pageTitle")
        layout.addWidget(heading)
        layout.addWidget(explanation)

        palette_card = QFrame()
        palette_card.setObjectName("card")
        palette = QHBoxLayout(palette_card)
        palette.setContentsMargins(10, 7, 10, 7)
        palette.setSpacing(7)
        self.palette_group = QButtonGroup(self)
        self.palette_group.setExclusive(True)

        for color, name in COLOR_NAMES.items():
            button = QPushButton(f"{color}  {name}")
            button.setCheckable(True)
            button.setMinimumHeight(38)
            button.setStyleSheet(sticker_style(color, size=58))
            self.palette_group.addButton(button)
            self.color_buttons[color] = button

            button.clicked.connect(
                lambda checked=False,
                c=color: self.select_color(c)
            )
            palette.addWidget(button)

        erase_button = QPushButton("지우개")
        erase_button.setCheckable(True)
        self.palette_group.addButton(erase_button)
        self.color_buttons[None] = erase_button
        erase_button.clicked.connect(
            lambda: self.select_color(None)
        )
        palette.addWidget(erase_button)

        layout.addWidget(palette_card)

        self.selected_label = QLabel()
        self.selected_label.setObjectName("mutedText")
        self.selected_label.setWordWrap(True)
        self.input_status = QLabel("조각 조합과 색별 9개 제한으로 확정되는 칸만 자동 입력합니다.")
        self.input_status.setObjectName("mutedText")
        self.input_status.setWordWrap(True)

        self.edit_centers = QCheckBox(
            "중앙 색 수정\n— 중앙 색이 예시와 다를 때"
        )

        panel, self.input_buttons = self.make_net(
            editable=True
        )
        board_card = QFrame()
        board_card.setObjectName("card")
        board_layout = QVBoxLayout(board_card)
        board_layout.setContentsMargins(8, 6, 8, 6)
        board_layout.addWidget(panel, 0, Qt.AlignmentFlag.AlignHCenter)

        self.count_label = QLabel()
        self.count_label.setWordWrap(True)
        self.count_label.setObjectName("mutedText")

        hint = QLabel(
            "면 그림의 위쪽: F/R/B/L은 U · U는 B · D는 F"
        )
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setObjectName("mutedText")
        hint.setWordWrap(True)

        input_actions = QHBoxLayout()
        self.reset_colors_button = QPushButton("색상 초기화")
        self.reset_colors_button.setToolTip("예시 중앙색만 남기고 입력한 색을 모두 비웁니다.")
        self.reset_colors_button.clicked.connect(self.reset_colors)
        input_actions.addWidget(self.reset_colors_button)
        input_actions.addStretch()

        self.solve_button = QPushButton("해법 찾기 →")
        self.solve_button.setMinimumHeight(42)
        self.solve_button.clicked.connect(self.start_solve)
        input_actions.addWidget(self.solve_button)

        summary_card = QFrame()
        summary_card.setObjectName("card")
        summary_card.setFixedWidth(300)
        summary_layout = QVBoxLayout(summary_card)
        summary_layout.setContentsMargins(16, 14, 16, 14)
        summary_layout.setSpacing(10)
        summary_title = QLabel("입력 상태")
        summary_title.setStyleSheet("font-size: 15px; font-weight: 700;")
        summary_layout.addWidget(summary_title)
        summary_layout.addWidget(self.selected_label)
        summary_layout.addWidget(self.input_status)
        summary_layout.addWidget(self.edit_centers)
        summary_layout.addWidget(self.count_label)
        summary_layout.addWidget(hint)
        summary_layout.addStretch()
        summary_layout.addLayout(input_actions)

        self.input_content_layout = QHBoxLayout()
        self.input_content_layout.setSpacing(12)
        self.input_content_layout.addWidget(board_card, 0)
        self.input_content_layout.addWidget(summary_card, 1)
        self.input_content_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.addLayout(self.input_content_layout, 1)

        self.tabs.addTab(self.make_scroll_page(self.input_page), "① 색상 입력")

    def make_guide_page(self):
        self.guide_page = QWidget()
        self.guide_page.setObjectName("appPage")
        layout = QVBoxLayout(self.guide_page)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(6)

        self.basis_label = QLabel()
        self.basis_label.setWordWrap(True)
        self.basis_label.setObjectName("mutedText")
        layout.addWidget(self.basis_label)

        self.step_label = QLabel()
        self.step_label.setObjectName("stepTitle")
        layout.addWidget(self.step_label)

        self.after_checkbox = QCheckBox(
            "이번 동작을 마친 뒤의 상태 미리보기"
        )
        self.after_checkbox.toggled.connect(
            self.update_preview
        )
        layout.addWidget(self.after_checkbox)

        body = QHBoxLayout()

        panel, self.guide_buttons = self.make_net(
            editable=False
        )
        body.addWidget(panel, 3)

        detail = QVBoxLayout()

        self.instruction_label = QLabel()
        self.instruction_label.setWordWrap(True)
        self.instruction_label.setStyleSheet(
            "font-size: 20px; font-weight: bold;"
        )
        detail.addWidget(self.instruction_label)

        self.direction_label = QLabel()
        self.direction_label.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )
        self.direction_label.setStyleSheet(
            "font-size: 64px; color: #2563EB;"
        )
        detail.addWidget(self.direction_label)

        self.view_label = QLabel()
        self.view_label.setWordWrap(True)
        self.view_label.setObjectName("mutedText")
        detail.addWidget(self.view_label)

        face_grid = QGridLayout()
        self.detail_buttons = []

        for index in range(9):
            button = QPushButton()
            button.setFixedSize(58, 58)
            button.setStyleSheet("padding: 0;")
            self.detail_buttons.append(button)
            face_grid.addWidget(
                button,
                index // 3,
                index % 3,
            )

        detail.addLayout(face_grid)
        detail.addStretch()

        body.addLayout(detail, 1)
        layout.addLayout(body, 1)

        notice = QLabel(
            "해당 면의 한 층만 돌리세요.\n"
            "바라보기 위해 큐브 전체를 움직였다면, "
            "다음 동작 전에 처음 기준 자세로 돌아오세요."
        )
        notice.setWordWrap(True)
        layout.addWidget(notice)

        controls = QHBoxLayout()

        input_button = QPushButton("입력 화면으로")
        input_button.clicked.connect(
            lambda: self.tabs.setCurrentIndex(0)
        )

        self.previous_button = QPushButton("← 이전 단계")
        self.previous_button.clicked.connect(self.previous)

        self.next_button = QPushButton(
            "돌렸어요 · 다음 →"
        )
        self.next_button.clicked.connect(self.next)

        controls.addWidget(input_button)
        controls.addStretch()
        controls.addWidget(self.previous_button)
        controls.addWidget(self.next_button)

        layout.addLayout(controls)

        self.tabs.addTab(self.make_scroll_page(self.guide_page), "② 회전 안내")

    @staticmethod
    def make_scroll_page(page):
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setWidget(page)
        return scroll_area

    def select_color(self, color):
        self.selected_color = color

        for button_color, button in self.color_buttons.items():
            button.setChecked(button_color == color)
            button.setStyleSheet(
                sticker_style(
                    button_color,
                    highlighted=button_color == color and color is not None,
                )
                if button_color is not None
                else (
                    "border: 2px solid #172033; border-radius: 6px;"
                    if color is None
                    else ""
                )
            )

        name = (
            COLOR_NAMES[color]
            if color is not None
            else "지우개"
        )
        self.selected_label.setText(
            f"현재 선택 · {name}  —  우클릭 부채꼴 순서:\n흰 → 노 → 파 → 초 → 빨 → 주"
        )

    def begin_radial_color(self, button, global_position):
        if (
            button.property("sticker_index") == 4
            and not self.edit_centers.isChecked()
        ):
            return
        self.radial_button = button
        self.radial_picker.open_at(global_position)

    def move_radial_color(self, global_position):
        self.radial_picker.set_pointer(global_position)

    def finish_radial_color(self, button, global_position):
        color = self.radial_picker.color_at(global_position)
        self.radial_picker.hide()
        if color is None or button is None:
            return
        face = button.property("face")
        index = button.property("sticker_index")
        if face is not None and index is not None:
            self.paint_sticker(face, int(index), color)

    def auto_fill_forced_colors(self):
        """Fill only stickers forced by center identities, cubie colors, and color counts."""
        centers = [self.faces[face][4] for face in FACE_ORDER]
        if any(color is None for color in centers) or len(set(centers)) != 6:
            return 0

        filled = 0
        while True:
            counts = Counter(
                color
                for face in FACE_ORDER
                for color in self.faces[face]
                if color is not None
            )
            deficits = {color: 9 - counts[color] for color in COLOR_NAMES}
            if any(value < 0 for value in deficits.values()):
                break

            blank_cells = [
                (face, index)
                for face in FACE_ORDER
                for index in range(9)
                if index != 4 and self.faces[face][index] is None
            ]
            if not blank_cells:
                break

            changed = False
            available = [color for color, amount in deficits.items() if amount > 0]
            if len(available) == 1 and deficits[available[0]] == len(blank_cells):
                for face, index in blank_cells:
                    self.faces[face][index] = available[0]
                    self.auto_filled_stickers.add((face, index))
                filled += len(blank_cells)
                break

            allowed_pieces = {}
            used_pieces = {}
            for position, stickers in CUBIE_STICKERS.items():
                size = sum(component != 0 for component in position)
                if size not in (2, 3):
                    continue
                colors = frozenset(self.faces[face][4] for face, _ in stickers)
                allowed_pieces.setdefault(size, set()).add(colors)
                current_values = [
                    self.faces[face][index]
                    for face, index in stickers
                ]
                if all(color is not None for color in current_values):
                    used_pieces.setdefault(size, set()).add(frozenset(current_values))

            for position, stickers in CUBIE_STICKERS.items():
                size = len(stickers)
                if size not in (2, 3):
                    continue
                missing = [
                    (face, index)
                    for face, index in stickers
                    if self.faces[face][index] is None
                ]
                if not missing:
                    continue

                known_values = [
                    self.faces[face][index]
                    for face, index in stickers
                    if self.faces[face][index] is not None
                ]
                known = set(known_values)
                if len(known) != len(known_values):
                    continue

                candidates_by_slot = [set() for _ in missing]
                for piece in allowed_pieces.get(size, ()):
                    if piece in used_pieces.get(size, set()):
                        continue
                    if not known.issubset(piece):
                        continue
                    remaining = tuple(piece - known)
                    if len(remaining) != len(missing):
                        continue
                    for assignment in itertools.permutations(remaining):
                        usage = Counter(assignment)
                        if any(usage[color] > deficits[color] for color in usage):
                            continue
                        for slot, color in enumerate(assignment):
                            candidates_by_slot[slot].add(color)

                for (face, index), candidates in zip(missing, candidates_by_slot):
                    if len(candidates) == 1:
                        self.faces[face][index] = next(iter(candidates))
                        self.auto_filled_stickers.add((face, index))
                        filled += 1
                        changed = True
                        break

                if changed:
                    break

            if not changed:
                break

        return filled

    def paint_sticker(self, face, index, color=None):
        if index == 4 and not self.edit_centers.isChecked():
            return

        for inferred_face, inferred_index in self.auto_filled_stickers:
            self.faces[inferred_face][inferred_index] = None
        self.auto_filled_stickers.clear()

        chosen_color = self.selected_color if color is None else color
        self.faces[face][index] = chosen_color
        self.tabs.setTabEnabled(1, False)
        filled = self.auto_fill_forced_colors()
        if filled:
            self.input_status.setText(f"확정 가능한 색 {filled}칸을 자동 입력했습니다.")
        else:
            self.input_status.setText("조각 조합과 색별 9개 제한으로 확정되는 칸만 자동 입력합니다.")
        self.update_input()

    def advance_with_space(self):
        if self.tabs.currentIndex() == 1 and self.next_button.isEnabled():
            self.next()

    def reset_colors(self):
        self.faces = {
            face: [
                CENTERS[face] if index == 4 else None
                for index in range(9)
            ]
            for face in FACE_ORDER
        }
        self.auto_filled_stickers.clear()
        self.moves = []
        self.states = []
        self.step = 0
        self.selected_color = "W"
        self.edit_centers.setChecked(False)
        self.tabs.setTabEnabled(1, False)
        self.tabs.setCurrentIndex(0)
        self.solve_button.setEnabled(True)
        self.solve_button.setText("해법 찾기 →")
        self.input_status.setText("조각 조합과 색별 9개 제한으로 확정되는 칸만 자동 입력합니다.")

        if hasattr(self, "_animation_kind"):
            self._animation_kind = None
        if hasattr(self, "_camera_transition_pending"):
            self._camera_transition_pending = False
        if hasattr(self, "_queued_rewind"):
            self._queued_rewind = None
        if hasattr(self, "_pending_rewind"):
            self._pending_rewind = None
        if hasattr(self, "cube3d"):
            self.cube3d.stop_animation()
            self.cube3d.set_state(None)
            self.cube3d.reset_camera()
        self.update_input()

    def draw_net(self, buttons, faces, active_face=None):
        for (face, index), button in buttons.items():
            color = faces[face][index]

            text = (
                f"{face}·{color or '?'}"
                if index == 4
                else (
                    f"{color}*"
                    if color and (face, index) in self.auto_filled_stickers
                    else color or ""
                )
            )

            button.setText(text)
            if (face, index) in self.auto_filled_stickers:
                button.setToolTip("자동 입력된 색 · 클릭해 직접 바꿀 수 있습니다.")
            elif index != 4:
                button.setToolTip("좌클릭: 선택한 색 · 우클릭 드래그: 부채꼴 색상 선택")
            button.setStyleSheet(
                sticker_style(
                    color,
                    highlighted=face == active_face,
                    size=40,
                )
            )

    def update_input(self):
        self.draw_net(self.input_buttons, self.faces)
        self.select_color(self.selected_color)

        counts = Counter(
            color
            for face in FACE_ORDER
            for color in self.faces[face]
        )

        self.count_label.setText(
            " / ".join(
                f"{name}: {counts[color]}/9"
                for color, name in COLOR_NAMES.items()
            )
            + f"\n미입력: {counts[None]}칸"
        )

    def start_solve(self):
        counts = Counter(
            color
            for face in FACE_ORDER
            for color in self.faces[face]
        )

        if counts[None]:
            QMessageBox.warning(
                self,
                "입력 확인",
                f"아직 {counts[None]}칸이 비어 있습니다.",
            )
            return

        if any(
            counts[color] != 9
            for color in COLOR_NAMES
        ):
            QMessageBox.warning(
                self,
                "입력 확인",
                "각 색은 정확히 9개여야 합니다.",
            )
            return

        try:
            cube_string = build_kociemba_string(
                self.faces
            )
        except Exception as exc:
            QMessageBox.warning(
                self, "입력 확인", str(exc)
            )
            return

        already_solved = all(
            all(
                color == self.faces[face][4]
                for color in self.faces[face]
            )
            for face in FACE_ORDER
        )

        if already_solved:
            self.show_solution("")
            return

        self.input_page.setEnabled(False)
        self.tabs.setTabEnabled(1, False)
        self.solve_button.setText("해법 계산 중…")

        self.worker = SolverThread(cube_string, self)
        self.worker.finished.connect(self.solve_finished)
        self.worker.start()

    def solve_finished(self):
        worker = self.worker
        self.worker = None

        self.input_page.setEnabled(True)
        self.solve_button.setText("해법 찾기 →")

        if worker.error:
            QMessageBox.warning(
                self,
                "해법 계산 실패",
                worker.error
                + "\n\n색 개수는 정확하지만 해법이 존재하지 않습니다. "
                "잘못된 조합이거나 입력 방향이 잘못됐을 수 있습니다."
                "\n정확한 색상이 맞는지 다시 확인해주세요.",
            )
        else:
            self.show_solution(worker.solution)

        worker.deleteLater()

    def show_solution(self, solution):
        self.moves = solution.split()
        self.states = [copy_faces(self.faces)]

        try:
            for move in self.moves:
                state = copy_faces(self.states[-1])
                apply_move_to_faces(state, move)
                self.states.append(state)

            final = self.states[-1]

            if not all(
                all(
                    color == final[face][4]
                    for color in final[face]
                )
                for face in FACE_ORDER
            ):
                raise ValueError(
                    "계산된 해법으로 완성되지 않았습니다. "
                    "회전 안내를 중단합니다."
                )

        except Exception as exc:
            QMessageBox.warning(
                self, "해법 검증 실패", str(exc)
            )
            return

        self.step = 0
        self.tabs.setTabEnabled(1, True)
        self.render_step()
        self.tabs.setCurrentIndex(1)

    def render_step(self):
        total = len(self.moves)
        finished = self.step >= total

        front = COLOR_NAMES[self.states[0]["F"][4]]
        up = COLOR_NAMES[self.states[0]["U"][4]]

        self.basis_label.setText(
            f"기준 자세: 앞면 F 중앙 = {front} / "
            f"윗면 U 중앙 = {up}\n"
            "F/R/B/L/U/D는 처음 정한 면을 뜻합니다."
        )

        self.after_checkbox.blockSignals(True)
        self.after_checkbox.setChecked(False)
        self.after_checkbox.blockSignals(False)
        self.after_checkbox.setEnabled(not finished)

        self.previous_button.setEnabled(self.step > 0)
        self.next_button.setEnabled(not finished)

        for button in self.detail_buttons:
            button.setVisible(not finished)

        if finished:
            self.step_label.setText(
                f"완료 · {total}개 동작"
            )
            self.instruction_label.setText(
                "큐브 맞추기 완료!"
            )
            self.direction_label.setText("✓")
            self.view_label.setText(
                "실물의 여섯 면도 각각 한 색으로 "
                "맞춰졌는지 확인하세요."
            )
            self.draw_net(
                self.guide_buttons,
                self.states[-1],
            )
            return

        move = self.moves[self.step]
        face = move[0]
        suffix = move[1:]

        if suffix == "2":
            direction = "180° · 반 바퀴"
            arrow = "↻ ↻"
        elif suffix == "'":
            direction = "반시계 방향 90°"
            arrow = "↺"
        else:
            direction = "시계 방향 90°"
            arrow = "↻"

        center = COLOR_NAMES[self.states[0][face][4]]
        top = TOP_NEIGHBOR[face]

        self.step_label.setText(
            f"다음 동작 {self.step + 1} / {total}"
            f" · 기호 {move}"
        )

        self.instruction_label.setText(
            f"{FACE_NAMES[face]}\n"
            f"중앙 색: {center}\n"
            f"{direction}"
        )

        self.direction_label.setText(arrow)

        self.view_label.setText(
            "방향은 해당 면을 바깥에서 직접 "
            "바라봤을 때 기준입니다.\n\n"
            f"아래 확대 그림의 위쪽은 "
            f"{FACE_NAMES[top]} {top}입니다."
        )

        self.update_preview()

    def update_preview(self, *args):
        if not self.states or self.step >= len(self.moves):
            return

        offset = (
            1 if self.after_checkbox.isChecked() else 0
        )
        state = self.states[self.step + offset]
        face = self.moves[self.step][0]

        self.draw_net(
            self.guide_buttons,
            state,
            active_face=face,
        )

        for index, button in enumerate(
            self.detail_buttons
        ):
            color = state[face][index]
            button.setText(
                face if index == 4 else color
            )
            button.setStyleSheet(
                sticker_style(color, size=58)
            )

    def next(self):
        if self.step < len(self.moves):
            self.step += 1
            self.render_step()

    def previous(self):
        if self.step == 0:
            return

        move = self.moves[self.step - 1]

        if move.endswith("2"):
            inverse = move
        elif move.endswith("'"):
            inverse = move[0]
        else:
            inverse = move + "'"

        answer = QMessageBox.question(
            self,
            "이전 단계로 이동",
            f"이전 단계로 돌아갈까요?\n\n"
            f"실물에서 직전 동작 {move}을 했다면 "
            f"반대 동작 {inverse}으로 되돌려야 합니다.\n"
            "아직 실제로 돌리지 않았다면 "
            "실물을 되돌릴 필요는 없습니다.",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if answer == QMessageBox.StandardButton.Yes:
            self.step -= 1
            self.render_step()

    def closeEvent(self, event):
        if self.worker is not None:
            QMessageBox.information(
                self,
                "계산 중",
                "해법 계산이 끝난 뒤 종료해 주세요.",
            )
            event.ignore()
            return

        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    configure_application_style(app)

    window = CubeGuide()
    window.show()

    sys.exit(app.exec())
