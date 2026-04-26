#!/usr/bin/env python3
"""Synthetic check that emits non-conforming output (for the meta-validator)."""
import sys

print("Something is wrong somewhere")  # NOT in [SEVERITY] file=… shape
sys.exit(1)
