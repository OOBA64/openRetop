# Reference behaviour: QuickSurface, Fusion, Rhino 8

What the tools openRetop is measured against actually do: parameters, defaults, workflows and
messages, written as behaviour specs to build from (no third-party code). Collected 2026-10-11.

| File | Use it for |
|---|---|
| [QUICKSURFACE.md](QUICKSURFACE.md) | The workflow openRetop copies: mesh prep, selection, primitives and Auto Constrain, alignment, section sketches, trim, freeform, Compare / Straightness |
| [FUSION.md](FUSION.md) | Sketching, the constraint solver, AutoConstrain, solid features, timeline and parameters, Fusion's mesh-to-CAD tools |
| [fusion/api_sketch.md](fusion/api_sketch.md), [fusion/api_features.md](fusion/api_features.md) | Digests of Fusion's public API: grep, don't read |
| [RHINO.md](RHINO.md) | ShrinkWrap, QuadRemesh, SubD, Patch / NetworkSrf, ReduceMesh and mesh checks, deviation reports |

Where they feed the Track H tasks ([TASKS.md](../TASKS.md)):

| Task | Read |
|---|---|
| H-01 Align (done; extras) | QUICKSURFACE §4.2 |
| H-02 primitive type-in / constraints | QUICKSURFACE §4.1 (Auto Constrain tolerances, constraint drop-down, plane modes) |
| H-04 segmentation | FUSION §6 (Fast / Accurate face groups), RHINO §6 |
| H-07 scan cleanup | QUICKSURFACE §2, RHINO §5 |
| H-14 Section Sketch | QUICKSURFACE §5, FUSION §6 (per-span refit) and §3 (AutoConstrain) |
| H-15 / H-16 / H-17 fillet, revolve, mirror, timeline | FUSION §4, §5 |
| H-19 deviation tools | QUICKSURFACE §8, RHINO §8 |

QuickSurface ships sample scans with matching CAD (QUICKSURFACE §11); check their licence before
adding any to the repo.
