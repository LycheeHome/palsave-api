import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BACKUP_DIR = Path(os.environ["PALSAVE_API_BACKUP_DIR"])
HOST = os.environ.get("PALSAVE_API_HOST", "127.0.0.1")
PORT = int(os.environ.get("PALSAVE_API_PORT", "8787"))

ARCHIVE_DIR = Path("snapshots")
STATE_PATH = Path("state.json")
