"""Optional VTK Qt host with a headless-safe fallback."""

from __future__ import annotations

import os

from PySide6.QtWidgets import QLabel, QVBoxLayout, QFrame, QWidget


class VTKViewportWidget(QFrame):
    """Embed the public VTK render window without owning scene policy."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.renderer = None
        self.render_window = None
        self.interactor = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        try:
            from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor
            from vtkmodules.vtkRenderingCore import vtkRenderer

            self.interactor = QVTKRenderWindowInteractor(self)
            self.render_window = self.interactor.GetRenderWindow()
            self.renderer = vtkRenderer()
            self.render_window.AddRenderer(self.renderer)
            layout.addWidget(self.interactor)
        except (ImportError, RuntimeError) as exc:
            self._fallback_error = str(exc)
            layout.addWidget(QLabel("VTK viewport unavailable", self))

    @property
    def available(self) -> bool:
        return self.renderer is not None and self.render_window is not None

    def start(self) -> None:
        if self.interactor is not None:
            self.interactor.Initialize()

    def render(self) -> None:
        if os.environ.get("QT_QPA_PLATFORM", "").strip().lower() == "offscreen":
            return
        if self.render_window is not None:
            self.render_window.Render()

    def add_test_geometry(self) -> bool:
        if self.renderer is None:
            return False
        from vtkmodules.vtkFiltersSources import vtkSphereSource
        from vtkmodules.vtkRenderingCore import vtkActor, vtkPolyDataMapper

        source = vtkSphereSource()
        source.SetThetaResolution(24)
        source.SetPhiResolution(16)
        mapper = vtkPolyDataMapper()
        mapper.SetInputConnection(source.GetOutputPort())
        actor = vtkActor()
        actor.SetMapper(mapper)
        self.renderer.AddActor(actor)
        self.renderer.ResetCamera()
        self.render()
        return True
