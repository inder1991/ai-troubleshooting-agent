"""Q8 violation — cursor.execute outside the gateway."""
import sqlite3

def hack() -> None:
    cursor = sqlite3.connect(":memory:").cursor()
    cursor.execute("SELECT 1")
