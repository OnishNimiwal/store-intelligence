import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent


def dataset_root() -> Path:
    return Path(os.getenv("DATASET_ROOT", str(ROOT_DIR)))


def pos_csv_path() -> Path:
    env_path = os.getenv("POS_CSV_PATH")
    if env_path:
        return Path(env_path)
    return ROOT_DIR / "pos_transactions.csv"


def store_layout_path() -> Path:
    env_path = os.getenv("STORE_LAYOUT_PATH")
    if env_path:
        return Path(env_path)
    return ROOT_DIR / "store_layout.json"
