from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from settings.settings_data import (
    DEFAULT_REGION_SELECTION_EDGE_COLOR,
    DEFAULT_REGION_SELECTION_COLOR,
    DEFAULT_REGION_SELECTION_OPACITY,
    SETTINGS_VERSION,
    AppDisplaySettings,
    AppImportSettings,
    AppKeybindSettings,
    AppSettings,
    AppUiSettings,
    default_app_settings,
)
from settings.settings_io import (
    load_settings,
    save_settings,
    settings_from_dict,
    settings_to_dict,
)


def _sample_settings() -> AppSettings:
    return AppSettings(
        version=SETTINGS_VERSION,
        display=AppDisplaySettings(
            show_grid=False,
            show_axes=True,
            show_normals=True,
            show_axis_gizmo=False,
            show_viewcube=False,
            region_selection_color="#FF8800",
            region_selection_edge_color="#FFF2CC",
            region_selection_opacity=0.5,
        ),
        import_settings=AppImportSettings(
            default_proxy_quality="High",
        ),
        ui=AppUiSettings(
            window_width=1440,
            window_height=900,
            window_mode="remembered_size",
            remember_window_size=False,
        ),
        keybinds=AppKeybindSettings(
            undo="Ctrl+Alt+Z",
            redo="Ctrl+Alt+Y",
            rename_selected="Ctrl+R",
            toggle_visibility="V",
            isolate_selected="Shift+V",
            show_all="Alt+V",
            frame_selected="F",
            move="G",
            rotate="R",
            confirm_transform="Enter",
            cancel_transform="Esc",
            delete_selected="Delete",
        ),
        future={"reserved": "ok"},
    )


class SettingsDataTests(unittest.TestCase):
    def test_default_app_settings_returns_valid_defaults(self) -> None:
        settings = default_app_settings()

        self.assertEqual(settings.version, SETTINGS_VERSION)
        self.assertTrue(settings.display.show_grid)
        self.assertTrue(settings.display.show_axes)
        self.assertFalse(settings.display.show_normals)
        self.assertTrue(settings.display.show_axis_gizmo)
        self.assertTrue(settings.display.show_viewcube)
        self.assertEqual(settings.display.region_selection_color, DEFAULT_REGION_SELECTION_COLOR)
        self.assertEqual(
            settings.display.region_selection_edge_color,
            DEFAULT_REGION_SELECTION_EDGE_COLOR,
        )
        self.assertEqual(
            settings.display.region_selection_opacity,
            DEFAULT_REGION_SELECTION_OPACITY,
        )
        self.assertEqual(settings.import_settings.default_proxy_quality, "Medium")
        self.assertEqual(settings.ui.window_width, 1280)
        self.assertEqual(settings.ui.window_height, 800)
        self.assertEqual(settings.ui.window_mode, "maximized")
        self.assertTrue(settings.ui.remember_window_size)
        self.assertEqual(settings.keybinds.undo, "Ctrl+Z")
        self.assertEqual(settings.keybinds.redo, "Ctrl+Y")
        self.assertEqual(settings.keybinds.rename_selected, "F2")
        self.assertEqual(settings.keybinds.toggle_visibility, "H")
        self.assertEqual(settings.keybinds.isolate_selected, "Shift+H")
        self.assertEqual(settings.keybinds.show_all, "Alt+H")
        self.assertEqual(settings.keybinds.frame_selected, "F")
        self.assertEqual(settings.keybinds.move, "G")
        self.assertEqual(settings.keybinds.rotate, "R")
        self.assertEqual(settings.keybinds.confirm_transform, "Enter")
        self.assertEqual(settings.keybinds.cancel_transform, "Esc")
        self.assertEqual(settings.keybinds.delete_selected, "Delete")
        self.assertEqual(settings.future, {})

    def test_default_app_settings_uses_fresh_future_dict(self) -> None:
        settings = default_app_settings()
        other_settings = default_app_settings()

        settings.future["reserved"] = True

        self.assertEqual(other_settings.future, {})


