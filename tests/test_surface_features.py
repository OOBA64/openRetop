from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from project.project_data import (
    ProjectFourBoundaryPatchFeature,
    ProjectLoftFeature,
    default_project_data,
)
from app.app_state import AppState
from project.project_io import load_project, save_project
from project.project_state import project_from_app_state
from surfaces.four_boundary_feature import (
    FourBoundaryPatchFeatureCollection,
    FourBoundaryPatchFeatureRecord,
    add_four_boundary_feature,
    mark_four_boundary_features_dirty_for_curve,
)
from surfaces.loft_feature import (
    LoftFeatureCollection,
    LoftFeatureOptions,
    LoftFeatureRecord,
    add_loft_feature,
    loft_feature_for_brep_surface,
    mark_loft_features_dirty_for_curve,
)


class EditableSurfaceFeatureTests(unittest.TestCase):
    def test_clearing_selection_does_not_delete_feature_records(self) -> None:
        state = AppState()
        feature = LoftFeatureRecord(
            id="loft-feature-a",
            name="Editable Loft 1",
            options=LoftFeatureOptions(source_curve_ids=["a", "b"]),
        )
        state.loft_feature_collection.features.append(feature)

        state.clear_selection()

        self.assertEqual(state.loft_feature_collection.features, [feature])

    def test_loft_feature_stores_options_and_links_brep(self) -> None:
        collection = LoftFeatureCollection()
        feature = LoftFeatureRecord(
            id="loft-feature-a",
            name="Editable Loft 1",
            options=LoftFeatureOptions(
                source_curve_ids=["curve-a", "curve-b"],
                preserve_corners=True,
                cap_start=True,
            ),
            brep_surface_id="brep-a",
            last_build_success=True,
            last_build_reason="Built.",
        )

        add_loft_feature(collection, feature)

        self.assertIs(loft_feature_for_brep_surface(collection, "brep-a"), feature)
        self.assertEqual(feature.options.source_curve_ids, ["curve-a", "curve-b"])
        self.assertTrue(feature.options.cap_start)

    def test_source_curve_edit_marks_linked_loft_dirty(self) -> None:
        collection = LoftFeatureCollection(
            features=[
                LoftFeatureRecord(
                    id="loft-feature-a",
                    name="Editable Loft 1",
                    options=LoftFeatureOptions(source_curve_ids=["curve-a", "curve-b"]),
                    brep_surface_id="brep-a",
                    last_build_success=True,
                )
            ]
        )

        changed = mark_loft_features_dirty_for_curve(collection, "curve-b")

        self.assertEqual(changed, collection.features)
        self.assertTrue(changed[0].metadata["loft_feature_dirty"])
        self.assertEqual(changed[0].metadata["source_edit_revision"], 1)

    def test_four_boundary_feature_marks_dirty_after_source_edit(self) -> None:
        collection = FourBoundaryPatchFeatureCollection()
        feature = FourBoundaryPatchFeatureRecord(
            id="patch-feature-a",
            name="Four-Curve Patch 1",
            source_curve_ids=["bottom", "right", "top", "left"],
            preview_surface_id="surface-a",
        )
        add_four_boundary_feature(collection, feature)

        changed = mark_four_boundary_features_dirty_for_curve(collection, "right")

        self.assertEqual(changed, [feature])
        self.assertTrue(feature.metadata["four_boundary_feature_dirty"])

    def test_project_save_load_preserves_editable_features(self) -> None:
        project = default_project_data()
        project.loft_features = [
            ProjectLoftFeature(
                id="loft-feature-a",
                name="Editable Loft 1",
                options={
                    "source_curve_ids": ["curve-a", "curve-b"],
                    "preserve_corners": True,
                    "cap_start": True,
                    "cap_end": True,
                    "rebuild_on_source_edit": True,
                    "overbuild_enabled": True,
                    "overbuild_amount": 0.2,
                    "overbuild_u_start": 0.15,
                    "overbuild_u_end": 0.25,
                    "overbuild_v_start": 0.1,
                    "overbuild_v_end": 0.3,
                    "show_overbuild_handles": True,
                },
                brep_surface_id="brep-a",
                preview_surface_id=None,
                last_build_success=True,
                last_build_reason="Built.",
                last_build_warnings=[],
                metadata={"loft_feature_dirty": False},
            )
        ]
        project.four_boundary_patch_features = [
            ProjectFourBoundaryPatchFeature(
                id="patch-feature-a",
                name="Four-Curve Patch 1",
                source_curve_ids=["bottom", "right", "top", "left"],
                preserve_corners=True,
                match_directions=True,
                fill_method="coons_preview",
                brep_surface_id=None,
                preview_surface_id="surface-a",
                last_build_status="Built.",
                metadata={"four_boundary_feature_dirty": False},
            )
        ]

        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "features.openretop"
            save_project(project, path)
            loaded = load_project(path)

        self.assertEqual(loaded.loft_features, project.loft_features)
        self.assertEqual(
            loaded.four_boundary_patch_features,
            project.four_boundary_patch_features,
        )

    def test_project_export_includes_runtime_feature_collections(self) -> None:
        loft_collection = LoftFeatureCollection(
            features=[
                LoftFeatureRecord(
                    id="loft-feature-a",
                    name="Editable Loft 1",
                    options=LoftFeatureOptions(
                        source_curve_ids=["curve-a", "curve-b"],
                        cap_end=True,
                    ),
                    brep_surface_id="brep-a",
                    last_build_success=True,
                    last_build_reason="Built.",
                )
            ]
        )
        patch_collection = FourBoundaryPatchFeatureCollection(
            features=[
                FourBoundaryPatchFeatureRecord(
                    id="patch-feature-a",
                    name="Patch 1",
                    source_curve_ids=["a", "b", "c", "d"],
                    preview_surface_id="surface-a",
                )
            ]
        )

        project = project_from_app_state(
            mesh_object=None,
            proxy_quality="Medium",
            show_grid=True,
            show_axes=True,
            show_normals=False,
            section_axis="Z",
            section_offset=0.0,
            show_section_plane=False,
            loft_feature_collection=loft_collection,
            four_boundary_feature_collection=patch_collection,
        )

        self.assertEqual(project.loft_features[0].id, "loft-feature-a")
        self.assertEqual(
            project.loft_features[0].options["source_curve_ids"],
            ["curve-a", "curve-b"],
        )
        self.assertTrue(project.loft_features[0].options["cap_end"])
        self.assertTrue(project.loft_features[0].options["overbuild_enabled"])
        self.assertAlmostEqual(
            project.loft_features[0].options["overbuild_u_start"],
            0.10,
        )
        self.assertEqual(
            project.four_boundary_patch_features[0].source_curve_ids,
            ["a", "b", "c", "d"],
        )


if __name__ == "__main__":
    unittest.main()
