# Review of the "revised roadmap" (renderer-neutral / multi-viewport direction)

Source: the ChatGPT roadmap document supplied with the rework request.
Decisions below are mine; the task IDs refer to [TASKS.md](TASKS.md).

## What it gets right (adopted)

| Idea | Verdict |
|---|---|
| The project holds the truth; viewports are disposable presentation caches | **Adopt, already true.** `SceneSnapshot` (`viewer/scene_types.py`) is immutable and `scene_types`/`scene_builder` import no VTK. Keep it that way. |
| Share IDs and `CameraState`, never renderer objects | **Adopt.** `CameraRequest` and the stable scene IDs already exist; add an explicit `CameraState` when a second view needs it (R-04). |
| Capability model instead of pretending renderers are equal | **Adopt** (R-03). Cheap and prevents a leaky abstraction. |
| Stable topology IDs for BREP faces/edges, mapped to tessellation ranges | **Adopt, and make it the centre of the CAD plan** (R-05). It is useful with *any* renderer. |
| Keep CAD-kernel API and viewport API separate | **Adopt.** `infrastructure/cad_adapter.py` already is the kernel seam. |
| Mesh/scan tools stay VTK-centric; repair, alignment, print-prep as workspaces | **Adopt** as the long-term shape (R-10..R-12). |
| Don't rewrite the working viewport; don't put renderer state in project files | **Adopt.** |

## Where I disagree or re-sequence

### 1. A native OCCT (AIS) viewport is a spike, not a phase
Phase C/D (Tasks 95-104) commits to a second renderer, a second GL context in the
same window, a second Qt event translation layer, and platform-specific window
embedding. Checked here: the `cadquery-ocp` Windows wheel does ship
`AIS`, `V3d`, `OpenGl`, `Graphic3d`, `SelectMgr` and `WNT`, but **no `Xw` or `Cocoa`**,
so Linux/macOS embedding is unproven. I have not tried to embed a `V3d_View` in
PySide6, and nobody should assume it is cheap.

Most of what the roadmap wants from OCCT is *topological picking*: "this is face 42,
this is an edge". That does not need AIS. With stable topology IDs (R-05) VTK can
carry a per-triangle `face_id` cell array and per-polyline `edge_id` array and pick
through `vtkCellPicker`. That gives native-feeling face/edge/vertex selection,
highlighting and sewing workflows with the renderer we already ship and test.

**Decision:** do R-05 (topology IDs + VTK face/edge picking) first. Run the OCCT
viewport as a **time-boxed spike (R-07)** with a written go/no-go:
go only if VTK face/edge picking proves inadequate for fillet/trim selection *and*
a `V3d_View` embeds in PySide6 on Windows and Linux with no GL-context conflict.
Until then no Task 95-104 work is scheduled.

### 2. "Nothing visibly changes" for five tasks is the wrong order
Tasks 90-94 are an invisible refactor. The stated goal of this project is that CAD
should be *intuitive*; the current UI has serious discoverability problems
([UX_AUDIT.md](UX_AUDIT.md)). Those are cheaper than renderer work and benefit every
user immediately. **UX foundations (Track U) go first**; the neutral viewport
contract (R-01, R-02) proceeds in parallel as small extractions that keep tests green,
and is not allowed to block UX tasks.

### 3. Workspaces should select *tools*, not renderers
The roadmap's workspace table maps workspaces to renderers. For users the useful
meaning of a workspace is: which tools are on the toolbar, which panel is shown, which
scene categories are expanded, and what the next step is. The renderer is a
secondary, mostly invisible setting. **Decision:** workspaces are
Scan -> Sections -> Curves -> Surfaces -> Export (UX-10); renderer choice stays an
advanced per-viewport option (R-08) and is never required to use a workspace.

### 4. build123d vs CadQuery vs raw OCP
The real kernel work in this repository is already raw OCP (`Geom_BSplineCurve`
edges, `BRepOffsetAPI_ThruSections` through CadQuery's `Solid.makeLoft`).
CadQuery is used for shape wrappers and STEP export. A third API adds a dependency
and a migration for no feature we are blocked on. **Decision:** stay on
CadQuery/OCP behind the existing `cad_adapter`; revisit only if a specific missing
capability (e.g. a robust sewing or trim API) is found (R-13).

### 5. The roadmap omits the things users hit first
Not mentioned anywhere: undo coverage for every operation, autosave/crash recovery,
large-scan behaviour (>1M triangles), region selection on the *source* mesh (today it
runs on a decimated display proxy), multiple regions, units, and a first-run
experience. Several of these are now in Track E/U of the task list.

### 6. Dual view is worth doing, but with two VTK views first
Split view for scan-vs-reconstruction is a genuinely good reverse-engineering feature.
Two synchronized VTK viewports (shared `CameraState` + shared selection IDs) deliver
it without a second renderer; an OCCT pane can slot into the same host later (R-09).

## Resulting order

1. **Track U (UX foundations)** and **Track E (engineering debt)** - start now.
2. **R-01..R-05** - viewport host/backend contract, VTK extraction, capabilities,
   `CameraState`, BREP render items + topology IDs. Small steps, behaviour unchanged.
3. **R-06 / R-09** - face/edge picking in VTK, split view with two VTK viewports.
4. **R-07** - OCCT viewport spike with an explicit go/no-go.
5. **R-10..R-12** - repair, alignment, print-prep workspaces; **R-13** CAD depth
   (guide rails, trims, sewing, booleans).

## Acceptance of "82G"
The roadmap asks for a final combined viewport acceptance (82G) before new
architecture. 82F landed; the real-Windows viewport tests were run during the rework
(5 of 6 pass, 1 navigation-widget pixel assertion fails on this display and also fails
on the original 82F commit). That test needs a DPI-independent assertion (E-09); I do
not treat it as blocking.
