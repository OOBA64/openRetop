# openRetop V3 project-format baseline

## Status and authority

This document records the project-file contract at the start of Task 75. It is
the compatibility baseline for the V3 refactor; it does not introduce a new
format. The executable authority remains:

- `src/project/project_data.py` for the in-memory records and defaults;
- `src/project/project_io.py` for JSON encoding, decoding, and validation;
- `src/project/project_state.py` for application-state export; and
- the restore path in `src/app/main_window.py` for application behavior after
  decoding.

Existing `.openretop` files with `version: 1` must continue to load throughout
V3. Moving code between layers must not silently reinterpret any field recorded
here.

## Physical representation

- A project is one UTF-8 JSON text file. It is not a ZIP/container and contains
  no embedded mesh or CAD payload.
- The conventional extension is `.openretop`. The serializer and loader do not
  enforce it; the current tests intentionally permit a `.json` path.
- `save_project()` writes two-space-indented JSON with `ensure_ascii=False` and
  one trailing newline.
- Saving writes directly to the destination path. There is currently no
  temporary-file/atomic-replace protocol and no backup file.
- Object key order follows the serializer's insertion order but is not a
  semantic contract.
- `version` is an integer schema discriminator, currently exactly `1`.
  A missing version defaults to `1`; booleans are not accepted as integers;
  every explicit value other than integer `1` is rejected.
- Python's standard `json` implementation is used with its defaults. The field
  validators do not currently reject non-finite floats, so `NaN`/infinity are a
  known portability risk even though they are not valid interoperable JSON.

## Top-level version 1 schema

Every non-feature key below is emitted on save. Missing keys are accepted on
load and receive the stated default. `null` is accepted in place of an omitted
`transform`, `display`, or legacy `section` object and for collection fields
whose collection parser treats `null` as empty.

| Key | JSON shape | Default | Meaning |
| --- | --- | --- | --- |
| `version` | integer | `1` | Exact project schema version. |
| `name` | string | `"Untitled Project"` | Logical project name. The current UI exporter always supplies this default rather than deriving a name from the file path. |
| `mesh_path` | string or `null` | `null` | External source-mesh reference; mesh bytes are not embedded. |
| `mesh_name` | string or `null` | `null` | User-visible mesh name. |
| `mesh_visible` | boolean | `true` | Mesh visibility. |
| `transform` | object | identity/default object | Mesh object transform, detailed below. |
| `display` | object | default display object | Project display choices, detailed below. |
| `section` | object | default legacy section object | Legacy single-section controls and fallback values. |
| `section_planes` | array | `[]` | Stored section-plane records. |
| `active_section_plane_id` | string or `null` | `null` | Preferred active section plane. |
| `section_results` | array | `[]` | Stored section polylines. |
| `curves` | array | `[]` | Stored fitted/manual/derived curves. |
| `surfaces` | array | `[]` | Parametric/preview surface records. |
| `brep_surfaces` | array | `[]` | Rebuildable BREP record descriptors, not CAD bodies. |
| `loft_features` | array | `[]` | Editable loft feature records. Omitted by the serializer when empty. |
| `four_boundary_patch_features` | array | `[]` | Four-boundary feature records. Omitted by the serializer when empty. |

Unknown top-level keys are ignored when loading and are not retained when the
project is saved again. This is not a lossless forward-compatible reader.

### `transform`

| Key | Shape | Default | Validation/meaning |
| --- | --- | --- | --- |
| `location` | three numbers | `[0, 0, 0]` | Object location. |
| `rotation` | three numbers | `[0, 0, 0]` | Rotation values in the application's existing convention. |
| `scale` | number | `1.0` | Uniform scale; required to be greater than zero. |
| `origin` | three numbers | `[0, 0, 0]` | Object transform origin/pivot. |

The project stores the values, not a 4x4 matrix. The application reconstructs
the transform matrix during restore.

### `display`

| Key | Shape | Default | Validation/meaning |
| --- | --- | --- | --- |
| `proxy_quality` | string | `"Medium"` | Display-mesh proxy-quality label. The UI normalizes it on use. |
| `show_grid` | boolean | `true` | Grid visibility. |
| `show_axes` | boolean | `true` | Axes visibility. |
| `show_normals` | boolean | `false` | Format-level normals flag. The current UI save and restore paths force this to `false`. |
| `colors` | object of string to string | `{}` | Display-color overrides. Only `#RRGGBB` values survive decoding; accepted values are uppercased. Invalid entries and a non-object value are ignored as an empty/partial map. |

