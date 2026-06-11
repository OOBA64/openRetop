from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from settings.settings_data import (
    SETTINGS_VERSION,
    AppDisplaySettings,
    AppImportSettings,
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
        ),
        import_settings=AppImportSettings(
            default_proxy_quality="High",
        ),
        ui=AppUiSettings(
            window_width=1440,
            window_height=900,
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
        self.assertEqual(settings.import_settings.default_proxy_quality, "Medium")
        self.assertEqual(settings.ui.window_width, 1280)
        self.assertEqual(settings.ui.window_height, 800)
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
                },
                "import": {
                    "default_proxy_quality": "High",
                },
                "ui": {
                    "window_width": 1440,
                    "window_height": 900,
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
        self.assertEqual(settings.import_settings.default_proxy_quality, "Medium")
        self.assertEqual(settings.ui.window_width, 1600)
        self.assertEqual(settings.ui.window_height, 800)
        self.assertEqual(settings.future, {})

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
            {"import": []},
            {"import": {"default_proxy_quality": "Ultra"}},
            {"ui": []},
            {"ui": {"window_width": 0}},
            {"ui": {"window_height": "800"}},
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
