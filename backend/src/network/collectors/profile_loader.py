"""Load YAML device profiles, resolve inheritance, build sysObjectID index."""
from __future__ import annotations

import fnmatch
import logging
from pathlib import Path

import yaml

from .models import (
    DeviceProfile,
    MetricDefinition,
    MetricSymbol,
    MetricTagDef,
    MetadataFieldDef,
)

logger = logging.getLogger(__name__)

PROFILES_DIR = Path(__file__).parent / "profiles"


class ProfileLoader:
    """Loads device profiles from YAML files and matches sysObjectIDs."""

    def __init__(self, profiles_dir: Path | None = None) -> None:
        self._dir = profiles_dir or PROFILES_DIR
        self._profiles: dict[str, DeviceProfile] = {}
        # Ordered list: (pattern, profile_name) — specific patterns first.
        self._oid_index: list[tuple[str, str]] = []

    @property
    def profiles(self) -> dict[str, DeviceProfile]:
        return dict(self._profiles)

    def load_all(self) -> int:
        """Load all YAML profiles from the profiles directory.

        Returns the count of loaded profiles (excluding base fragments).
        """
        if not self._dir.exists():
            logger.warning("Profiles directory not found: %s", self._dir)
            return 0

        # First pass: load raw YAML
        raw: dict[str, dict] = {}
        for path in sorted(self._dir.glob("*.yaml")):
            try:
                with open(path) as f:
                    data = yaml.safe_load(f) or {}
                raw[path.stem] = data
            except Exception as e:
                logger.error("Failed to load profile %s: %s", path.name, e)

        # Second pass: resolve extends + build DeviceProfile
        self._profiles.clear()
        self._oid_index.clear()
        for name, data in raw.items():
            try:
                profile = self._resolve(name, data, raw)
                self._profiles[name] = profile
            except Exception as e:
                logger.error("Failed to resolve profile %s: %s", name, e)

        # Build OID index (specific patterns before wildcard catch-all)
        self._build_oid_index()
        count = sum(1 for n in self._profiles if not n.startswith("_"))
        logger.info("Loaded %d device profiles (%d base fragments)", count, len(self._profiles) - count)
        return count

    def match(self, sys_object_id: str) -> DeviceProfile | None:
        """Match a sysObjectID to the best profile.

        Tries exact match first, then wildcard. Returns None if no match.
        The generic.yaml catch-all ("*") is always the last resort.
        """
        if not sys_object_id:
            return self._profiles.get("generic")

        for pattern, name in self._oid_index:
            if self._oid_matches(sys_object_id, pattern):
                return self._profiles.get(name)

        return self._profiles.get("generic")

    def get(self, name: str) -> DeviceProfile | None:
        return self._profiles.get(name)

    def list_profiles(self) -> list[DeviceProfile]:
        """Return all non-base profiles."""
        return [p for n, p in self._profiles.items() if not n.startswith("_")]

    # ── Internal ──

    def _resolve(self, name: str, data: dict, raw_all: dict[str, dict]) -> DeviceProfile:
        """Resolve a profile with extends inheritance."""
        merged_metrics: list[MetricDefinition] = []
        merged_metadata: dict[str, MetadataFieldDef] = {}

        # Resolve base profiles first
        for base_name in data.get("extends", []):
            base_stem = base_name.replace(".yaml", "")
            if base_stem in raw_all:
                base = self._resolve(base_stem, raw_all[base_stem], raw_all)
                merged_metrics.extend(base.metrics)
                merged_metadata.update(base.metadata_fields)

        # Add own metrics
        for m in data.get("metrics", []):
            merged_metrics.append(self._parse_metric(m))

        # Add own metadata
        meta_section = data.get("metadata", {}).get("device", {}).get("fields", {})
        for field_name, field_def in meta_section.items():
            merged_metadata[field_name] = self._parse_metadata_field(field_def)

        return DeviceProfile(
            name=name,
            sysobjectid=data.get("sysobjectid", []),
            extends=data.get("extends", []),
            vendor=data.get("vendor", ""),
            device_type=data.get("device_type", ""),
            metrics=merged_metrics,
            metadata_fields=merged_metadata,
        )

    def _parse_metric(self, raw: dict) -> MetricDefinition:
        symbol = None
        if "symbol" in raw:
            symbol = MetricSymbol(**raw["symbol"])

        table = None
        if "table" in raw:
            table = MetricSymbol(**raw["table"])

        symbols = [MetricSymbol(**s) for s in raw.get("symbols", [])]

        metric_tags = []
        for t in raw.get("metric_tags", []):
            col = MetricSymbol(**t["column"]) if "column" in t else None
            metric_tags.append(MetricTagDef(
                tag=t["tag"],
                index=t.get("index"),
                column=col,
            ))

        return MetricDefinition(
            MIB=raw.get("MIB", ""),
            symbol=symbol,
            table=table,
            symbols=symbols,
            metric_tags=metric_tags,
        )

    def _parse_metadata_field(self, raw: dict) -> MetadataFieldDef:
        symbol = None
        if "symbol" in raw:
            symbol = MetricSymbol(**raw["symbol"])
        return MetadataFieldDef(value=raw.get("value"), symbol=symbol)

    def _build_oid_index(self) -> None:
        """Build ordered (pattern, profile_name) index.

        Specific OID patterns come first; wildcard catch-all ("*") last.
        """
        entries: list[tuple[str, str, int]] = []  # (pattern, name, specificity)
        for name, profile in self._profiles.items():
            if name.startswith("_"):
                continue
            for pattern in profile.sysobjectid:
                specificity = self._pattern_specificity(pattern)
                entries.append((pattern, name, specificity))

        # Sort by specificity descending (most specific first)
        entries.sort(key=lambda e: e[2], reverse=True)
        self._oid_index = [(pat, name) for pat, name, _ in entries]

    @staticmethod
    def _pattern_specificity(pattern: str) -> int:
        """Score a sysObjectID pattern by specificity.

        Exact OIDs score highest. "*" alone scores 0.
        """
        if pattern == "*":
            return 0
        # Count non-wildcard segments
        parts = pattern.split(".")
        return sum(1 for p in parts if p != "*")

    @staticmethod
    def _oid_matches(oid: str, pattern: str) -> bool:
        """Match a sysObjectID against a pattern.

        Supports:
        - Exact match: "1.3.6.1.4.1.9.1.123"
        - Trailing wildcard: "1.3.6.1.4.1.9.1.*" matches "1.3.6.1.4.1.9.1.anything"
        - Full wildcard: "*" matches everything
        """
        if pattern == "*":
            return True
        return fnmatch.fnmatch(oid, pattern)
