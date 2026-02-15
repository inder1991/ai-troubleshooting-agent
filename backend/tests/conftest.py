import sys
import types
import os

# Prevent src/__init__.py from importing the old orchestrator
# by pre-registering 'src' as an empty module before pytest collects tests
backend_dir = os.path.join(os.path.dirname(__file__), "..")
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

# Pre-load 'src' as a namespace package to avoid triggering src/__init__.py's
# import of the orchestrator (which has missing dependencies)
if "src" not in sys.modules:
    src_mod = types.ModuleType("src")
    src_mod.__path__ = [os.path.join(backend_dir, "src")]
    src_mod.__package__ = "src"
    sys.modules["src"] = src_mod

if "src.models" not in sys.modules:
    models_mod = types.ModuleType("src.models")
    models_mod.__path__ = [os.path.join(backend_dir, "src", "models")]
    models_mod.__package__ = "src.models"
    sys.modules["src.models"] = models_mod
