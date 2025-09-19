import os
import random

FLAVOR = "flavor_data"
DEATHLINK_FILE = "deathlink"
_flavor_cache = {}


def load_deathlink():
    """Load deathlink.txt into the cache (must exist)."""
    file_path = os.path.join(FLAVOR, f"{DEATHLINK_FILE}.txt")

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Missing required file: {file_path}")

    with open(file_path, 'r', encoding='utf-8') as f:
        lines = [line.strip() for line in f if line.strip()]
    _flavor_cache[DEATHLINK_FILE] = lines


def GetFlavorText(PlayerName):
    """Always pull from deathlink file only."""
    if DEATHLINK_FILE not in _flavor_cache:
        load_deathlink()

    if _flavor_cache[DEATHLINK_FILE]:
        return random.choice(_flavor_cache[DEATHLINK_FILE]).replace("PLAYER", PlayerName)
    else:
        return f"No deathlink flavor text available for {PlayerName}."
