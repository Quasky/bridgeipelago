import os
import random
import glob

FLAVOR = "flavor_data"
_flavor_cache = {}
DEATHLINK_FILE = "deathlink"

os.makedirs(FLAVOR, exist_ok=True)


def BuildFlavorFile(PlayerName):
    file_path = os.path.join(FLAVOR, f"{PlayerName}.txt")
    if not os.path.exists(file_path): 
        with open(file_path, 'w', encoding='utf-8') as f:
            print(f"Flavor file created: {file_path}")
    else:
        print(f"Flavor file already exists: {file_path}")


def load_flavor(PlayerName):
    pattern = os.path.join(FLAVOR, f"{PlayerName}*.txt")
    matched_files = glob.glob(pattern)

    if not matched_files:
        BuildFlavorFile(PlayerName)
        matched_files = glob.glob(pattern)

    all_lines = []
    for filepath in matched_files:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f if line.strip()]
            all_lines.extend(lines)

    _flavor_cache[PlayerName] = all_lines


def GetFlavorText(PlayerName):
    if PlayerName not in _flavor_cache:
        load_flavor(PlayerName)

    if not _flavor_cache[PlayerName]:
        if DEATHLINK_FILE not in _flavor_cache:
            load_flavor(DEATHLINK_FILE)

        if _flavor_cache[DEATHLINK_FILE]:
            return random.choice(_flavor_cache[DEATHLINK_FILE]).replace("PLAYER", PlayerName)
        
    else:
        return random.choice(_flavor_cache[PlayerName]).replace("PLAYER", PlayerName)