class SettingsIOTests(unittest.TestCase):
    def test_settings_to_dict_preserves_all_fields(self) -> None:
        settings = _sample_settings()

        self.assertEqual(
            settings_to_dict(settings),
            {
                "version": SETTINGS_VERSION,
                "display": {
                    "show_grid": False,
                    "show_axes": True,
                    "show_normals": True,
                    "show_axis_gizmo": False,
                    "show_viewcube": False,
                    "region_selection_color": "#FF8800",
                    "region_selection_edge_color": "#FFF2CC",
                    "region_selection_opacity": 0.5,
                },
                "import": {
                    "default_proxy_quality": "High",
                },
                "ui": {
                    "window_width": 1440,
                    "window_height": 900,
                    "window_mode": "remembered_size",
                    "remember_window_size": False,
                },
                "keybinds": {
                    "undo": "Ctrl+Alt+Z",
                    "redo": "Ctrl+Alt+Y",
                    "rename_selected": "Ctrl+R",
                    "toggle_visibility": "V",
                    "isolate_selected": "Shift+V",
                    "show_all": "Alt+V",
                    "frame_selected": "F",
                    "move": "G",
                    "rotate": "R",
                    "confirm_transform": "Enter",
                    "cancel_transform": "Esc",
                    "delete_selected": "Delete",
                },
                "future": {
                    "reserved": "ok",
                },
            },
        )

    def test_settings_from_dict_round_trips_to_settings_data(self) -> None:
        settings = _sample_settings()

        self.assertEqual(settings_from_dict(settings_to_dict(settings)), settings)

    def test_settings_from_dict_uses_defaults_for_missing_optional_fields(self) -> None:
        settings = settings_from_dict(
            {
                "version": SETTINGS_VERSION,
                "display": {
                    "show_grid": False,
                },
                "ui": {
                    "window_width": 1600,
                },
            }
        )

        self.assertFalse(settings.display.show_grid)
        self.assertTrue(settings.display.show_axes)
        self.assertFalse(settings.display.show_normals)
        self.assertTrue(settings.display.show_axis_gizmo)
        self.assertTrue(settings.display.show_viewcube)
        self.assertEqual(settings.display.region_selection_color, DEFAULT_REGION_SELECTION_COLOR)
        self.assertEqual(
            settings.display.region_selection_edge_color,
            DEFAULT_REGION_SELECTION_EDGE_COLOR,
        )
        self.assertEqual(
            settings.display.region_selection_opacity,
            DEFAULT_REGION_SELECTION_OPACITY,
        )
        self.assertEqual(settings.import_settings.default_proxy_quality, "Medium")
        self.assertEqual(settings.ui.window_width, 1600)
        self.assertEqual(settings.ui.window_height, 800)
        self.assertEqual(settings.ui.window_mode, "maximized")
        self.assertTrue(settings.ui.remember_window_size)
        self.assertEqual(settings.keybinds.toggle_visibility, "H")
        self.assertEqual(settings.keybinds.undo, "Ctrl+Z")
        self.assertEqual(settings.keybinds.redo, "Ctrl+Y")
        self.assertEqual(settings.future, {})

    def test_settings_from_dict_preserves_keybinds(self) -> None:
        settings = settings_from_dict(
            {
                "version": SETTINGS_VERSION,
                "keybinds": {
                    "undo": "Ctrl+U",
                    "redo": "Ctrl+Shift+U",
                    "rename_selected": "F4",
                    "toggle_visibility": "V",
                    "isolate_selected": "Shift+V",
                    "show_all": "Alt+V",
                    "frame_selected": "A",
                    "move": "M",
                    "rotate": "T",
                    "confirm_transform": "Return",
                    "cancel_transform": "Escape",
                    "delete_selected": "BackSpace",
                },
            }
        )

        self.assertEqual(settings.keybinds.undo, "Ctrl+U")
        self.assertEqual(settings.keybinds.redo, "Ctrl+Shift+U")
        self.assertEqual(settings.keybinds.rename_selected, "F4")
        self.assertEqual(settings.keybinds.toggle_visibility, "V")
        self.assertEqual(settings.keybinds.isolate_selected, "Shift+V")
        self.assertEqual(settings.keybinds.show_all, "Alt+V")
        self.assertEqual(settings.keybinds.frame_selected, "A")
        self.assertEqual(settings.keybinds.move, "M")
        self.assertEqual(settings.keybinds.rotate, "T")
        self.assertEqual(settings.keybinds.confirm_transform, "Return")
        self.assertEqual(settings.keybinds.cancel_transform, "Escape")
        self.assertEqual(settings.keybinds.delete_selected, "BackSpace")

    def test_settings_from_dict_clamps_region_opacity(self) -> None:
        low = settings_from_dict(
            {
                "version": SETTINGS_VERSION,
                "display": {"region_selection_opacity": 0.0},
            }
        )
        high = settings_from_dict(
            {
                "version": SETTINGS_VERSION,
                "display": {"region_selection_opacity": 5.0},
            }
        )

        self.assertEqual(low.display.region_selection_opacity, 0.05)
        self.assertEqual(high.display.region_selection_opacity, 1.0)

    def test_settings_to_dict_accepts_rgb_region_color_tuples(self) -> None:
        settings = default_app_settings()
        settings.display.region_selection_color = (1.0, 0.5, 0.0)  # type: ignore[assignment]
        settings.display.region_selection_edge_color = [255, 255, 255]  # type: ignore[assignment]

        data = settings_to_dict(settings)

        self.assertEqual(data["display"]["region_selection_color"], "#FF8000")  # type: ignore[index]
        self.assertEqual(data["display"]["region_selection_edge_color"], "#FFFFFF")  # type: ignore[index]

    def test_save_and_load_settings_round_trips_json_and_creates_file(self) -> None:
        settings = _sample_settings()

        with TemporaryDirectory() as tmpdir:
            settings_path = Path(tmpdir) / "nested" / "settings.json"

            save_settings(settings, settings_path)

            text = settings_path.read_text(encoding="utf-8")
            raw_data = json.loads(text)
            self.assertTrue(settings_path.exists())
            self.assertTrue(text.startswith("{\n"))
            self.assertIn('\n  "version": 1,', text)
            self.assertEqual(raw_data["import"]["default_proxy_quality"], "High")
            self.assertEqual(raw_data["keybinds"]["toggle_visibility"], "V")
            self.assertEqual(load_settings(settings_path), settings)

    def test_load_settings_missing_file_returns_defaults(self) -> None:
        with TemporaryDirectory() as tmpdir:
            settings_path = Path(tmpdir) / "missing" / "settings.json"

            self.assertEqual(load_settings(settings_path), default_app_settings())

    def test_load_settings_invalid_json_returns_defaults(self) -> None:
        with TemporaryDirectory() as tmpdir:
            settings_path = Path(tmpdir) / "settings.json"
            settings_path.write_text("{broken json", encoding="utf-8")

            self.assertEqual(load_settings(settings_path), default_app_settings())

    def test_load_settings_invalid_shapes_return_defaults(self) -> None:
        invalid_shapes: list[object] = [
            [],
            {"version": False},
            {"version": SETTINGS_VERSION + 1},
            {"display": []},
            {"display": {"show_grid": 1}},
            {"display": {"show_axis_gizmo": 1}},
            {"display": {"show_viewcube": 1}},
            {"display": {"region_selection_color": "cyan"}},
            {"display": {"region_selection_edge_color": "#12XX90"}},
            {"display": {"region_selection_opacity": "0.5"}},
            {"import": []},
            {"import": {"default_proxy_quality": "Ultra"}},
            {"ui": []},
            {"ui": {"window_width": 0}},
            {"ui": {"window_height": "800"}},
            {"ui": {"window_mode": "fullscreen"}},
            {"ui": {"remember_window_size": "yes"}},
            {"keybinds": []},
            {"keybinds": {"toggle_visibility": ""}},
            {"future": []},
        ]

        with TemporaryDirectory() as tmpdir:
            for index, shape in enumerate(invalid_shapes):
                with self.subTest(shape=shape):
                    settings_path = Path(tmpdir) / f"settings-{index}.json"
                    settings_path.write_text(json.dumps(shape), encoding="utf-8")

                    self.assertEqual(load_settings(settings_path), default_app_settings())

    def test_settings_to_dict_rejects_non_settings_data(self) -> None:
        with self.assertRaises(ValueError) as context:
            settings_to_dict(object())  # type: ignore[arg-type]

        self.assertIn("Expected AppSettings", str(context.exception))


if __name__ == "__main__":
    unittest.main()
