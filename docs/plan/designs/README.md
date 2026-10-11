# Design studies for the Track H P0 tasks

Written on 2026-10-10 by reading the code at commit 233d271 (nothing was changed while writing
them). File and line references drift as the code moves; the function names hold.

| File | Task | State |
|---|---|---|
| [H-02_primitive_type_in.md](H-02_primitive_type_in.md) | H-02 Type In and constraints for fitted primitives | to do |
| [H-04_H-07_segmentation_and_cleanup.md](H-04_H-07_segmentation_and_cleanup.md) | H-04 automatic segmentation, H-07 scan cleanup | to do |
| [H-05_help.md](H-05_help.md) | H-05 help (F1, Getting Started, Mouse & Keys); also H-06 | H-05 to do; H-06 done (d4555d4), as designed except: surfaces running past the scan are named instead of an edge count, and nothing is kept automatically to fill a gap |

H-01 (Align to World) was built from a fourth study (a950e3a): the three-click path. Auto and
editing a sketch turned off the world planes are still to come.
