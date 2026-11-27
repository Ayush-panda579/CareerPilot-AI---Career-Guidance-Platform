import os
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parent


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY")
    UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", str(APP_ROOT / "uploads"))