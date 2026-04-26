"""Q13 violation — yaml.load without Loader= permits arbitrary code execution."""
import yaml

def parse(text: str) -> object:
    return yaml.load(text)
