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

import json
import os
import sqlite3
from pathlib import Path

from flask import Flask, g, jsonify, request, render_template, abort

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = os.environ.get("DATABASE_PATH", str(BASE_DIR / "negri.db"))
SEED_PATH = BASE_DIR / "seed_data.json"

CORE_FIELDS = [
    {"key": "no", "label": "Admission No.", "type": "text", "core": True},
    {"key": "artu", "label": "A.R./T/U", "type": "text", "core": True},
    {"key": "day", "label": "Day", "type": "text", "core": True},
    {"key": "month", "label": "Month", "type": "text", "core": True},
    {"key": "year", "label": "Year", "type": "text", "core": True},
    {"key": "surname", "label": "Surname", "type": "text", "core": True},
    {"key": "first", "label": "Christian Name", "type": "text", "core": True},
    {"key": "sex", "label": "Sex", "type": "select", "options": ["M", "F"], "core": True},
    {"key": "parent", "label": "Parent / Guardian Name", "type": "text", "core": True},
    {"key": "address", "label": "Address", "type": "text", "core": True},
]

app = Flask(__name__)


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DB_PATH)
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admission_no TEXT UNIQUE NOT NULL,
            payload TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS custom_fields (
            key TEXT PRIMARY KEY,
            label TEXT NOT NULL,
            type TEXT NOT NULL DEFAULT 'text',
            options TEXT
        );
        """
    )
    db.commit()

    # Seed with the transcribed register on first run only.
    count = db.execute("SELECT COUNT(*) FROM records").fetchone()[0]
    if count == 0 and SEED_PATH.exists():
        seed = json.loads(SEED_PATH.read_text(encoding="utf-8"))
        for rec in seed:
            db.execute(
                "INSERT INTO records (admission_no, payload) VALUES (?, ?)",
                (str(rec.get("no")), json.dumps(rec, ensure_ascii=False)),
            )
        db.commit()
    db.close()


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def get_custom_fields(db):
    rows = db.execute("SELECT key, label, type, options FROM custom_fields ORDER BY rowid").fetchall()
    out = []
    for r in rows:
        field = {"key": r["key"], "label": r["label"], "type": r["type"], "core": False}
        if r["options"]:
            field["options"] = json.loads(r["options"])
        out.append(field)
    return out


def all_fields(db):
    return CORE_FIELDS + get_custom_fields(db)


def row_to_record(row):
    return json.loads(row["payload"])


def slugify(label, existing_keys):
    import re
    base = re.sub(r"[^a-z0-9]+", "_", label.lower().strip()).strip("_") or "field"
    key = base
    n = 1
    while key in existing_keys:
        n += 1
        key = f"{base}_{n}"
    return key


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


# ---------------------------------------------------------------------------
# Records API
# ---------------------------------------------------------------------------

@app.route("/api/records", methods=["GET"])
def list_records():
    db = get_db()
    rows = db.execute("SELECT payload FROM records ORDER BY rowid").fetchall()
    return jsonify([row_to_record(r) for r in rows])


@app.route("/api/records", methods=["POST"])
def create_record():
    db = get_db()
    data = request.get_json(force=True, silent=True) or {}
    no = str(data.get("no", "")).strip()
    if not no:
        return jsonify({"error": "Admission No. is required."}), 400

    existing = db.execute("SELECT 1 FROM records WHERE admission_no = ?", (no,)).fetchone()
    if existing:
        return jsonify({"error": "A record with that admission number already exists."}), 409

    fields = all_fields(db)
    record = {f["key"]: str(data.get(f["key"], "")).strip() for f in fields}
    record["no"] = no

    db.execute(
        "INSERT INTO records (admission_no, payload) VALUES (?, ?)",
        (no, json.dumps(record, ensure_ascii=False)),
    )
    db.commit()
    return jsonify(record), 201


@app.route("/api/records/<path:no>", methods=["PUT"])
def update_record(no):
    db = get_db()
    row = db.execute("SELECT * FROM records WHERE admission_no = ?", (no,)).fetchone()
    if not row:
        abort(404)

    data = request.get_json(force=True, silent=True) or {}
    new_no = str(data.get("no", "")).strip()
    if not new_no:
        return jsonify({"error": "Admission No. is required."}), 400

    if new_no != no:
        clash = db.execute("SELECT 1 FROM records WHERE admission_no = ?", (new_no,)).fetchone()
        if clash:
            return jsonify({"error": "That admission number already exists on another record."}), 409

    fields = all_fields(db)
    record = {f["key"]: str(data.get(f["key"], "")).strip() for f in fields}
    record["no"] = new_no

    db.execute(
        "UPDATE records SET admission_no = ?, payload = ? WHERE admission_no = ?",
        (new_no, json.dumps(record, ensure_ascii=False), no),
    )
    db.commit()
    return jsonify(record)


@app.route("/api/records/<path:no>", methods=["DELETE"])
def delete_record(no):
    db = get_db()
    cur = db.execute("DELETE FROM records WHERE admission_no = ?", (no,))
    db.commit()
    if cur.rowcount == 0:
        abort(404)
    return jsonify({"deleted": no})


# ---------------------------------------------------------------------------
# Fields API
# ---------------------------------------------------------------------------

@app.route("/api/fields", methods=["GET"])
def list_fields():
    db = get_db()
    return jsonify({"core": CORE_FIELDS, "custom": get_custom_fields(db)})


@app.route("/api/fields", methods=["POST"])
def add_field():
    db = get_db()
    data = request.get_json(force=True, silent=True) or {}
    label = str(data.get("label", "")).strip()
    if not label:
        return jsonify({"error": "Field name is required."}), 400

    existing_keys = [f["key"] for f in all_fields(db)]
    key = slugify(label, existing_keys)

    db.execute(
        "INSERT INTO custom_fields (key, label, type, options) VALUES (?, ?, 'text', NULL)",
        (key, label),
    )

    # Backfill existing records with a blank value for the new field.
    rows = db.execute("SELECT admission_no, payload FROM records").fetchall()
    for r in rows:
        rec = json.loads(r["payload"])
        if key not in rec:
            rec[key] = ""
            db.execute(
                "UPDATE records SET payload = ? WHERE admission_no = ?",
                (json.dumps(rec, ensure_ascii=False), r["admission_no"]),
            )
    db.commit()
    return jsonify({"key": key, "label": label, "type": "text", "core": False}), 201


@app.route("/api/fields/<key>", methods=["DELETE"])
def remove_field(key):
    db = get_db()
    if key in [f["key"] for f in CORE_FIELDS]:
        return jsonify({"error": "Core fields cannot be removed."}), 400

    cur = db.execute("DELETE FROM custom_fields WHERE key = ?", (key,))
    db.commit()
    if cur.rowcount == 0:
        abort(404)

    rows = db.execute("SELECT admission_no, payload FROM records").fetchall()
    for r in rows:
        rec = json.loads(r["payload"])
        if key in rec:
            del rec[key]
            db.execute(
                "UPDATE records SET payload = ? WHERE admission_no = ?",
                (json.dumps(rec, ensure_ascii=False), r["admission_no"]),
            )
    db.commit()
    return jsonify({"removed": key})


# ---------------------------------------------------------------------------
# Import / Export / Reset
# ---------------------------------------------------------------------------

@app.route("/api/export", methods=["GET"])
def export_all():
    db = get_db()
    records = [row_to_record(r) for r in db.execute("SELECT payload FROM records ORDER BY rowid").fetchall()]
    return jsonify({"fields": get_custom_fields(db), "records": records})


@app.route("/api/import", methods=["POST"])
def import_all():
    db = get_db()
    data = request.get_json(force=True, silent=True) or {}

    if isinstance(data, list):
        records, fields = data, []
    else:
        records, fields = data.get("records", []), data.get("fields", [])

    if not isinstance(records, list):
        return jsonify({"error": "Invalid import format: 'records' must be a list."}), 400

    db.execute("DELETE FROM records")
    db.execute("DELETE FROM custom_fields")

    for f in fields:
        if not f.get("key") or f.get("core"):
            continue
        db.execute(
            "INSERT OR REPLACE INTO custom_fields (key, label, type, options) VALUES (?, ?, ?, ?)",
            (f["key"], f.get("label", f["key"]), f.get("type", "text"),
             json.dumps(f["options"]) if f.get("options") else None),
        )

    seen_no = set()
    for rec in records:
        no = str(rec.get("no", "")).strip()
        if not no or no in seen_no:
            continue
        seen_no.add(no)
        db.execute(
            "INSERT INTO records (admission_no, payload) VALUES (?, ?)",
            (no, json.dumps(rec, ensure_ascii=False)),
        )
    db.commit()
    return jsonify({"imported_records": len(seen_no), "imported_fields": len(fields)})


@app.route("/api/reset", methods=["POST"])
def reset_all():
    db = get_db()
    db.execute("DELETE FROM records")
    db.execute("DELETE FROM custom_fields")
    db.commit()

    if SEED_PATH.exists():
        seed = json.loads(SEED_PATH.read_text(encoding="utf-8"))
        for rec in seed:
            db.execute(
                "INSERT INTO records (admission_no, payload) VALUES (?, ?)",
                (str(rec.get("no")), json.dumps(rec, ensure_ascii=False)),
            )
        db.commit()
    return jsonify({"status": "reset"})


# ---------------------------------------------------------------------------

init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
