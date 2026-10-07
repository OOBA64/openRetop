"""Project schema versioning: each step upgrades a raw project dict by one version."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from project.project_data import PROJECT_VERSION

Migration = Callable[[dict[str, object]], dict[str, object]]


def _v0_to_v1(data: dict[str, object]) -> dict[str, object]:
    # Pre-versioned files had the same layout, just no version stamp.
    return {**data, "version": 1}


def _v1_to_v2(data: dict[str, object]) -> dict[str, object]:
    # v2 records the length unit of the imported mesh. v1 never recorded one,
    # so millimetres is assumed and flagged so the UI can ask the user.
    return {
        **data,
        "version": 2,
        "units": data.get("units", "mm"),
        "units_assumed": True,
    }


MIGRATIONS: dict[int, Migration] = {
    0: _v0_to_v1,
    1: _v1_to_v2,
}


def migrate_project_dict(data: Mapping[str, object]) -> tuple[dict[str, object], list[int]]:
    """Upgrade ``data`` to ``PROJECT_VERSION``.

    Returns the upgraded dict and the list of versions that were migrated from.
    Raises ValueError for non-integer versions or versions newer than this build.
    """

    result = dict(data)
    raw_version = result.get("version")
    if raw_version is None:
        version = 0
    elif isinstance(raw_version, bool) or not isinstance(raw_version, int):
        raise ValueError("version must be an integer.")
    else:
        version = raw_version
    if version < 0:
        raise ValueError(f"Unsupported project version: {version}")
    if version > PROJECT_VERSION:
        raise ValueError(
            f"Unsupported project version: {version} (this build reads up to {PROJECT_VERSION})"
        )

    applied: list[int] = []
    while version < PROJECT_VERSION:
        result = MIGRATIONS[version](result)
        applied.append(version)
        version += 1
    return result, applied
