"""The "Model & Next steps" panel: shows what the project contains and what to do next."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from openretop.application.guidance import Guidance, Stage

# (enabled, tooltip) for an action id.
Availability = Callable[[str], tuple[bool, str]]


class NextStepsPanel(QWidget):
    """Renders a :class:`Guidance` as a title, summary, and one button per suggested action."""

    action_requested = Signal(str)
    recent_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("next_steps_panel")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(10, 10, 10, 10)
        self._layout.setSpacing(6)
        self.guidance: Guidance | None = None
        self.step_buttons: dict[str, QPushButton] = {}
        self.recent_buttons: list[QPushButton] = []

    def set_guidance(
        self,
        guidance: Guidance,
        availability: Availability,
        recent_projects: tuple[str, ...] = (),
    ) -> None:
        self.guidance = guidance
        self._clear()

        title = QLabel(guidance.title, self)
        title.setObjectName("next_steps_title")
        title.setStyleSheet("font-size: 13pt; font-weight: 600;")
        title.setWordWrap(True)
        self._layout.addWidget(title)

        explanation = QLabel(guidance.explanation, self)
        explanation.setObjectName("next_steps_explanation")
        explanation.setWordWrap(True)
        self._layout.addWidget(explanation)

        for line in guidance.summary:
            label = QLabel(line, self)
            label.setObjectName("next_steps_summary")
            label.setWordWrap(True)
            self._layout.addWidget(label)

        for step in guidance.steps:
            enabled, tooltip = availability(step.action_id)
            button = QPushButton(step.label, self)
            button.setObjectName(f"next_step_{step.action_id.replace('.', '_')}")
            button.setProperty("primary", step.primary)
            if step.primary:
                button.setStyleSheet(
                    "font-weight: 600; border: 1px solid #00d1ff; padding: 5px;"
                )
            button.setEnabled(enabled)
            hint = step.hint
            button.setToolTip(f"{hint}\n\n{tooltip}" if hint and tooltip else hint or tooltip)
            button.clicked.connect(lambda _checked=False, action_id=step.action_id: self.action_requested.emit(action_id))
            self._layout.addWidget(button)
            self.step_buttons[step.action_id] = button
            if step.hint:
                note = QLabel(step.hint, self)
                note.setObjectName("next_step_hint")
                note.setWordWrap(True)
                note.setStyleSheet("color: #9aa0a6; margin: 0 0 4px 4px;")
                self._layout.addWidget(note)

        if guidance.stage is Stage.START and recent_projects:
            heading = QLabel("Recent projects", self)
            heading.setStyleSheet("font-weight: 600; margin-top: 8px;")
            self._layout.addWidget(heading)
            for path in recent_projects:
                button = QPushButton(Path(path).name, self)
                button.setFlat(True)
                button.setToolTip(path)
                button.clicked.connect(lambda _checked=False, value=path: self.recent_requested.emit(value))
                self._layout.addWidget(button)
                self.recent_buttons.append(button)

        if guidance.cad_note:
            warning = QLabel(guidance.cad_note, self)
            warning.setObjectName("next_steps_cad_note")
            warning.setWordWrap(True)
            warning.setStyleSheet("color: #e0a030; margin-top: 8px;")
            self._layout.addWidget(warning)
        self._layout.addStretch(1)

    def _clear(self) -> None:
        self.step_buttons.clear()
        self.recent_buttons.clear()
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = None if item is None else item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
