"""Very small desktop entry point for opening and viewing meshes."""

from __future__ import annotations

from pathlib import Path
from tkinter import Button, Label, Menu, Tk, filedialog, messagebox

from mesh.import_mesh import get_mesh_summary_lines, load_mesh, show_mesh


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
        self.root.geometry("520x260")
        self.root.minsize(420, 220)

        self.status = Label(
            self.root,
            text="Choose File > Open Mesh... to load an STL, OBJ, or PLY mesh.",
            justify="left",
            anchor="nw",
            padx=18,
            pady=18,
        )
        self.status.pack(fill="both", expand=True)

        Button(self.root, text="Open Mesh...", command=self.open_mesh).pack(pady=(0, 18))

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
            mesh = load_mesh(mesh_path)
        except (FileNotFoundError, ValueError, SystemExit) as exc:
            self.status.config(text="Mesh load failed.")
            messagebox.showerror("Could not open mesh", str(exc))
            return

        summary = "\n".join([str(mesh_path), "", *get_mesh_summary_lines(mesh)])
        self.status.config(text=summary)

        show_mesh(mesh, show_normals=True, normal_scale=0.02)

    def run(self) -> None:
        self.root.mainloop()


def main() -> int:
    OpenRetopApp().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
