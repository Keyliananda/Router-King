"""Diagnostic script — paste into FreeCAD's Python console to debug CAM module structure.

Usage:  Open FreeCAD → View → Python Console → paste this entire script.
"""

import sys
import FreeCAD as App

print("=" * 60)
print("FreeCAD CAM Module Diagnostic")
print("=" * 60)
print(f"FreeCAD version: {App.Version()}")
print(f"Python: {sys.version}")
print()

# Step 1: Activate CAMWorkbench so modules get loaded
print("--- Step 1: Activate CAM Workbench ---")
try:
    import FreeCADGui as Gui
    try:
        Gui.activateWorkbench("CAMWorkbench")
        print("CAMWorkbench activated OK")
    except Exception as e1:
        print(f"CAMWorkbench failed: {e1}")
        try:
            Gui.activateWorkbench("PathWorkbench")
            print("PathWorkbench activated OK (legacy)")
        except Exception as e2:
            print(f"PathWorkbench also failed: {e2}")
except ImportError:
    print("FreeCADGui not available (headless)")
print()

# Step 2: List all loaded modules with 'path' or 'cam' in their name
print("--- Step 2: Loaded CAM/Path modules ---")
cam_mods = sorted(k for k in sys.modules if "path" in k.lower() or "cam" in k.lower())
for m in cam_mods:
    mod = sys.modules[m]
    loc = getattr(mod, "__file__", getattr(mod, "__path__", "builtin/C++"))
    print(f"  {m:40s} -> {loc}")
print(f"  ({len(cam_mods)} modules total)")
print()

# Step 3: Probe specific modules for Create function
print("--- Step 3: Probe for Job.Create ---")
candidates = [
    "Path.Main.Job",
    "PathScripts.PathJob",
    "Path.Job",
    "CAM.Job",
    "CAM.PathJob",
    "Path.Main.Job.ObjectJob",
]
found_creator = None
found_module_name = None
for name in candidates:
    try:
        mod = __import__(name, fromlist=["*"])
        attrs = [a for a in dir(mod) if not a.startswith("_")]
        create_fn = getattr(mod, "Create", None)
        print(f"  {name}: OK (attrs={attrs})")
        if create_fn:
            import inspect
            try:
                sig = inspect.signature(create_fn)
                print(f"    Create signature: {sig}")
            except Exception:
                print(f"    Create: {create_fn} (sig unavailable)")
            if found_creator is None:
                found_creator = create_fn
                found_module_name = name
        else:
            print(f"    Create: NOT FOUND")
    except Exception as e:
        print(f"  {name}: FAILED ({e})")
print()

# Step 4: Try creating a job with TestTeil
print("--- Step 4: Test Job Creation ---")
doc = App.ActiveDocument
if doc is None:
    print("No active document. Creating one with a test box...")
    doc = App.newDocument("Unnamed")
    box = doc.addObject("Part::Box", "TestTeil")
    box.Length = 50
    box.Width = 30
    box.Height = 10
    doc.recompute()
    print(f"Created doc={doc.Name}, box={box.Name}")

model = doc.getObject("TestTeil")
if model is None:
    print("ERROR: No object named 'TestTeil' found in document.")
    print(f"  Available objects: {[o.Name for o in doc.Objects]}")
else:
    print(f"Found model: {model.Name} (TypeId={model.TypeId})")

    if found_creator:
        print(f"\nTrying {found_module_name}.Create('Job', [{model.Name}])...")
        try:
            job = found_creator("Job", [model])
            doc.recompute()
            print(f"SUCCESS! job={job.Name}, TypeId={job.TypeId}")
            print(f"  job attrs: {[a for a in dir(job) if not a.startswith('_')]}")
            # Check for Operations group
            ops = getattr(job, "Operations", None)
            print(f"  job.Operations: {ops}")
            model_attr = getattr(job, "Model", None)
            print(f"  job.Model: {model_attr}")
        except Exception as e:
            print(f"FAILED: {e}")
            import traceback
            traceback.print_exc()
    else:
        print("\nNo Create function found. Trying manual object creation...")
        try:
            job = doc.addObject("Path::FeaturePython", "Job")
            print(f"Created Path::FeaturePython: {job.Name}")
            print(f"  TypeId={job.TypeId}")
            # Try to set up via ObjectJob
            try:
                from Path.Main.Job import ObjectJob
                job.Proxy = ObjectJob(job, [model], None)
                doc.recompute()
                print(f"  ObjectJob proxy assigned OK")
            except Exception as e2:
                print(f"  ObjectJob proxy failed: {e2}")
        except Exception as e:
            print(f"Manual creation failed: {e}")

print()
print("--- Step 5: Path module details ---")
try:
    import Path
    print(f"Path module: {Path}")
    print(f"Path.__file__: {getattr(Path, '__file__', 'N/A')}")
    print(f"Path.__path__: {getattr(Path, '__path__', 'N/A')}")
    print(f"Path public attrs: {[a for a in dir(Path) if not a.startswith('_')]}")
except Exception as e:
    print(f"import Path failed: {e}")

try:
    import CAM
    print(f"\nCAM module: {CAM}")
    print(f"CAM.__file__: {getattr(CAM, '__file__', 'N/A')}")
    print(f"CAM public attrs: {[a for a in dir(CAM) if not a.startswith('_')]}")
except Exception as e:
    print(f"import CAM failed: {e}")

print()
print("=" * 60)
print("DONE. Copy this output and share it.")
print("=" * 60)
