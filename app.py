"""
Negri Primary School — Admission Register
A small Flask + SQLite web app that replaces the browser-localStorage
version with a real shared database: every visitor sees the same data,
and edits are stored server-side.

Run locally:
    pip install -r requirements.txt
    python app.py
    -> open http://localhost:5000

See README.md for deployment instructions (Render, Railway, Fly.io, etc).
"""

import hashlib
import hmac
import json
import os
import sqlite3
from pathlib import Path

from flask import Flask, g, jsonify, request, abort

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = os.environ.get("DATABASE_PATH", str(BASE_DIR / "negri.db"))
SEED_PATH = BASE_DIR / "seed_data.json"

CORE_FIELDS = [
    {"key": "no", "label": "Admission No.", "type": "text", "core": True},
    {"key": "artu", "label": "A.R./T/U", "type": "text", "core": True},
    {"key": "day", "label": "Day", "type": "text", "core": True},
    {"key": "month", "label": "Month", "type": "text", "core": True},
