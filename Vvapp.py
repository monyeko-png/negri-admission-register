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

INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Negri Primary School — Admission Register</title>
<style>
  :root {
    --ink: #2b2418; --paper: #faf6ec; --paper-alt: #f2ead6;
    --accent: #8a5a2b; --accent-dark: #5f3d1c; --line: #d8c9a8;
    --shadow: rgba(90, 65, 30, 0.15); --danger: #a23b3b; --ok: #3b7a4a;
  }
  * { box-sizing: border-box; }
  body { margin: 0; font-family: 'Georgia','Times New Roman',serif; background: linear-gradient(180deg,#efe6d0 0%,#e8dcc0 100%); color: var(--ink); min-height: 100vh; }
  header { padding: 28px 20px 18px; text-align: center; background: var(--accent-dark); color: #f6ecd9; box-shadow: 0 3px 10px var(--shadow); }
  header h1 { margin: 0 0 4px; font-size: 1.5rem; letter-spacing: 0.5px; }
  header p { margin: 0; font-size: 0.85rem; opacity: 0.85; font-style: italic; }

  .toolbar { max-width: 1250px; margin: 18px auto 0; padding: 0 16px; display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }
  #search { flex: 1 1 260px; padding: 12px 14px; font-size: 1rem; border: 2px solid var(--line); border-radius: 8px; background: var(--paper); color: var(--ink); font-family: inherit; }
  #search:focus { outline: none; border-color: var(--accent); }
  select { padding: 11px 10px; font-size: 0.95rem; border-radius: 8px; border: 2px solid var(--line); background: var(--paper); color: var(--ink); font-family: inherit; }
  button { font-family: inherit; font-size: 0.9rem; padding: 10px 16px; border-radius: 8px; border: none; cursor: pointer; font-weight: 600; transition: filter 0.15s; }
  button:hover { filter: brightness(1.08); }
  button:disabled { opacity: 0.5; cursor: not-allowed; }
  .btn-primary { background: var(--accent); color: #fff; }
  .btn-primary:hover { background: var(--accent-dark); }
  .btn-ghost { background: var(--paper); color: var(--accent-dark); border: 2px solid var(--line); }
  .btn-danger { background: var(--danger); color: #fff; }
  .btn-ok { background: var(--ok); color: #fff; }
  .btn-small { padding: 5px 10px; font-size: 0.78rem; border-radius: 6px; }
  #fileImport { display: none; }

  .stats { max-width: 1250px; margin: 12px auto 0; padding: 0 16px; font-size: 0.85rem; color: var(--accent-dark); display: flex; gap: 18px; flex-wrap: wrap; align-items: center; min-height: 20px; }
  .stats strong { color: var(--ink); }
  .save-flag { font-size: 0.78rem; color: var(--ok); font-style: italic; }
  .err-flag { font-size: 0.78rem; color: var(--danger); font-weight: 600; }

  .table-wrap { max-width: 1250px; margin: 16px auto 40px; padding: 0 16px; overflow-x: auto; }
  table { width: 100%; border-collapse: collapse; background: var(--paper); border-radius: 10px; overflow: hidden; box-shadow: 0 4px 14px var(--shadow); font-size: 0.88rem; }
  thead th { background: var(--accent); color: #fff; text-align: left; padding: 10px 10px; font-weight: 600; position: sticky; top: 0; cursor: pointer; user-select: none; white-space: nowrap; }
  thead th.actions-col { cursor: default; }
  thead th:hover:not(.actions-col) { background: var(--accent-dark); }
  thead th .arrow { opacity: 0.6; font-size: 0.75em; margin-left: 3px; }
  tbody td { padding: 8px 10px; border-bottom: 1px solid var(--line); vertical-align: top; }
  tbody tr:nth-child(even) { background: var(--paper-alt); }
  tbody tr:hover { background: #eadfbf; }
  tbody tr.editing { background: #fff3d6 !important; }
  .no-col { font-weight: 700; color: var(--accent-dark); white-space: nowrap; }
  .sex-M { color: #2c5f7c; font-weight: 600; }
  .sex-F { color: #9c3860; font-weight: 600; }
  mark { background: #ffe28a; color: inherit; padding: 0 1px; border-radius: 2px; }
  .empty { text-align: center; padding: 40px 20px; color: #8a7a5a; font-style: italic; }
  .actions-cell { white-space: nowrap; display: flex; gap: 6px; }

  td input, td select.edit-input { width: 100%; padding: 5px 6px; font-family: inherit; font-size: 0.85rem; border: 1px solid var(--line); border-radius: 4px; background: #fffdf6; }

  .modal-overlay { display: none; position: fixed; inset: 0; background: rgba(43,36,24,0.55); align-items: center; justify-content: center; z-index: 50; padding: 16px; }
  .modal-overlay.open { display: flex; }
  .modal { background: var(--paper); border-radius: 12px; max-width: 480px; width: 100%; padding: 22px; box-shadow: 0 10px 30px rgba(0,0,0,0.3); max-height: 90vh; overflow-y: auto; }
  .modal h2 { margin: 0 0 14px; font-size: 1.2rem; color: var(--accent-dark); }
  .modal label { display: block; font-size: 0.78rem; font-weight: 700; color: var(--accent-dark); text-transform: uppercase; letter-spacing: 0.3px; margin: 12px 0 4px; }
  .modal input, .modal select { width: 100%; padding: 9px 10px; font-family: inherit; font-size: 0.95rem; border: 2px solid var(--line); border-radius: 6px; background: #fffdf6; }
  .modal-buttons { margin-top: 20px; display: flex; gap: 10px; justify-content: flex-end; }
  .field-note { font-size: 0.78rem; color: #8a7a5a; margin-top: 4px; }

  .field-list { list-style: none; margin: 10px 0 0; padding: 0; }
  .field-list li { display: flex; justify-content: space-between; align-items: center; padding: 8px 4px; border-bottom: 1px solid var(--line); font-size: 0.9rem; }
  .field-list li.core { color: #a89574; }
  .field-list .tag { font-size: 0.7rem; background: var(--line); color: var(--accent-dark); padding: 1px 6px; border-radius: 4px; margin-left: 6px; }
  .add-field-row { display: flex; gap: 8px; margin-top: 14px; }
  .add-field-row input { flex: 1; padding: 9px 10px; border: 2px solid var(--line); border-radius: 6px; font-family: inherit; background: #fffdf6; }

  @media (max-width: 780px) {
    table, thead, tbody, th, td, tr { display: block; }
    thead { display: none; }
    tbody tr { background: var(--paper) !important; margin-bottom: 12px; border-radius: 10px; box-shadow: 0 2px 8px var(--shadow); padding: 10px 12px; }
    tbody td { border: none; padding: 4px 0; display: flex; gap: 6px; align-items: flex-start; }
    tbody td::before { content: attr(data-label); font-weight: 700; color: var(--accent-dark); min-width: 96px; flex-shrink: 0; font-size: 0.76rem; text-transform: uppercase; letter-spacing: 0.3px; padding-top: 2px; }
    .actions-cell { flex-wrap: wrap; }
  }
  footer { text-align: center; padding: 20px; font-size: 0.78rem; color: #8a7a5a; }
</style>
</head>
<body>

<header>
  <h1>Negri Primary School</h1>
  <p>Admission Register &middot; c. 1975&ndash;1983 &middot; shared live database</p>
</header>

<div class="toolbar">
  <input type="text" id="search" placeholder="Search all fields..." autocomplete="off">
  <select id="sexFilter">
    <option value="">All (M/F)</option>
    <option value="M">Male</option>
    <option value="F">Female</option>
  </select>
  <button class="btn-primary" id="addBtn">+ Add Record</button>
  <button class="btn-ghost" id="fieldsBtn">Manage Fields</button>
  <button class="btn-ghost" id="exportBtn">Export JSON</button>
  <button class="btn-ghost" id="importBtn">Import JSON</button>
  <button class="btn-ghost" id="resetBtn">Reset to Original</button>
  <input type="file" id="fileImport" accept="application/json">
</div>

<div class="stats" id="stats"></div>

<div class="table-wrap">
  <table id="dataTable">
    <thead><tr id="headRow"></tr></thead>
    <tbody id="tbody"></tbody>
  </table>
  <div class="empty" id="emptyMsg" style="display:none;">No matching records found.</div>
</div>

<footer>
  This is a shared live database &mdash; changes made here are visible to everyone who opens this page.
  Use <strong>Export JSON</strong> for your own backups.
</footer>

<div class="modal-overlay" id="modalOverlay">
  <div class="modal">
    <h2 id="modalTitle">Add Record</h2>
    <form id="recordForm">
      <div id="formFields"></div>
      <div class="modal-buttons">
        <button type="button" class="btn-ghost" id="modalCancel">Cancel</button>
        <button type="submit" class="btn-primary">Save Record</button>
      </div>
    </form>
  </div>
</div>

<div class="modal-overlay" id="fieldsOverlay">
  <div class="modal">
    <h2>Manage Fields</h2>
    <div class="field-note">Core fields are always present. Add custom fields (e.g. "Class", "Notes") &mdash; they appear as new columns for everyone using this page.</div>
    <ul class="field-list" id="fieldList"></ul>
    <div class="add-field-row">
      <input type="text" id="newFieldLabel" placeholder="New field name, e.g. Notes">
      <button type="button" class="btn-primary btn-small" id="addFieldBtn">Add Field</button>
    </div>
    <div class="modal-buttons">
      <button type="button" class="btn-ghost" id="fieldsClose">Close</button>
    </div>
  </div>
</div>

<script>
const API = '/api';

let CORE_FIELDS = [];
let CUSTOM_FIELDS = [];
let RECORDS = [];
let sortKey = 'no';
let sortDir = 1;
let editingNo = null;

function allFields() { return CORE_FIELDS.concat(CUSTOM_FIELDS); }

async function api(path, options) {
  const res = await fetch(API + path, Object.assign({
    headers: { 'Content-Type': 'application/json' }
  }, options));
  let body = null;
  try { body = await res.json(); } catch (e) {}
  if (!res.ok) {
    const msg = (body && body.error) ? body.error : ('Request failed (' + res.status + ')');
    throw new Error(msg);
  }
  return body;
}

function showError(msg) {
  const el = document.getElementById('errFlag');
  if (!el) return;
  el.textContent = msg;
  el.style.opacity = '1';
  clearTimeout(showError._t);
  showError._t = setTimeout(() => { el.style.opacity = '0'; }, 4000);
}

function flashSaved() {
  const el = document.getElementById('saveFlag');
  if (!el) return;
  el.style.opacity = '1';
  clearTimeout(flashSaved._t);
  flashSaved._t = setTimeout(() => { el.style.opacity = '0'; }, 1500);
}

const searchEl = document.getElementById('search');
const sexEl = document.getElementById('sexFilter');
const tbody = document.getElementById('tbody');
const headRow = document.getElementById('headRow');
const statsEl = document.getElementById('stats');
const emptyMsg = document.getElementById('emptyMsg');
const modalOverlay = document.getElementById('modalOverlay');
const modalTitle = document.getElementById('modalTitle');
const recordForm = document.getElementById('recordForm');
const formFields = document.getElementById('formFields');
const fieldsOverlay = document.getElementById('fieldsOverlay');
const fieldList = document.getElementById('fieldList');

function escapeHtml(str) {
  return String(str == null ? '' : str).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
function highlight(text, term) {
  const safe = escapeHtml(text || '');
  if (!term) return safe || '&ndash;';
  const idx = safe.toLowerCase().indexOf(term.toLowerCase());
  if (idx === -1) return safe || '&ndash;';
  return safe.slice(0, idx) + '<mark>' + safe.slice(idx, idx + term.length) + '</mark>' + safe.slice(idx + term.length);
}
function matches(rec, term) {
  if (!term) return true;
  const hay = allFields().map(f => rec[f.key]).join(' ').toLowerCase();
  return hay.includes(term.toLowerCase());
}

function renderHeader() {
  headRow.innerHTML = allFields().map(f => `<th data-key="${f.key}">${escapeHtml(f.label)} <span class="arrow"></span></th>`).join('')
    + `<th class="actions-col">Actions</th>`;
  headRow.querySelectorAll('th[data-key]').forEach(th => {
    th.addEventListener('click', () => {
      const key = th.dataset.key;
      if (sortKey === key) { sortDir *= -1; } else { sortKey = key; sortDir = 1; }
      headRow.querySelectorAll('.arrow').forEach(a => a.textContent = '');
      th.querySelector('.arrow').textContent = sortDir === 1 ? '\u25b2' : '\u25bc';
      render();
    });
  });
}

function render() {
  const term = searchEl.value.trim();
  const sexVal = sexEl.value;
  const fields = allFields();

  let filtered = RECORDS.filter(r => matches(r, term) && (!sexVal || r.sex === sexVal));
  filtered.sort((a, b) => {
    let av = a[sortKey], bv = b[sortKey];
    if (sortKey === 'no') { av = parseFloat(av) || 0; bv = parseFloat(bv) || 0; }
    else { av = (av || '').toString().toLowerCase(); bv = (bv || '').toString().toLowerCase(); }
    if (av < bv) return -1 * sortDir;
    if (av > bv) return 1 * sortDir;
    return 0;
  });

  tbody.innerHTML = '';
  if (filtered.length === 0) {
    emptyMsg.style.display = 'block';
  } else {
    emptyMsg.style.display = 'none';
    const frag = document.createDocumentFragment();
    filtered.forEach(r => {
      const tr = document.createElement('tr');
      if (String(r.no) === String(editingNo)) {
        tr.classList.add('editing');
        tr.innerHTML = fields.map(f => editCellHtml(f, r)).join('')
          + `<td data-label="Actions" class="actions-cell">
               <button class="btn-ok btn-small" data-action="save" data-no="${escapeHtml(r.no)}">Save</button>
               <button class="btn-ghost btn-small" data-action="cancel">Cancel</button>
             </td>`;
      } else {
        tr.innerHTML = fields.map(f => viewCellHtml(f, r, term)).join('')
          + `<td data-label="Actions" class="actions-cell">
               <button class="btn-ghost btn-small" data-action="edit" data-no="${escapeHtml(r.no)}">Edit</button>
               <button class="btn-danger btn-small" data-action="delete" data-no="${escapeHtml(r.no)}">Delete</button>
             </td>`;
      }
      frag.appendChild(tr);
    });
    tbody.appendChild(frag);
  }

  const maleCount = RECORDS.filter(r => r.sex === 'M').length;
  const femaleCount = RECORDS.filter(r => r.sex === 'F').length;
  statsEl.innerHTML = `
    <span><strong>${filtered.length}</strong> of ${RECORDS.length} records shown</span>
    <span>Male: <strong>${maleCount}</strong></span>
    <span>Female: <strong>${femaleCount}</strong></span>
    <span class="save-flag" id="saveFlag" style="opacity:0;">Saved &#10003;</span>
    <span class="err-flag" id="errFlag" style="opacity:0;"></span>
  `;
}

function viewCellHtml(f, r, term) {
  if (f.key === 'no') return `<td class="no-col" data-label="${escapeHtml(f.label)}">${escapeHtml(r.no)}</td>`;
  if (f.key === 'sex') return `<td class="sex-${r.sex}" data-label="${escapeHtml(f.label)}">${r.sex || '&ndash;'}</td>`;
  return `<td data-label="${escapeHtml(f.label)}">${highlight(r[f.key], term)}</td>`;
}
function editCellHtml(f, r) {
  const val = r[f.key] != null ? r[f.key] : '';
  if (f.type === 'select') {
    const opts = (f.options || []).map(o => `<option value="${o}" ${o === val ? 'selected' : ''}>${o}</option>`).join('');
    return `<td data-label="${escapeHtml(f.label)}"><select class="edit-input" data-field="${f.key}">${opts}</select></td>`;
  }
  return `<td data-label="${escapeHtml(f.label)}"><input type="text" class="edit-input" data-field="${f.key}" value="${escapeHtml(val)}"></td>`;
}

tbody.addEventListener('click', async (e) => {
  const btn = e.target.closest('button[data-action]');
  if (!btn) return;
  const action = btn.dataset.action;

  if (action === 'edit') {
    editingNo = btn.dataset.no;
    render();
  } else if (action === 'cancel') {
    editingNo = null;
    render();
  } else if (action === 'delete') {
    const no = btn.dataset.no;
    const rec = RECORDS.find(r => String(r.no) === String(no));
    const label = rec ? `${rec.surname || ''} ${rec.first || ''}`.trim() || no : no;
    if (!confirm(`Delete record #${no} (${label})? This cannot be undone.`)) return;
    try {
      await api('/records/' + encodeURIComponent(no), { method: 'DELETE' });
      RECORDS = RECORDS.filter(r => String(r.no) !== String(no));
      flashSaved();
      render();
    } catch (err) { showError(err.message); }
  } else if (action === 'save') {
    const originalNo = btn.dataset.no;
    const tr = btn.closest('tr');
    const updated = {};
    allFields().forEach(f => {
      const input = 
