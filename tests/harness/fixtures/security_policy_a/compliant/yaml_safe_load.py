"""Q13 compliant — yaml.safe_load."""
import yaml

def parse(text: str) -> object:
    return yaml.safe_load(text)
