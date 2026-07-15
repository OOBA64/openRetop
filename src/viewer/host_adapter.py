"""Tk host/widget adapter for a native VTK render window."""

from __future__ import annotations

from tkinter import Canvas
from typing import Callable


class TkVTKHostAdapter:
    """Own the concrete Tk canvas operations used by the viewport facade."""

    def __init__(
        self,
        parent: object,
        *,
        background: str,
        canvas_factory: Callable[..., Canvas] = Canvas,
    ) -> None:
        self.widget = canvas_factory(
            parent,
            background=background,
            borderwidth=0,
            highlightthickness=0,
        )

    def pack(self) -> None:
        self.widget.pack(fill="both", expand=True)

    def attach(self, render_window: object) -> None:
        self.widget.update_idletasks()
        render_window.SetWindowInfo(str(self.widget.winfo_id()))
        self.resize(render_window)

    def resize(self, render_window: object) -> None:
        render_window.SetSize(
            max(int(self.widget.winfo_width()), 1),
            max(int(self.widget.winfo_height()), 1),
        )

    def close(self) -> None:
        self.widget.destroy()


__all__ = ("TkVTKHostAdapter",)