`project_from_dict()` retains every syntactically valid color key. The UI
restore path applies only names in its known `DISPLAY_COLOR_FIELDS`, so an
unknown valid color key does not survive a full UI load/save cycle.

### Legacy `section`

| Key | Shape | Default | Validation/meaning |
| --- | --- | --- | --- |
| `axis` | string `X`, `Y`, or `Z` | `"Z"` | Case-insensitive on input and normalized to uppercase. |
| `offset` | number | `0.0` | Axis offset. |
| `show_plane` | boolean | `false` | Legacy single-plane visibility. |

When `section_planes` is missing or empty, the application creates one section
plane from this legacy object. This fallback is the key compatibility path for
early version 1 files and must remain intact.

## Collection record schemas

IDs must be non-empty and unique within each individual collection. The loader
does not require IDs to be globally unique across categories and does not fully
validate references between collections.

### `section_planes[]`

| Key | Shape | Default when missing |
| --- | --- | --- |
| `id` | non-empty string | Required; no usable default. |
| `name` | string | `"Section Plane N"`. |
| `axis` | `X`, `Y`, or `Z` string | Legacy `section.axis`. |
| `offset` | number | Legacy `section.offset`. |
| `visible` | boolean | Legacy `section.show_plane`. |
| `origin` | three numbers | Derived from `axis` and `offset`. |
| `normal` | three numbers | Positive unit axis vector derived from `axis`. |

Provided origins and normals are shape/type checked but are not normalized or
checked for a nonzero magnitude at this layer. Arbitrary oriented planes are
represented by explicit `origin` and `normal` while retaining the legacy
axis/offset fields.

### `section_results[]`

| Key | Shape | Default when missing |
| --- | --- | --- |
| `id` | non-empty string | Required. |
| `name` | string | `"Section N"`. |
| `plane_id` | string | Empty string. |
| `axis` | `X`, `Y`, or `Z` string | `"Z"`. |
| `offset` | number | `0.0`. |
| `visible` | boolean | `true`. |
| `plane_origin` | three numbers | Derived from `axis`/`offset`. |
| `plane_normal` | three numbers | Derived from `axis`. |
| `is_arbitrary_plane` | boolean | `false`. |
| `polylines` | array of arrays of 3D points | `[]`. |
| `segment_count` | integer | `0`. |

On application restore, a section result whose `plane_id` is absent from the
restored plane collection is skipped. A malformed runtime result that the
section collection rejects is also skipped by the current adapter.

### `curves[]`

| Key | Shape | Default when missing |
| --- | --- | --- |
| `id` | non-empty string | Required. |
| `name` | string | `"Curve N"`. |
| `section_result_id` | string | Empty string. |
| `plane_id` | string | Empty string. |
| `original_points` | array of 3D points | `[]`. |
| `fitted_points` | array of 3D points | `[]`. |
| `mean_error` | number | `0.0`. |
| `max_error` | number | `0.0`. |
| `is_closed` | boolean | `false`. |
| `visible` | boolean | `true`. |
| `point_count` | integer or `null` | Computed as `len(fitted_points)`. |
| `length` | number or `null` | Computed as fitted-polyline length. |
| `endpoint_distance` | number or `null` | Computed from fitted endpoints. |
| `bounding_box_size` | number or `null` | Largest fitted-points AABB dimension. |
| `is_tiny_fragment` | boolean or `null` | Computed from the diagnostics below. |
| `source_section_result_id` | string or `null` | Falls back to `section_result_id`. |
| `source_plane_id` | string or `null` | Falls back to `plane_id`. |
| `metadata` | JSON-safe object | `{}`. |

The current tiny-fragment calculation is true when any of these conditions is
met: fewer than 2 fitted points, polyline length below `0.01`, or largest AABB
dimension below `0.01`.

The raw data/IO layer preserves explicit diagnostics and lineage fields. The UI
restore path creates a `StoredCurve`, upgrades manual-curve storage, and
recomputes diagnostics. A later UI save therefore canonicalizes diagnostics
from geometry. It also exports `source_section_result_id` and `source_plane_id`
from the curve's current primary IDs, so distinct values in those two explicit
lineage fields are not presently guaranteed to survive a full UI load/save
cycle. Lineage stored in `metadata` is preserved.

#### Curve metadata compatibility contract

`metadata` is deliberately open-ended, but it is persisted only when every
value is JSON-safe. Existing metadata families are part of the version 1
compatibility surface. In particular, V3 must preserve:

- manual/editable curve data: `creation_type`, `control_points`,
  `control_points_v2`, `point_types`, `point_type_sources`,
  `corner_angle_threshold_degrees`, `control_point_revision`,
  `corner_detection_revision`, `curve_method`, `sample_count`, `smoothness`,
  `preserve_corners`, and closure state;
