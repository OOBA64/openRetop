"""A small line-icon set drawn for the workbench, rendered in the theme's colours.

Every icon is SVG markup for a 24 x 24 box with round 1.6 px strokes, written with a
``{c}`` placeholder for the stroke colour so the same drawing serves light and dark themes
and the disabled state.
"""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap

_STROKE = 'fill="none" stroke="{c}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"'

ICONS: dict[str, str] = {
    # a scan coming into the tray
    "open_scan": (
        '<path d="M12 3v10M8 9l4 4 4-4"/>'
        '<path d="M4 14v4a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-4"/>'
    ),
    "open_project": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "save": (
        '<path d="M5 4h11l3 3v12a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1z"/>'
        '<path d="M8 4v5h7V4M8 20v-6h8v6"/>'
    ),
    "undo": '<path d="M9 14 4 9l5-5"/><path d="M4 9h10a6 6 0 0 1 0 12h-3"/>',
    "redo": '<path d="m15 14 5-5-5-5"/><path d="M20 9H10a6 6 0 0 0 0 12h3"/>',
    "frame_all": (
        '<path d="M4 9V5a1 1 0 0 1 1-1h4M15 4h4a1 1 0 0 1 1 1v4M20 15v4a1 1 0 0 1-1 1h-4M9 20H5a1 1 0 0 1-1-1v-4"/>'
        '<path d="M8 12h8M12 8v8" opacity="0.55"/>'
    ),
    "frame_selected": (
        '<path d="M4 9V5a1 1 0 0 1 1-1h4M15 4h4a1 1 0 0 1 1 1v4M20 15v4a1 1 0 0 1-1 1h-4M9 20H5a1 1 0 0 1-1-1v-4"/>'
        '<rect x="9" y="9" width="6" height="6" rx="1"/>'
    ),
    "move": (
        '<path d="M12 3v18M3 12h18"/>'
        '<path d="m9 6 3-3 3 3M9 18l3 3 3-3M6 9l-3 3 3 3M18 9l3 3-3 3"/>'
    ),
    "rotate": '<path d="M20 12a8 8 0 1 1-2.6-5.9"/><path d="M20 4v5h-5"/>',
    # a cutting plane
    "section_plane": (
        '<path d="M3 16 8 8h13l-5 8z"/>'
        '<path d="M12 3v18" opacity="0.55"/>'
    ),
    # the outline the cut produces
    "section_cut": (
        '<path d="M3 18 8 9h13l-5 9z" opacity="0.5"/>'
        '<path d="M8.5 15c1.5-3 4-3.5 5.5-2.5s3-.5 3.5-1.5" stroke-width="2.2"/>'
    ),
    "curve": (
        '<path d="M5 18C7 8 17 16 19 6"/>'
        '<circle cx="5" cy="18" r="1.6"/><circle cx="19" cy="6" r="1.6"/>'
    ),
    "region": (
        '<path d="M6 6c3-2 9-2 12 1s2 8-2 10-9 2-11-1-2-8 1-10z" stroke-dasharray="2.4 2.4"/>'
        '<path d="m12 11 5 2-2 1-1 2z"/>'
    ),
    "measure": (
        '<path d="M3 16 16 3l5 5L8 21z"/>'
        '<path d="m7 12 2 2M10 9l2 2M13 6l2 2"/>'
    ),
    # scene tree kinds
    # a sketch on a plane: a profile of lines and a rounded corner
    "section_sketch": (
        '<path d="M3 18 7.5 6H21l-4.5 12z" opacity="0.5"/>'
        '<path d="M8.5 15.5 10.5 9.5h5.2a1.6 1.6 0 0 1 1.5 2.1l-1.3 3.9z" stroke-width="2.1"/>'
    ),
    # a profile pushed out into a block
    "extrude": (
        '<path d="M4 17.5 9 15h11l-5 2.5z" opacity="0.55"/>'
        '<path d="M4 17.5V9l5-2.5h11V15M4 9h11l5-2.5M15 9v8.5"/>'
        '<path d="M12 4.5V1.8m0 0-1.6 1.6M12 1.8l1.6 1.6" stroke-width="1.6"/>'
    ),
    # surfacing tools: a patch laid over scan points
    "fit_surface": (
        '<path d="M3 15c3-4 6-6 9-6s6 2 9 6l-4 5H7z"/>'
        '<path d="M6 7.5h.01M10 5h.01M14 5h.01M18 7.5h.01" stroke-width="2.4"/>'
    ),
    # a surface swept between two section curves
    "loft": (
        '<path d="M4 7c3-2 6 2 9 0s5-2 7-1"/><path d="M4 18c3-2 6 2 9 0s5-2 7-1"/>'
        '<path d="M4 7v11M20 6v11M12 7.3v11" opacity="0.5"/>'
    ),
    # a gap closed inside a boundary
    "fill": (
        '<path d="M4 8c4-3 12-3 16 0l-1 9c-4 3-10 3-14 0z"/>'
        '<path d="M8 10.5c2.5 1.2 5.5 1.2 8 0M8 14c2.5 1.2 5.5 1.2 8 0" opacity="0.55"/>'
    ),
    # an edge pushed outwards
    "extend": (
        '<path d="M3 16c2-4 5-6 9-6"/><path d="M12 10c3 0 5 1 7 3" stroke-dasharray="2 2.2"/>'
        '<path d="m16 9 3 4-4.5 1"/>'
    ),
    # two crossing surfaces with the cut-off part dashed
    "trim": (
        '<path d="M4 18 14 6"/><path d="M4 9h9"/><path d="M13 9h7" stroke-dasharray="2 2.2"/>'
        '<path d="M14 6l4-5" stroke-dasharray="2 2.2" opacity="0.6"/>'
    ),
    # a colour map: a surface with deviation bands
    "compare": (
        '<path d="M3 17c3-3 6-9 9-9s6 6 9 9"/>'
        '<path d="M6.5 13.5v4M9.5 10v7.5M14.5 10v7.5M17.5 13.5v4" opacity="0.55"/>'
    ),
    "project": '<path d="m12 3 9 5-9 5-9-5z"/><path d="m3 13 9 5 9-5" opacity="0.6"/>',
    "mesh": (
        '<path d="m12 3 8 4.5v9L12 21l-8-4.5v-9z"/>'
        '<path d="m4 7.5 8 4.5 8-4.5M12 12v9" opacity="0.6"/>'
    ),
    "folder": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" opacity="0.8"/>',
    "surface": '<path d="M4 17c3-1 4-9 8-9s5 8 8 9"/><path d="M4 17h16" opacity="0.5"/>',
    "solid": (
        '<path d="m12 3 8 4.5v9L12 21l-8-4.5v-9z"/>'
        '<path d="m4 7.5 8 4.5 8-4.5" />'
        '<path d="M12 12v9"/>'
    ),
    "feature": '<path d="M5 19c2-7 5-11 14-14"/><path d="M5 13c3 0 5 1 6 6" opacity="0.6"/>',
}


