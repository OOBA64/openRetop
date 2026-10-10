# Human-use audit, 2026-10-10

Owner request: "test every single feature, and every single workflow for human use
compatibility ... pretend you are a human coming from some other enterprise reverse
engineering software, would this program be useable to you? Would it be useable if you had
no experience at all? ... write a priority task list to address these concerns."

The resulting tasks are **Track H** in [TASKS.md](TASKS.md). This file has the evidence.

## Method

Earlier checks called the window's handlers directly. That is how the manual trim bug got
through: the handler worked, but no real click ever reached it. For this pass every
workflow was driven through the real window with real input
([scripts/usability](../../scripts/usability/README.md)):

- mouse press, move, release and wheel events go to the 3D view;
- toolbar, tab and panel buttons are clicked as widgets;
- keys are typed into whatever has the focus;
- the units question and confirmations are answered by clicking their buttons;
- the status line, tool hint and panel text are read after every step and screenshots are kept.

Scenarios:

| Run | Workflow |
|---|---|
| s1 | First launch, Open Scan + units, orbit/pan/zoom, view keys, pick, Move with a typed value, section, region, measure, save, reopen |
| s2 | Bracket: fit every face by clicking it, Trim into a solid, Compare, Export STEP |
| s3 | Housing in Solid: Section Sketch + Extrude, History edit, 3D Sketch drawn and dimensioned with mouse and panel, region extrude, undo |
| s4 | Surface Sketch closed loop, Face From Curves, Loft from two sections, every menu |
| s5 | The owner's scans: oil pan (fit the flange, Section Sketch) and TurboBumper (794k triangles, Surface Sketch) |
| s6 | Command palette searches, Preferences, Delete, undo/redo chain, Help, F1 |
| trim | Fit a plane, Manual, Cut Line, two clicks, Enter, click the overhang, Apply |
| resize | Side arrow drag, corner arrow drag, click an arrow and type a distance |

## Bugs found and fixed in this pass

| Commit | What a user hit |
|---|---|
| 24e6a0e | **Manual trim did nothing.** Every Cut Line click was taken for a drag, because a release only counted as a click when the press could select scene objects. Also: one trimmed surface was "sewn" into a "Shell with 6 open edges"; dropped pieces were nearly invisible. |
| 1ff1bd6 | A resize arrow jumped by the grab offset on the first move (a 15 mm drag moved 12 mm). Also added: corner arrows, click-and-type distances, arrows kept on screen. |
| 0508939 | **Export wrote a hidden plane** instead of the trimmed solid, because the last fitted surface stayed selected after Trim hid it. "Area too small" now says what to do. Dropped trim pieces are calmer at 25% red. |
| 545b624 | **Typing a dimension and pressing Enter finished the whole 3D Sketch.** An extrude that changed nothing still reported a volume. |
| c8d07d7 | **A fresh Surface Sketch curve could not be closed** by clicking its first point, although the hint said so. The palette called Split Surfaces "Automatic Trim". |

Each fix has a regression test that fails on the old code.

## What works for a person today

These were verified with real input. The figures come from the runs:

- **Opening a scan:** asks for its units. The oil pan opens in 1.7 s and the bumper in 10 s.
- **Fitting surfaces:** Fit Surface, click a face, then Create. Bracket faces come out within 0.02 mm RMS.
- **Resizing:** arrows on sides and corners; typed values are exact (−5 gives −5.000); undo works.
- **Manual trim:** two clicks across the overhang, Enter, click the overhang, Apply. The result was one 7149 mm² surface.
- **Trim into a solid, Compare, Export STEP:** the bracket becomes one valid solid, and Compare gives RMS 0.020 mm.
- **3D Sketch:** dimensions typed in the panel, region picking, extrude new/join/cut, History edit, undo. Constraints and degrees of freedom are shown.
- **Help while working:** a tool hint on the canvas, a Next steps panel, and tooltips that say why a command is disabled.
- **Ctrl+K palette:** finds every command the app has.

## Persona 1: an experienced Design X / QuickSurface / ExModel user

The expected first ten minutes are import, clean the mesh, align to the world, segment, then
fit regions. In openRetop:

1. **Import works**, but there is **no mesh cleanup**: no deleting stray pieces, filling
   holes, decimating or smoothing. Palette searches for "decimate", "fill holes" and "align"
   find nothing.
