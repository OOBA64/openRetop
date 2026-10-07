"""What should the user do next? A pure function of the project state.

The UI shows this as the "Model & Next steps" panel. Keeping the decision logic here
(no Qt) means it is unit-testable and the same advice can be reused by a tour,
the command palette, or a workspace stepper.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from openretop.application.state import AppState


class Stage(str, Enum):
    START = "start"  # no scan loaded
    SCAN = "scan"  # scan loaded, no sections yet
    SECTIONS = "sections"  # sections/curves exist, no surface yet
    SURFACES = "surfaces"  # a BREP surface exists
    EXPORT = "export"  # a built BREP is ready to export


@dataclass(frozen=True)
class GuidanceStep:
    action_id: str
    label: str
    hint: str = ""
    primary: bool = False


@dataclass(frozen=True)
class Guidance:
    stage: Stage
    title: str
    explanation: str
    summary: tuple[str, ...]
    steps: tuple[GuidanceStep, ...]
    cad_note: str = ""


def build_guidance(state: AppState, *, cad_available: bool, has_runtime_brep: bool, selected_curve_count: int = 0) -> Guidance:
    """Describe the project and the sensible next actions."""

    cad_note = "" if cad_available else "CAD kernel (CadQuery) is not installed: surfaces and STEP export are unavailable."
    mesh = state.mesh_object
    if mesh is None:
        return Guidance(
            stage=Stage.START,
            title="Start with a scan",
            explanation="openRetop turns a mesh scan into sections, curves and CAD surfaces you can export as STEP.",
            summary=("Supported files: STL, OBJ, PLY", "You can also drag a scan or project onto this window."),
            steps=(
                GuidanceStep("file.open_model", "Open a scan...", "Choose the file, then its length unit.", primary=True),
                GuidanceStep("file.open_project", "Open a project...", "Continue earlier work."),
            ),
            cad_note=cad_note,
        )

    summary = _summary(state)
    curves = state.curve_collection.curves
    surfaces = state.brep_surface_collection.surfaces

    if surfaces:
        steps = [
            GuidanceStep(
                "file.export_step",
                "Export STEP...",
                "Select the BREP surface in the Scene tree first." if not has_runtime_brep else "Writes the surface in the model's units.",
                primary=has_runtime_brep,
            )
        ]
        if not has_runtime_brep:
            steps.insert(
                0,
                GuidanceStep("surface.rebuild_brep", "Rebuild selected surface", "Surfaces are rebuilt after opening a project.", primary=True),
            )
        steps.append(GuidanceStep("section.add_plane", "Add another section plane", "Cut more sections for the next surface."))
        return Guidance(
            Stage.EXPORT if has_runtime_brep else Stage.SURFACES,
            "Export your surface" if has_runtime_brep else "Rebuild, then export",
            "Your BREP surface is ready for CAD." if has_runtime_brep else "The BREP surface needs rebuilding before it can be exported.",
            summary,
            tuple(steps),
            cad_note,
        )

    if curves:
        two = selected_curve_count >= 2
        return Guidance(
            Stage.SECTIONS,
            "Turn curves into a surface",
            "Select curves in the Scene tree, then build a surface from them.",
            summary,
            (
                GuidanceStep(
                    "surface.editable_brep_loft",
                    "Loft between two curves",
                    "Two curves are selected." if two else "Select two curves in the Scene tree first.",
                    primary=True,
                ),
                GuidanceStep("surface.brep_face", "Fill a closed curve", "Select one closed curve first."),
                GuidanceStep("section.add_plane", "Add another section plane", "More sections give you more curves to loft."),
                GuidanceStep("manual_curve.create", "Draw a curve by hand", "For edges the sections miss."),
            ),
            cad_note,
        )

    return Guidance(
        Stage.SCAN,
        "Cut sections through the scan",
        "Each section becomes a curve you can loft into a surface.",
        summary,
        (
            GuidanceStep("section.add_plane", "Add a section plane", "Planes are cutting positions; move them in the Properties panel."),
            GuidanceStep("section.compute", "Compute section", "Slices the scan at the active plane.", primary=True),
            GuidanceStep("region.start", "Select a surface region", "Click a smooth area of the scan to pick it."),
            GuidanceStep("manual_curve.create", "Draw a curve by hand", "Click points on the scan."),
        ),
        cad_note,
    )


def _count(number: int, noun: str) -> str:
    return f"{number} {noun}{'' if number == 1 else 's'}"


def _summary(state: AppState) -> tuple[str, ...]:
    mesh = state.mesh_object
    assert mesh is not None
    lines = [mesh.name]
    triangles = int(mesh.source_triangle_count or len(mesh.source_mesh.triangles))
    lines.append(f"{triangles:,} triangles, units: {state.units}" + (" (assumed)" if state.units_assumed else ""))
    if mesh.source_bounds_min is not None and mesh.source_bounds_max is not None:
        size = [float(value) for value in (mesh.source_bounds_max - mesh.source_bounds_min)]
        lines.append(f"Size: {size[0]:.4g} x {size[1]:.4g} x {size[2]:.4g} {state.units}")
    counts = []
    if state.section_collection.results:
        counts.append(_count(len(state.section_collection.results), "section"))
    curves = state.curve_collection.curves
    if curves:
        counts.append(_count(len(curves), "curve"))
    if state.brep_surface_collection.surfaces:
        counts.append(_count(len(state.brep_surface_collection.surfaces), "BREP surface"))
    if counts:
        lines.append(", ".join(counts))
    return tuple(lines)