def svg_markup(name: str, color: str) -> str:
    body = ICONS[name].replace("{c}", color)
    stroke = _STROKE.replace("{c}", color)
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" {stroke}>{body}</svg>'


def _pixmap(name: str, color: str, size: int, ratio: float) -> QPixmap:
    from PySide6.QtSvg import QSvgRenderer

    pixels = max(1, round(size * ratio))
    pixmap = QPixmap(pixels, pixels)
    pixmap.fill(Qt.GlobalColor.transparent)
    renderer = QSvgRenderer(QByteArray(svg_markup(name, color).encode("utf-8")))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, pixels, pixels))
    painter.end()
    pixmap.setDevicePixelRatio(ratio)
    return pixmap


def themed_icon(name: str, color: str, disabled_color: str, *, size: int = 20) -> QIcon:
    """The icon in ``color``, greyed to ``disabled_color`` when its action is disabled; sharp at 1x and 2x."""

    icon = QIcon()
    for ratio in (1.0, 2.0):
        icon.addPixmap(_pixmap(name, color, size, ratio), QIcon.Mode.Normal)
        icon.addPixmap(_pixmap(name, color, size, ratio), QIcon.Mode.Active)
        icon.addPixmap(_pixmap(name, disabled_color, size, ratio), QIcon.Mode.Disabled)
    return icon


ICON_SIZE = QSize(20, 20)

__all__ = ("ICONS", "ICON_SIZE", "svg_markup", "themed_icon")