2. **No alignment.** This is the first real stop. Section planes, Section Sketch planes and
   3D Sketch planes are all world planes (XY/XZ/YZ plus an offset). On a scan that is not
   already square to the world, none of those planes lies on the part. Design X users expect
   an Align wizard: plane, axis, point, or 3-2-1 from fitted features.
3. **No automatic segmentation in the app.** The kernel has one (RE-03, region growing that
   classifies plane, cylinder and freeform), but no button reaches it. Picking faces one
   click at a time works on the bracket. On the oil pan, Auto chose **freeform for the
   flange**, which is a plane, and small holes are hard to hit.
4. **Fitted primitives cannot be typed in or constrained.** QuickSurface's plane dialog has
   Type In, From another plane, Middle plane and Constrain normal; openRetop has none of
   them. A cylinder's radius cannot be rounded to 8.00, and an axis cannot be made
   perpendicular to a datum. This is exactly the design intent an RE user is paid to recover.
5. **A fitted plane is a large square:** 1.3× the selection's diagonal, turned to OCC's
   default axes rather than the face's edges, and opaque. On a long narrow face it covers
   the scan. The resize arrows fix it by hand, but every plane needs that.
6. **Trim, sew and Compare work.** The messages use kernel words ("shell", "open edges")
   and the open edges are not shown, so it is unclear which face is missing.
7. **The Solid workspace is thin for real parts.** There is extrude only: no fillet,
   chamfer, revolve or mirror. The History list has no timeline bar or roll-back. Arcs are
   centre-and-ends only; there are no 3-point or tangent arcs and no trim, extend or offset
   in sketches.
8. **Deviation is basic:** a colour map and RMS, but no probe to read the value under the
   pointer and no control over the legend range.
9. **Navigation is fixed.** It cannot be switched to a SolidWorks/Design X or Fusion mouse
   mapping, so muscle memory fights the app.

**Verdict:** usable for a prismatic demo part (bracket to STEP in a few minutes). Not yet
usable for paid work. The walls come within the first 20 minutes: alignment, primitives
with intent (type-in, constraints), and fillets.

## Persona 2: no reverse engineering or CAD experience

1. **Getting started is good.** Launch says to open a scan, the units question is clear,
   and Next steps suggests a tool.
2. **Three sketch tools with similar names:**
   - Surface Sketch (curves on the scan, Surface workspace);
   - Section Sketch (a profile fitted to a cut, Solid workspace);
   - 3D Sketch (a constrained 2D sketch on a plane, Solid workspace).

   A newcomer cannot tell from the names which one to use.
3. **The menus do not match the toolbar.**
   - Create holds only "Add Section Plane" and "Region Select".
   - Modify mixes transforms, eleven axis and plane locks, section commands and Surface Sketch.
   - Edit has "Select Section Plane", "Delete Mesh" and "Toggle Mesh Visibility" next to the
     generic Delete and Hide.
4. **There is no help.** The Help menu holds only About, and F1 does nothing. There is no
   keys cheat sheet, sample scan or tutorial.
5. **Undo with nothing left to undo says nothing.** The status line keeps the previous
   "Undid Compute Section", which reads as if it undid again.
6. **Failure messages explain the kernel, not the next step.** For example: "Shell with
   6 open edges" and "area too small" (that one is fixed now).
7. **Panels are dense.** Hint paragraphs sit above every control group.
8. **There is no autosave.** A crash or a wrong Discard loses the session.
9. **The first Fit waits about 10 s** while the kernel worker starts. Later fits take under 1 s.

**Verdict:** with the hints, a newcomer can open a scan, fit faces, trim and export the
bracket. When something does not work, they have no help to turn to, and the vocabulary
(three sketches, sew, shell) gets in the way.

## Smaller findings

- **Section Sketch on the oil pan:** the automatic tolerance came from the scan's
  coarseness: 1.5 mm, which allowed 4.7 mm maximum deviation. The bad segments are not
  marked.
- **Fitting a face that is already fitted gives no warning;** it makes a duplicate surface.
- **Face From Curves on the housing top** (a loop crossing the top's edges) gave RMS
  0.168 mm and max 1.126 mm. It is correct for that loop, but nothing tells the user that
  the loop crossed an edge.
- **Palette searches for "fillet" return "Section Sketch"** (its description mentions
  corner radii). That is good, but it hints that users will look for fillet and not find it.
