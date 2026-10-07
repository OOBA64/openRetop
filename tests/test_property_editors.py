"""Property panel editors: X/Y/Z vector boxes and in-place value updates."""

from __future__ import annotations

import unittest

from PySide6.QtWidgets import QApplication, QDoubleSpinBox

from workbench_ui.contracts import FieldDefinition, PropertyInspectorModel
from workbench_ui.widgets import PropertyInspectorWidget, VectorEditor


class VectorEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _inspector(self) -> PropertyInspectorWidget:
        fields = (
            FieldDefinition("location", "Location", (1.0, 2.0, 3.0), "vector", group="Transform"),
            FieldDefinition("scale", "Scale", 1.0, "number", group="Transform"),
        )
        inspector = PropertyInspectorWidget(PropertyInspectorModel(fields))
        # close, not just delete later: a shown top-level widget keeps focus and steals hover
        # events from tests that run after this one
        self.addCleanup(lambda: (inspector.close(), inspector.deleteLater(), self.app.processEvents()))
        return inspector

    def test_a_vector_is_three_labelled_number_boxes_not_a_text_line(self) -> None:
        editor = self._inspector()._editors["location"]
        self.assertIsInstance(editor, VectorEditor)
        self.assertEqual(len(editor.findChildren(QDoubleSpinBox)), 3)
        self.assertEqual(editor.value(), (1.0, 2.0, 3.0))

    def test_long_floats_are_shown_rounded(self) -> None:
        inspector = self._inspector()
        inspector.show_values({"location": (0.7483314773547883, 0.0, 0.0)})
        self.assertEqual(inspector._editors["location"].boxes[0].text(), "0.748")

    def test_editing_one_box_commits_the_whole_vector(self) -> None:
        inspector = self._inspector()
        received: list[tuple[str, object]] = []
        inspector.value_changed.connect(lambda field_id, value: received.append((field_id, value)))
        editor = inspector._editors["location"]
        editor.boxes[1].setValue(7.5)
        editor.boxes[1].editingFinished.emit()
        self.assertEqual(received, [("location", (1.0, 7.5, 3.0))])

    def test_show_values_updates_in_place_without_emitting(self) -> None:
        inspector = self._inspector()
        received: list[object] = []
        inspector.value_changed.connect(lambda *args: received.append(args))
        editor = inspector._editors["location"]
        inspector.show_values({"location": (4.0, 5.0, 6.0), "scale": 2.0, "unknown": 1})
        self.assertIs(inspector._editors["location"], editor)  # not rebuilt
        self.assertEqual(editor.value(), (4.0, 5.0, 6.0))
        self.assertEqual(inspector._editors["scale"].value(), 2.0)
        self.assertEqual(received, [])

    def test_a_box_being_typed_in_is_not_overwritten(self) -> None:
        inspector = self._inspector()
        inspector.show()
        editor = inspector._editors["location"]
        editor.boxes[0].setFocus()
        self.app.processEvents()
        if not editor.boxes[0].hasFocus():
            self.skipTest("focus is not delivered on this platform")
        inspector.show_values({"location": (9.0, 9.0, 9.0)})
        self.assertEqual(editor.value(), (1.0, 9.0, 9.0))


if __name__ == "__main__":
    unittest.main()
