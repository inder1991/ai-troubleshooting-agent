"""Shared utilities for tools/* harness scripts."""

from __future__ import annotations

import re
from typing import Any


def parse_front_matter(text: str) -> tuple[dict[str, Any], str]:
    """Extract YAML front-matter and body from a markdown file.

    Supports the limited YAML subset the harness uses:
      * `key: value` scalar lines
      * `applies_to:` (or any key with no value) followed by `- item` lines

    Returns (front_matter_dict, body). Empty dict if no front-matter.
    """
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
    if not match:
        return {}, text
    fm_text, body = match.group(1), match.group(2)
    fm: dict[str, Any] = {}
    current_list_key: str | None = None
    for raw in fm_text.splitlines():
        line = raw.rstrip()
        if not line or line.startswith("#"):
            continue
        list_item = re.match(r"^\s+-\s+(.+)$", line)
        if list_item and current_list_key is not None:
            fm.setdefault(current_list_key, []).append(list_item.group(1).strip())
            continue
        kv = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if not kv:
            current_list_key = None
            continue
        key, value = kv.group(1), kv.group(2).strip()
        if value == "":
            current_list_key = key
            fm[key] = []
        else:
            current_list_key = None
            fm[key] = value.strip('"').strip("'")
    return fm, body
