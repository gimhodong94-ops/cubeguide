import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QStackedWidget,
    QHBoxLayout,
    QPushButton,
    QCheckBox,
    QLabel,
    QSlider,
    QMessageBox,
    QWidget,
)

from gui import COLOR_NAMES, CubeGuide, sticker_style
from cube3d import Cube3D


class CubeGuide3D(CubeGuide):
    def make_guide_page(self):
        # 기존 회전 안내 화면을 먼저 만듭니다.
        super().make_guide_page()
        self._animation_kind = None
        self._camera_transition_pending = False
        self._queued_rewind = None
        self._pending_rewind = None

        layout = self.guide_page.layout()

        # 기존 gui.py에서 네 번째 항목이 큐브 표시 영역입니다.
        body = layout.itemAt(3).layout()
        net_panel = body.takeAt(0).widget()

        cube_stage = QWidget()
        cube_layout = QHBoxLayout(cube_stage)
        cube_layout.setContentsMargins(4, 4, 4, 4)
        cube_layout.setSpacing(8)

        self.roll_left_button = QPushButton("↶")
        self.roll_left_button.setFixedSize(42, 62)
        self.roll_left_button.setStyleSheet("font-size: 24px; border-radius: 12px;")
        self.roll_left_button.setToolTip("화면을 반시계 방향으로 90° 회전")
        self.roll_left_button.clicked.connect(
            lambda: self.cube3d.rotate_roll(-90)
        )

        self.cube3d = Cube3D(cube_stage)
        self.cube3d.animation_finished.connect(
            self.animation_finished
        )
        self.cube3d.camera_focus_finished.connect(
            self.camera_focus_finished
        )

        self.roll_right_button = QPushButton("↷")
        self.roll_right_button.setFixedSize(42, 62)
        self.roll_right_button.setStyleSheet("font-size: 24px; border-radius: 12px;")
        self.roll_right_button.setToolTip("화면을 시계 방향으로 90° 회전")
        self.roll_right_button.clicked.connect(
            lambda: self.cube3d.rotate_roll(90)
        )

        cube_layout.addWidget(self.roll_left_button)
        cube_layout.addWidget(self.cube3d, 1)
        cube_layout.addWidget(self.roll_right_button)

        # 3D와 기존 전개도를 전환할 수 있습니다.
        self.view_stack = QStackedWidget()
        self.view_stack.addWidget(cube_stage)
        self.view_stack.addWidget(net_panel)

        body.insertWidget(0, self.view_stack, 3)

        actions = QHBoxLayout()

        self.net_checkbox = QCheckBox("전개도로 보기")
        self.net_checkbox.toggled.connect(
            lambda checked:
            self.view_stack.setCurrentIndex(
                1 if checked else 0
            )
        )
        actions.addWidget(self.net_checkbox)

        speed_control = QWidget()
        speed_layout = QHBoxLayout(speed_control)
        speed_layout.setContentsMargins(0, 0, 0, 0)
        speed_layout.setSpacing(5)
        speed_layout.addWidget(QLabel("속도"))
        speed_layout.addWidget(QLabel("0.5×"))
        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setRange(5, 20)
        self.speed_slider.setSingleStep(1)
        self.speed_slider.setPageStep(1)
        self.speed_slider.setTickInterval(1)
        self.speed_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.speed_slider.setValue(10)
        self.speed_slider.setFixedWidth(125)
        self.speed_slider.setToolTip("애니메이션 속도: 0.5×부터 2.0×까지, 0.1× 단위")
        self.speed_slider.valueChanged.connect(self.update_animation_speed)
        speed_layout.addWidget(self.speed_slider)
        self.speed_value_label = QLabel("1.0×")
        self.speed_value_label.setMinimumWidth(38)
        speed_layout.addWidget(self.speed_value_label)
        speed_layout.addWidget(QLabel("2.0×"))
        actions.addWidget(speed_control)

        actions.addStretch()

        self.reset_camera_button = QPushButton("기준 시점")
        self.reset_camera_button.clicked.connect(
            self.cube3d.reset_camera
        )
        actions.addWidget(self.reset_camera_button)

        self.play_button = QPushButton(
            "▶ 3D 동작 다시 보기"
        )
        self.play_button.clicked.connect(
            self.play_animation
        )
        actions.addWidget(self.play_button)

        layout.insertLayout(4, actions)

    def update_animation_speed(self, slider_value):
        multiplier = slider_value / 10
        self.speed_value_label.setText(f"{multiplier:.1f}×")
        self.cube3d.set_animation_speed(multiplier)

    def render_step(self):
        self._camera_transition_pending = self.step < len(self.moves)
        super().render_step()

        finished = self.step >= len(self.moves)
        if finished:
            self._camera_transition_pending = False
            self.play_button.setEnabled(False)
            self.roll_left_button.setEnabled(True)
            self.roll_right_button.setEnabled(True)
            self.reset_camera_button.setEnabled(True)
            self.cube3d.set_state(self.states[-1])
        else:
            self._set_turn_controls_enabled(False)
            self.cube3d.set_state(self.states[self.step])
            face = self.moves[self.step][0]
            self.cube3d.focus_face(face)

    def _set_turn_controls_enabled(self, enabled):
        self.next_button.setEnabled(
            enabled and self.step < len(self.moves)
        )
        self.previous_button.setEnabled(enabled and self.step > 0)
        self.after_checkbox.setEnabled(
            enabled and self.step < len(self.moves)
        )
        self.play_button.setEnabled(
            enabled and self.step < len(self.moves)
        )
        self.roll_left_button.setEnabled(enabled)
        self.roll_right_button.setEnabled(enabled)
        self.reset_camera_button.setEnabled(enabled)

    def camera_focus_finished(self):
        if not self._camera_transition_pending:
            return

        self._camera_transition_pending = False
        if self._queued_rewind is not None:
            old_step, inverse = self._queued_rewind
            self._queued_rewind = None
            self._show_rewind_hint(old_step, inverse)
            self._pending_rewind = (old_step, inverse)
            QTimer.singleShot(180, self._begin_rewind_animation)
            return

        self.update_preview()
        self._set_turn_controls_enabled(True)

    def _show_rewind_hint(self, old_step, inverse):
        self.cube3d.set_state(self.states[old_step], inverse[0], inverse)
        self.draw_net(
            self.guide_buttons,
            self.states[old_step],
            active_face=inverse[0],
        )
        self.step_label.setText(f"되돌리는 중 · {inverse}")
        suffix = inverse[1:]
        direction = (
            "180° · 반 바퀴" if suffix == "2"
            else "반시계 방향 90°" if suffix == "'"
            else "시계 방향 90°"
        )
        center_color = COLOR_NAMES[self.states[old_step][inverse[0]][4]]
        self.instruction_label.setText(
            f"{inverse[0]} 면 · 중앙 색: {center_color}\n{direction}"
        )
        self.direction_label.setText(
            "↻ ↻" if inverse.endswith("2")
            else "↺" if inverse.endswith("'")
            else "↻"
        )
        self.view_label.setText("청록색 화살표가 가리키는 방향으로 돌리세요.")
        for index, button in enumerate(self.detail_buttons):
            color = self.states[old_step][inverse[0]][index]
            button.setText(inverse[0] if index == 4 else color)
            button.setStyleSheet(sticker_style(color))

    def _begin_rewind_animation(self):
        if self._pending_rewind is None:
            return
        old_step, inverse = self._pending_rewind
        self._pending_rewind = None
        self._animation_kind = "rewind"
        self.cube3d.animate(
            self.states[old_step],
            inverse,
            duration=1250,
        )

    def next(self):
        if (
            self.step >= len(self.moves)
            or self._camera_transition_pending
            or self._pending_rewind is not None
            or self._queued_rewind is not None
            or self._animation_kind is not None
        ):
            return

        move = self.moves[self.step]
        self.after_checkbox.blockSignals(True)
        self.after_checkbox.setChecked(False)
        self.after_checkbox.blockSignals(False)
        self.update_preview()
        self.net_checkbox.setChecked(False)
        self.view_stack.setCurrentIndex(0)
        self._animation_kind = "advance"
        self._set_turn_controls_enabled(False)
        self.cube3d.animate(
            self.states[self.step],
            move,
            duration=1250,
        )

    def previous(self):
        if (
            self.step == 0
            or self._camera_transition_pending
            or self._pending_rewind is not None
            or self._queued_rewind is not None
            or self._animation_kind is not None
        ):
            return

        old_step = self.step
        move = self.moves[old_step - 1]
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
        if answer != QMessageBox.StandardButton.Yes:
            return

        self.after_checkbox.blockSignals(True)
        self.after_checkbox.setChecked(False)
        self.after_checkbox.blockSignals(False)
        self.update_preview()
        self.net_checkbox.setChecked(False)
        self.view_stack.setCurrentIndex(0)
        self._queued_rewind = (old_step, inverse)
        self._camera_transition_pending = True
        self.cube3d.set_state(self.states[old_step])
        self._set_turn_controls_enabled(False)
        self.cube3d.focus_face(inverse[0])

    def update_preview(self, *args):
        self._animation_kind = None
        super().update_preview(*args)

        if not self.states:
            return

        if self.step >= len(self.moves):
            self.cube3d.set_state(self.states[-1])
            return

        offset = (
            1 if self.after_checkbox.isChecked()
            else 0
        )
        state = self.states[self.step + offset]
        target_step = self.step + offset
        hint_move = (
            self.moves[target_step]
            if target_step < len(self.moves)
            else None
        )
        face = hint_move[0] if hint_move else None
        if self._camera_transition_pending:
            face = None
            hint_move = None

        self.draw_net(self.guide_buttons, state, active_face=face)
        self.cube3d.set_state(state, face, hint_move)

    def play_animation(self):
        if (
            not self.states
            or self._camera_transition_pending
            or self._pending_rewind is not None
            or self._queued_rewind is not None
            or self._animation_kind is not None
        ):
            return

        if self.step >= len(self.moves):
            return

        # 毎回の動作前の状態から再生します。
        self.after_checkbox.blockSignals(True)
        self.after_checkbox.setChecked(False)
        self.after_checkbox.blockSignals(False)

        self.update_preview()

        self.net_checkbox.setChecked(False)
        self.view_stack.setCurrentIndex(0)

        move = self.moves[self.step]
        self._animation_kind = "replay"
        self._set_turn_controls_enabled(False)

        self.cube3d.animate(
            self.states[self.step],
            move,
            duration=1800,
        )

    def animation_finished(self):
        animation_kind = self._animation_kind
        self._animation_kind = None

        if animation_kind == "advance":
            self.step += 1
            self.render_step()
            return

        if animation_kind == "rewind":
            self.step -= 1
            self.render_step()
            return

        if animation_kind == "replay":
            self.after_checkbox.blockSignals(True)
            self.after_checkbox.setChecked(True)
            self.after_checkbox.blockSignals(False)
            self._camera_transition_pending = True
            self.update_preview()
            next_step = self.step + 1
            if next_step < len(self.moves):
                self.cube3d.focus_face(self.moves[next_step][0])
            else:
                self._camera_transition_pending = False
                self.update_preview()
                self._set_turn_controls_enabled(True)
            return

        self._set_turn_controls_enabled(True)

    def closeEvent(self, event):
        self._camera_transition_pending = False
        self._queued_rewind = None
        self._pending_rewind = None
        self.cube3d.stop_animation()
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)

    app.setStyleSheet("""
        QWidget {
            font-family: 'Malgun Gothic';
            font-size: 13px;
        }
        QMainWindow {
            background: #F1F5F9;
        }
        QPushButton {
            padding: 7px;
            border-radius: 6px;
        }
        QTabBar::tab {
            padding: 10px 20px;
        }
    """)

    window = CubeGuide3D()
    window.setWindowTitle("3×3 큐브 가이드 · 3D")
    window.resize(1200, 850)
    window.show()

    sys.exit(app.exec())
