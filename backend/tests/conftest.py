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

# Stub out missing third-party modules that old v3 routes depend on
# so that importing create_app() doesn't fail during tests.
# We use a MagicMock-style module that returns a dummy for any attribute.
from unittest.mock import MagicMock


class _StubModule(types.ModuleType):
    """A module stub that returns a MagicMock for any missing attribute."""
    def __getattr__(self, name):
        return MagicMock()


_stub_module_names = [
    "langchain_openai",
    "langchain_core",
    "langchain_core.messages",
    "langchain_core.prompts",
    "langchain_core.output_parsers",
    "langchain_anthropic",
    "langgraph",
    "langgraph.graph",
    "langgraph.graph.state",
    "elasticsearch",
    "ddtrace",
    "ddtrace.trace",
]
for _mod_name in _stub_module_names:
    if _mod_name not in sys.modules:
        _stub = _StubModule(_mod_name)
        _stub.__path__ = []
        _stub.__package__ = _mod_name
        sys.modules[_mod_name] = _stub

# Provide a minimal working StateGraph and END for workflow tests
class _MinimalStateGraph:
    """Minimal StateGraph stand-in so workflow tests can verify nodes/edges."""
    def __init__(self, state_type):
        self.nodes = {}
        self._entry = None
        self._conditional_edges = {}
        self._edges = {}

    def add_node(self, name, func):
        self.nodes[name] = func

    def set_entry_point(self, name):
        self._entry = name

    def add_conditional_edges(self, source, func, mapping):
        self._conditional_edges[source] = (func, mapping)

    def add_edge(self, source, target):
        self._edges[source] = target

sys.modules["langgraph.graph"].StateGraph = _MinimalStateGraph
sys.modules["langgraph.graph"].END = "__end__"