- mesh placement/projection data: `snap_to_mesh`, `snap_mode`,
  `snap_triangle_indices`, `snap_normals`, `snap_projection_distances`,
  `keep_curve_on_mesh`, `source_mesh_name`, projection counts/distances,
  failed indices, warnings, backend, and index/query timing;
- work-plane and lineage data: `work_plane_type`,
  `source_section_plane_id`, `source_curve_ids`, source creation types, and
  repair/rebuild/projection lineage; and
- region-boundary data carried by editable curves, including boundary counts,
  closure, perimeter, and region/source identifiers.

Old polyline/manual metadata is upgraded by the existing manual-curve parser and
`ensure_manual_curve_storage()`. Hidden legacy Hybrid and Catmull-Rom method
values remain loadable. This compatibility behavior must not be replaced by a
new interpretation during architectural extraction.

### `surfaces[]`

| Key | Shape | Default when missing |
| --- | --- | --- |
| `id` | non-empty string | Required. |
| `name` | string | `"Surface N"`. |
| `source_curve_ids` | array of strings | `[]`. |
| `surface_type` | string | `"placeholder"`. |
| `visible` | boolean | `true`. |
| `metadata` | JSON-safe object | `{}`. |

Surface records describe sources/options. Preview mesh geometry is regenerated;
it is not a separately embedded geometry payload. During restore, missing source
curve IDs are recorded in runtime metadata as `missing_curve_ids` rather than
causing the whole project to fail.

### `brep_surfaces[]`

| Key | Shape | Default when missing |
| --- | --- | --- |
| `id` | non-empty string | Required. |
| `name` | string | `"BREP Surface N"`. |
| `source_curve_ids` | array of strings | `[]`. |
| `brep_type` | string | `"unknown"`. |
| `backend` | string | Empty string. |
| `visible` | boolean | `true`. |
| `selected` | boolean | `false`. |
| `metadata` | JSON-safe object | `{}`. |

No CadQuery/OCP/OCCT object or tessellated BREP body is serialized. Non-JSON CAD
objects in metadata cause save validation to fail. On restore, each record is
marked `runtime_status: rebuild_required`, the runtime BREP cache is empty, and
export remains unavailable until a rebuild. Missing source curves are annotated
similarly to ordinary surfaces. BREP selection is the one object-selection state
currently represented directly in the file.

### `loft_features[]`

| Key | Shape | Default when missing |
| --- | --- | --- |
| `id` | non-empty string | Required. |
| `name` | string | `"Editable Loft N"`. |
| `options` | JSON-safe object | `{}`. |
| `brep_surface_id` | string or `null` | `null`. |
| `preview_surface_id` | string or `null` | `null`. |
| `last_build_success` | boolean | `false`. |
| `last_build_reason` | string | `"Not built."`. |
| `last_build_warnings` | array of strings | `[]`. |
| `metadata` | JSON-safe object | `{}`. |

The application currently recognizes option keys for ordered source curves,
source-order locking, CAD-wire use, direction/seam matching, corner
preservation, caps/solid/ruled choices, smoothing, source-edit rebuild,
overbuild enablement and U/V amounts, handle visibility, and nested metadata.
The format layer treats `options` as an open JSON-safe object.

### `four_boundary_patch_features[]`

| Key | Shape | Default when missing |
| --- | --- | --- |
| `id` | non-empty string | Required. |
| `name` | string | `"Four-Boundary Patch N"`. |
| `source_curve_ids` | array of strings | `[]`. |
| `preserve_corners` | boolean | `true`. |
| `match_directions` | boolean | `true`. |
| `fill_method` | string | `"coons_preview"`. |
| `brep_surface_id` | string or `null` | `null`. |
| `preview_surface_id` | string or `null` | `null`. |
| `last_build_status` | string | `"Not built."`. |
| `metadata` | JSON-safe object | `{}`. |

## Scalar, geometry, and metadata validation

- Numbers accept JSON integers or floats but reject booleans. `scale` must be
  greater than zero. No general finite-number check exists at this boundary.
- Vector and point fields require exactly three numeric components. Empty point
  arrays are legal. Plane normals are not normalized by project IO.
- Booleans are strict JSON booleans; `0`, `1`, and strings are rejected.
- Axes are case-insensitive strings and normalize to `X`, `Y`, or `Z`.
- A metadata/options object requires string keys. Values may be `null`, string,
  integer, float, boolean, list, or another string-keyed object recursively.
  Tuples, NumPy arrays, CAD objects, and arbitrary Python objects are rejected
  unless converted before export.
