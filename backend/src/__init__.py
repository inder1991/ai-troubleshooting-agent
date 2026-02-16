def __getattr__(name):
    if name == "TroubleshootingOrchestrator":
        from .orchestrator import TroubleshootingOrchestrator
        return TroubleshootingOrchestrator
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = ['TroubleshootingOrchestrator']