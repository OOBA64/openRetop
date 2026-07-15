# openRetop V3 desktop shell

Run the supported Qt shell with:

```powershell
python src/main.py
```

The window is composed from the independent `workbench_ui` package. The Scene
dock owns selection and visibility intent, the center viewport consumes Task 77
`SceneSnapshot` values, the Properties dock is the contextual inspector, and
the bottom Command Palette searches the same central action registry used by
menus and shortcuts.

Project/model dialogs are presentation adapters. They call the Task 78 import,
project, settings, CAD, and export services; those services do not create Qt
dialogs or widgets. The optional CAD backend reports unavailable capabilities
without enabling unsupported operations.

The legacy Tk shell is no longer the normal entry point. During the Task 80
parity window it remains available only as a compatibility implementation for
the existing regression suite; Task 81 removes it after the parity matrix and
workflow coverage are accepted.
