# V3 regression status

No known automated behavior regression remains at the Tasks 77-82 acceptance
boundary. Complete discovery is green and the architecture scanner reports no
new violations or practical cycles.

Historical framing failures were resolved by explicit camera requests applied
after scene synchronization and by transformed/category-aware snapshot bounds.
Historical project loss of region/selection state was resolved by optional,
backward-compatible project fields and complete V3 restore.

Windows driver-specific rendering and representative large customer data are
tracked as human release review items in `KNOWN_LIMITATIONS.md`, not as proven
regressions.