- Duplicate IDs are rejected inside planes, section results, curves, surfaces,
  BREP surfaces, loft features, and four-boundary features. References are not
  comprehensively validated by project IO.

## Asset references and restore behavior

- `mesh_path` is an external dependency. An absolute path is used as written; a
  relative path is resolved relative to the `.openretop` file's directory.
- The mesh file is loaded before its saved transform and generated records are
  restored. Missing/unreadable mesh content prevents a mesh-backed project from
  opening successfully.
- The saved proxy-quality label controls display-mesh construction. The
  full-resolution source is reloaded from the external mesh, not from the
  project file.
- Section planes/results, curves, surface descriptors, BREP descriptors, lofts,
  and four-boundary features are reconstructed from their records. Runtime
  actors, query indexes, preview meshes, and CAD objects are rebuilt or left in
  an explicit rebuild-required state.
- An invalid `active_section_plane_id` falls back to the first restored plane.
  Active curve/surface/feature IDs are not persisted; some adapters select the
  first restored feature as their runtime active item.

## Deliberately absent state

Version 1 does not persist:

- mesh vertex/triangle data or display proxies;
- VTK actors, viewport camera position/orientation/projection, clipping range,
  or framing state;
- the active region collection/triangle selection (a converted region boundary
  can survive as curve metadata, but the region selection itself does not);
- ordinary curve/surface/section selection, current workbench, expanded scene
  tree nodes, active transform/tool state, manual-curve transient session state,
  or undo/redo history;
- application preferences/keybindings (these belong to settings storage);
- accelerated mesh-query indexes/caches; or
- live CAD-kernel objects and generated BREP tessellation.

These omissions are not permission to add fields during an unrelated V3 task.
They identify state that must be deliberately reconstructed or left transient.

## Compatibility behaviors that must remain

1. A sparse version 1 document loads by filling nested and collection defaults.
2. A legacy file containing only the single `section` object restores one
   equivalent plane.
3. Missing later-added curve diagnostics and lineage fields are derived without
   rejecting the record.
4. Existing manual, curve-on-mesh, region-boundary, projected, rebuilt, repaired,
   old-polyline, Hybrid, and Catmull-Rom metadata survives load/save.
5. Rotated/arbitrary section origins and normals survive round-trip.
6. Surface, patch, BREP, editable-loft, and four-boundary descriptors survive
   without attempting to serialize proprietary/runtime CAD objects.
7. Invalid JSON produces a clear `ValueError`; a missing file continues to
   produce `FileNotFoundError`; unsupported versions remain explicit errors.

## Known compatibility risks

- **Strict version gate:** there is no migration dispatcher yet; any explicit
  version other than `1` is rejected.
- **Unknown-field loss:** unknown top-level and record-level schema keys are
  discarded. Only keys inside supported metadata/options bags are generally
  round-tripped.
- **External mesh fragility:** moving a project without its referenced mesh, or
  saving an inconvenient absolute path, can break reopening. Mesh content is
  not checksummed, so a changed file at the same path can change the project.
- **Non-atomic save:** interruption during direct write can leave a truncated
  project.
- **Project name canonicalization:** the current application exporter writes
  `"Untitled Project"`; a custom raw `name` is not guaranteed to survive an
  application-level reopen/save.
- **Derived-field canonicalization:** curve diagnostics and the two explicit
  source-ID fields can be recomputed/rebased by the application adapter.
- **Dangling references:** project IO accepts many missing cross-references;
  restore may skip a section result or annotate a surface/BREP rather than fail.
- **Stored-but-disabled normals:** `display.show_normals` exists in the format,
  but the current UI hard-codes it off on save and restore.
- **JSON portability:** non-finite float values are not proactively rejected.
- **No camera persistence:** reopening relies entirely on post-restore framing;
  the current framing regression is recorded in `KNOWN_REGRESSIONS.md`.

## Baseline verification

The principal executable coverage is in `tests/test_project_io.py`,
`tests/test_project_state.py`, `tests/test_main_window_ui.py`,
`tests/test_manual_curve_v2.py`, and `tests/test_surface_features.py`. Coverage
includes sparse/legacy input, validation failures, JSON round-trips, arbitrary
planes, manual and derived curve metadata, surface/BREP descriptors, editable
features, external mesh restore, and application-level save/load behavior.

Future project migrations must add dedicated old-file fixtures and must verify
an application-level load/save cycle, not only `ProjectData -> dict ->
ProjectData`, because the application adapters intentionally reconstruct and
canonicalize runtime state.
