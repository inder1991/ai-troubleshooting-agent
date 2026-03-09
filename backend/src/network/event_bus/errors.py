"""Custom exceptions for the event bus subsystem."""


class BackpressureError(Exception):
    """Raised when a channel queue exceeds its backpressure threshold.

    Callers should back off and retry, or drop the event and alert
    an operator that the pipeline is saturated.
    """
