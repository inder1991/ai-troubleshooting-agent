#!/usr/bin/env python3
"""Synthetic check that emits conforming output."""
import sys

print('[ERROR] file=tests/harness/fixtures/x.py:1 rule=demo.bad message="bad" suggestion="fix it"')
sys.exit(1)
