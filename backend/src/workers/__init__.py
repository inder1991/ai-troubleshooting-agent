"""Background-worker entrypoint.

Run with::

    python -m src.workers.main

See ``main.py`` for the dispatcher that brings up the outbox relay,
investigation runner, scheduler, and resume scan in one process.
"""
