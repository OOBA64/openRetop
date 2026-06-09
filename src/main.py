"""Very small desktop entry point for opening and viewing meshes."""

from __future__ import annotations

from pathlib import Path
from tkinter import BooleanVar, Button, Checkbutton, Entry, Frame, Label, Menu, OptionMenu
from tkinter import StringVar, Tk, filedialog, messagebox

from geometry.curves import CurveFitResult, fit_section_polylines
from geometry.sections import SECTION_AXES, SectionResult, extract_section
from mesh.diagnostics import format_diagnostic_lines
from mesh.import_mesh import get_section_summary_lines, show_mesh
from mesh.loader import load_mesh
from mesh.mesh_state import MeshState


MESH_FILE_TYPES = (
    ("Mesh files", "*.stl *.obj *.ply"),
    ("STL files", "*.stl"),
    ("OBJ files", "*.obj"),
    ("PLY files", "*.ply"),
    ("All files", "*.*"),
)


class OpenRetopApp:
    def __init__(self) -> None:
        self.root = Tk()
        self.root.title("openRetop")
        self.root.geometry("640x420")
        self.root.minsize(520, 360)

        self.mesh_state = MeshState()
        self.section_result: SectionResult | None = None
        self.curve_results: list[CurveFitResult] = []
        self.section_axis = StringVar(value="Z")
        self.section_offset = StringVar(value="0")
        self.show_section = BooleanVar(value=True)

        self.status = Label(
            self.root,
            text="Choose File > Open Mesh... to load an STL, OBJ, or PLY mesh.",
            justify="left",
            anchor="nw",
            padx=18,
            pady=18,
        )
        self.status.pack(fill="both", expand=True)

        controls = Frame(self.root, padx=18)
        controls.pack(fill="x", pady=(0, 16))

        Button(controls, text="Open Mesh...", command=self.open_mesh).grid(
            row=0,
            column=0,
            padx=(0, 10),
            pady=4,
            sticky="ew",
        )
        Button(controls, text="View Mesh", command=self.view_mesh).grid(
            row=0,
            column=1,
            padx=(0, 18),
            pady=4,
            sticky="ew",
        )
        Label(controls, text="Axis").grid(row=0, column=2, padx=(0, 6), sticky="e")
        OptionMenu(controls, self.section_axis, *SECTION_AXES).grid(
            row=0,
            column=3,
            padx=(0, 12),
            pady=4,
            sticky="ew",
        )
        Label(controls, text="Offset").grid(row=0, column=4, padx=(0, 6), sticky="e")
        Entry(controls, textvariable=self.section_offset, width=10).grid(
            row=0,
            column=5,
            padx=(0, 12),
            pady=4,
            sticky="ew",
        )
        Button(controls, text="Recompute Section", command=self.recompute_section).grid(
            row=1,
            column=0,
            columnspan=2,
            padx=(0, 10),
            pady=4,
            sticky="ew",
        )
        Checkbutton(
            controls,
            text="Show section curve",
            variable=self.show_section,
        ).grid(row=1, column=2, columnspan=3, pady=4, sticky="w")

        controls.columnconfigure(1, weight=1)
        controls.columnconfigure(5, weight=1)

        menu_bar = Menu(self.root)
        file_menu = Menu(menu_bar, tearoff=False)
        file_menu.add_command(label="Open Mesh...", command=self.open_mesh)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.destroy)
        menu_bar.add_cascade(label="File", menu=file_menu)
        self.root.config(menu=menu_bar)

    def open_mesh(self) -> None:
        selected_path = filedialog.askopenfilename(
            title="Open mesh",
            filetypes=MESH_FILE_TYPES,
        )
        if not selected_path:
            return

        mesh_path = Path(selected_path)
        self.status.config(text=f"Loading {mesh_path.name}...")
        self.root.update_idletasks()

        try:
            loaded = load_mesh(mesh_path)
        except (FileNotFoundError, ValueError, SystemExit) as exc:
            self.status.config(text="Mesh load failed.")
            messagebox.showerror("Could not open mesh", str(exc))
            return

        self.mesh_state = MeshState.from_loaded_mesh(loaded)
        self.recompute_section(show_error=False)
        self.view_mesh()

    def recompute_section(self, *, show_error: bool = True) -> None:
        if not self.mesh_state.is_loaded or self.mesh_state.mesh is None:
            if show_error:
                messagebox.showinfo("No mesh loaded", "Open a mesh before sectioning.")
            return

        try:
            offset = float(self.section_offset.get())
            self.section_result = extract_section(
                self.mesh_state.mesh,
                axis=self.section_axis.get(),
                offset=offset,
            )
            self.curve_results = fit_section_polylines(self.section_result.polylines)
        except ValueError as exc:
            if show_error:
                messagebox.showerror("Section failed", str(exc))
            return

        self.status.config(text=self._status_text())

    def view_mesh(self) -> None:
        if not self.mesh_state.is_loaded or self.mesh_state.mesh is None:
            messagebox.showinfo("No mesh loaded", "Open a mesh before viewing.")
            return

        show_mesh(
            self.mesh_state.mesh,
            show_normals=True,
            normal_scale=0.02,
            section_result=self.section_result,
            curve_results=self.curve_results,
            show_section=self.show_section.get(),
        )

    def _status_text(self) -> str:
        lines = []
        if self.mesh_state.file_path is not None:
            lines.extend([str(self.mesh_state.file_path), ""])

        lines.extend(format_diagnostic_lines(self.mesh_state))
        lines.extend(["", *get_section_summary_lines(self.section_result, self.curve_results)])
        return "\n".join(lines)

    def run(self) -> None:
        self.root.mainloop()


def main() -> int:
    OpenRetopApp().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
