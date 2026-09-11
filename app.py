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
      const input = tr.querySelector(`[data-field="${f.key}"]`);
      updated[f.key] = input ? input.value.trim() : '';
    });
    try {
      const saved = await api('/records/' + encodeURIComponent(originalNo), {
        method: 'PUT', body: JSON.stringify(updated)
      });
      const idx = RECORDS.findIndex(r => String(r.no) === String(originalNo));
      if (idx !== -1) RECORDS[idx] = saved;
      editingNo = null;
      flashSaved();
      render();
    } catch (err) { showError(err.message); }
  }
});

searchEl.addEventListener('input', render);
sexEl.addEventListener('change', render);

function buildFormFields(existing) {
  formFields.innerHTML = allFields().map(f => {
    const val = existing ? escapeHtml(existing[f.key] || '') : '';
    if (f.type === 'select') {
      const opts = (f.options || []).map(o => `<option value="${o}" ${existing && existing[f.key] === o ? 'selected' : ''}>${o}</option>`).join('');
      return `<label>${escapeHtml(f.label)}</label><select data-field="${f.key}">${opts}</select>`;
    }
    return `<label>${escapeHtml(f.label)}</label><input type="text" data-field="${f.key}" value="${val}">`;
  }).join('');
}

document.getElementById('addBtn').addEventListener('click', () => {
  modalTitle.textContent = 'Add Record';
  buildFormFields(null);
  const maxNo = RECORDS.reduce((m, r) => Math.max(m, parseFloat(r.no) || 0), 0);
  const noInput = formFields.querySelector('[data-field="no"]');
  if (noInput) noInput.value = maxNo + 1;
  modalOverlay.classList.add('open');
});
document.getElementById('modalCancel').addEventListener('click', () => modalOverlay.classList.remove('open'));
modalOverlay.addEventListener('click', (e) => { if (e.target === modalOverlay) modalOverlay.classList.remove('open'); });

recordForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  const newRec = {};
  allFields().forEach(f => {
    const input = formFields.querySelector(`[data-field="${f.key}"]`);
    newRec[f.key] = input ? input.value.trim() : '';
  });
  if (!newRec.no) { alert('Admission No. is required.'); return; }
  try {
    const saved = await api('/records', { method: 'POST', body: JSON.stringify(newRec) });
    RECORDS.push(saved);
    flashSaved();
    modalOverlay.classList.remove('open');
    render();
  } catch (err) { alert(err.message); }
});

function renderFieldList() {
  const items = CORE_FIELDS.map(f => `<li class="core">${escapeHtml(f.label)} <span class="tag">core</span></li>`).join('');
  const customItems = CUSTOM_FIELDS.map(f => `
    <li>${escapeHtml(f.label)} <span class="tag">custom</span>
      <button type="button" class="btn-danger btn-small" data-remove-field="${f.key}">Remove</button>
    </li>`).join('');
  fieldList.innerHTML = items + customItems;
}

document.getElementById('fieldsBtn').addEventListener('click', () => { renderFieldList(); fieldsOverlay.classList.add('open'); });
document.getElementById('fieldsClose').addEventListener('click', () => fieldsOverlay.classList.remove('open'));
fieldsOverlay.addEventListener('click', (e) => { if (e.target === fieldsOverlay) fieldsOverlay.classList.remove('open'); });

document.getElementById('addFieldBtn').addEventListener('click', async () => {
  const labelInput = document.getElementById('newFieldLabel');
  const label = labelInput.value.trim();
  if (!label) { alert('Enter a name for the new field.'); return; }
  try {
    const field = await api('/fields', { method: 'POST', body: JSON.stringify({ label }) });
    CUSTOM_FIELDS.push(field);
    RECORDS.forEach(r => { if (!(field.key in r)) r[field.key] = ''; });
    labelInput.value = '';
    renderFieldList();
    renderHeader();
    render();
  } catch (err) { alert(err.message); }
});

fieldList.addEventListener('click', async (e) => {
  const btn = e.target.closest('button[data-remove-field]');
  if (!btn) return;
  const key = btn.dataset.removeField;
  const field = CUSTOM_FIELDS.find(f => f.key === key);
  if (!field) return;
  if (!confirm(`Remove field "${field.label}"? This deletes this field's data from all records for everyone.`)) return;
  try {
    await api('/fields/' + encodeURIComponent(key), { method: 'DELETE' });
    CUSTOM_FIELDS = CUSTOM_FIELDS.filter(f => f.key !== key);
    RECORDS.forEach(r => { delete r[key]; });
    if (sortKey === key) { sortKey = 'no'; sortDir = 1; }
    renderFieldList();
    renderHeader();
    render();
  } catch (err) { alert(err.message); }
});

document.getElementById('exportBtn').addEventListener('click', async () => {
  try {
    const payload = await api('/export');
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = 'negri_admission_records.json';
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    URL.revokeObjectURL(url);
  } catch (err) { alert(err.message); }
});

const fileImport = document.getElementById('fileImport');
document.getElementById('importBtn').addEventListener('click', () => fileImport.click());
fileImport.addEventListener('change', (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = async (evt) => {
    try {
      const parsed = JSON.parse(evt.target.result);
      const count = Array.isArray(parsed) ? parsed.length : (parsed.records || []).length;
      if (!confirm(`Import ${count} records? This replaces ALL current data for everyone using this page.`)) return;
      await api('/import', { method: 'POST', body: JSON.stringify(parsed) });
      await loadAll();
    } catch (err) { alert('Could not import file: ' + err.message); }
    fileImport.value = '';
  };
  reader.readAsText(file);
});


async function loadAll() {
  const [fieldsResp, records] = await Promise.all([api('/fields'), api('/records')]);
  CORE_FIELDS = fieldsResp.core;
  CUSTOM_FIELDS = fieldsResp.custom;
  RECORDS = records;
  editingNo = null;
  renderHeader();
  render();
}

loadAll().catch(err => {
  document.body.innerHTML = '<p style="padding:40px;text-align:center;color:#a23b3b;">Could not load data from the server: ' + err.message + '</p>';
});
</script>

</body>
</html>
"""


@app.route("/")
def index():
    return INDEX_HTML


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


# ---------------------------------------------------------------------------
# Note: the old "/api/reset" endpoint (restore-to-seed-data) has been removed
# entirely at the user's request, after a couple of accidental clicks wiped
# out newly-imported data. There is now no way to bulk-wipe the database from
# the UI or API — only individual record edits/deletes and full imports
# (POST /api/import) remain, both of which are intentional, explicit actions.
# ---------------------------------------------------------------------------

init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
