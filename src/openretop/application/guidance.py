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
    SCAN = "scan"  # scan loaded, nothing modelled yet
    CURVES = "curves"  # sketch curves or sketches, no surface or body yet
    MODEL = "model"  # surfaces or bodies exist
    EXPORT = "export"  # a closed body is ready to export


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


def build_guidance(state: AppState, *, selected_curve_count: int = 0) -> Guidance:
    """Describe the project and the sensible next actions."""

    mesh = state.mesh_object
    if mesh is None:
        return Guidance(
            stage=Stage.START,
            title="Start with a scan",
            explanation="openRetop turns a mesh scan into CAD surfaces and solids you can export as STEP.",
            summary=("Supported files: STL, OBJ, PLY", "You can also drag a scan or project onto this window."),
            steps=(
                GuidanceStep("file.open_model", "Open a scan...", "Choose the file, then its length unit.", primary=True),
                GuidanceStep("file.open_project", "Open a project...", "Continue earlier work."),
            ),
        )

    summary = _summary(state)
    model = state.model
    bodies = [entity for entity in model.entities if entity.is_body]
    if bodies:
        return Guidance(
            Stage.EXPORT,
            "Check it and export",
            "A body is ready. Compare it with the scan, then export it.",
            summary,
            (
                GuidanceStep("model.compare", "Compare with the scan", "Colours the scan by its distance to the model.", primary=True),
                GuidanceStep("file.export_model", "Export STEP...", "Writes the selected or visible model."),
            ),
        )
    if model.entities:
        return Guidance(
            Stage.MODEL,
            "Join the surfaces into a body",
            "Trim the surfaces against each other and sew them; closed, they make a solid.",
            summary,
            (
                GuidanceStep("model.extend", "Extend surfaces", "Grow them past their edges so they meet."),
                GuidanceStep("model.trim", "Trim and sew", "Keeps the pieces on the scan.", primary=True),
                GuidanceStep("model.fit_surface", "Fit another surface", "Select an area of the scan."),
            ),
        )
    if model.sketch.curves:
        two = selected_curve_count >= 2
        return Guidance(
            Stage.CURVES,
            "Turn curves into surfaces",
            "Loft through curves, or make a face inside a loop of curves.",
            summary,
            (
                GuidanceStep("model.loft", "Loft", "Two curves are selected." if two else "Select two or more curves first.", primary=two),
                GuidanceStep("model.sketch", "Surface Sketch", "Draw more curves; Face From Curves fills a loop.", primary=not two),
                GuidanceStep("model.fit_surface", "Fit Surface", "Or fit a surface straight to an area of the scan."),
            ),
        )
    return Guidance(
        Stage.SCAN,
        "Model the part",
        "Surface: curves on the scan and fitted surfaces (organic shapes). Solid: sketches on planes, extruded.",
        summary,
        (
            GuidanceStep("model.fit_surface", "Fit Surface", "Select an area of the scan; a surface is fitted to it.", primary=True),
            GuidanceStep("model.sketch", "Surface Sketch", "Click points on the scan; curves follow its surface."),
            GuidanceStep("model.section_sketch", "Section Sketch", "Cut the scan with a plane; lines and arcs are fitted."),
            GuidanceStep("measure.distance", "Measure the scan", "Check its size against the real part."),
        ),
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
    if state.model.sketch.curves:
        counts.append(_count(len(state.model.sketch.curves), "curve"))
    surfaces = [entity for entity in state.model.entities if not entity.is_body]
    bodies = [entity for entity in state.model.entities if entity.is_body]
    if surfaces:
        counts.append(_count(len(surfaces), "surface"))
    if bodies:
        counts.append(_count(len(bodies), "body"))
    if counts:
        lines.append(", ".join(counts))
    return tuple(lines)
