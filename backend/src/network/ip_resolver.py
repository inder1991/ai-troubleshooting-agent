"""Radix tree wrapper for fast IP -> subnet/device resolution."""
import pytricia
from typing import Optional


class IPResolver:
    """O(log n) longest-prefix-match IP resolution using pytricia radix tree."""

    def __init__(self):
        self._tree = pytricia.PyTricia()

    def load_subnets(self, subnets: list[dict]) -> None:
        """Load subnet metadata into the radix tree.
        Each dict: {cidr, gateway_ip, zone_id, vlan_id, description, site}
        """
        self._tree = pytricia.PyTricia()
        for s in subnets:
            self._tree[s["cidr"]] = s

    def resolve(self, ip: str) -> Optional[dict]:
        """Resolve IP to its longest-prefix-match subnet metadata."""
        try:
            return self._tree[ip]
        except KeyError:
            return None

    def get_prefix(self, ip: str) -> Optional[str]:
        """Get the matching CIDR prefix for an IP."""
        try:
            return self._tree.get_key(ip)
        except KeyError:
            return None

    @property
    def count(self) -> int:
        return len(self._tree)
