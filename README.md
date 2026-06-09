This program is meant to take scans and aid in converting them to BREP surfaces. 

GOAL: Build a guided scan-to-cad tool that converts mesh scan data into clean NURBS/B-REP surfaces.

Initial MVP: 
1. Import STL/OBJ/PLY.
2. Display Mesh
3. Extract Cross Sections
4. Fit Splines to Sections
5. Fit simple NURBS surfaces. 
6. Export usable CAD geometry.

## Mesh Import Prototype

Install the prototype dependency:

```powershell
python -m pip install -r requirements.txt
```

Open the integrated app window:

```powershell
python src/main.py
```

You can also load a mesh directly from the import script:

```powershell
python src/mesh/import_mesh.py path\to\model.obj
```

Print mesh statistics without opening the viewer:

```powershell
python src/mesh/import_mesh.py path\to\model.stl --no-viewer
```

Extract a section and print curve-fit diagnostics without opening the viewer:

```powershell
python src/mesh/import_mesh.py path\to\model.stl --no-viewer --section-axis Z --section-offset 0
```

Show the vertex-normal overlay:

```powershell
python src/mesh/import_mesh.py path\to\model.ply --show-normals
```

The desktop app opens one main window with a menu bar, left control panel,
embedded viewport, and bottom status bar. Load a mesh from File > Open Model or
the sidebar Open Model button, then use the section controls to choose X/Y/Z,
set an offset, and compute the section. Normals are hidden by default and can be
enabled from View > Show Normals or the sidebar checkbox.

```powershell
python src/main.py
```

Do not commit secrets, API keys, credentials, or large scan files. Dont be stupid.
