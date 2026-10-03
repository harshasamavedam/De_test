"""Interactive query UI: a small read-only CQL console for the shop keyspace.

Serves a single self-contained HTML page at `/ui` plus the JSON endpoints it
calls. No build step and no extra dependencies beyond FastAPI.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from . import query
from .service import ShopService

router = APIRouter()


class QueryRequest(BaseModel):
    cql: str


def get_service(request: Request) -> ShopService:
    return request.app.state.shop_service


@router.get("/api/v1/query/presets", tags=["explore"])
def presets():
    return {"presets": query.PRESETS}


@router.post("/api/v1/query", tags=["explore"])
def run_query(payload: QueryRequest, service: ShopService = Depends(get_service)):
    try:
        return query.run(service.repo, payload.cql)
    except query.QueryError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


@router.get("/ui", response_class=HTMLResponse, include_in_schema=False)
def ui():
    return HTMLResponse(PAGE)


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Shop data explorer</title>
<style>
  :root { --bg:#0f1117; --panel:#171a23; --line:#2a2f3a; --fg:#e6e8ee; --muted:#9aa3b2;
          --accent:#5b8cff; --ok:#3ecf8e; --warn:#ffb454; --err:#ff6b6b; }
  * { box-sizing:border-box; }
  body { margin:0; font:14px/1.5 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
         background:var(--bg); color:var(--fg); }
  header { padding:14px 18px; border-bottom:1px solid var(--line); display:flex;
           align-items:center; gap:12px; flex-wrap:wrap; }
  h1 { font-size:15px; margin:0; font-weight:600; }
  .muted { color:var(--muted); font-size:12px; }
  .wrap { padding:16px 18px; display:grid; gap:14px; max-width:1200px; }
  .presets { display:flex; flex-wrap:wrap; gap:6px; }
  button { background:var(--panel); color:var(--fg); border:1px solid var(--line);
           border-radius:6px; padding:5px 9px; cursor:pointer; font:inherit; font-size:12px; }
  button:hover { border-color:var(--accent); }
  button.primary { background:var(--accent); border-color:var(--accent); color:#fff; font-size:13px; padding:7px 16px; }
  textarea { width:100%; min-height:82px; background:var(--panel); color:var(--fg);
             border:1px solid var(--line); border-radius:8px; padding:10px; font:inherit; resize:vertical; }
  .row { display:flex; align-items:center; gap:10px; }
  .status { font-size:12px; }
  .status.ok { color:var(--ok); } .status.err { color:var(--err); } .status.warn { color:var(--warn); }
  .tablewrap { overflow:auto; border:1px solid var(--line); border-radius:8px; max-height:70vh; }
  table { border-collapse:collapse; width:100%; font-size:12.5px; }
  th,td { text-align:left; padding:6px 10px; border-bottom:1px solid var(--line); white-space:nowrap; }
  th { position:sticky; top:0; background:#1d2130; color:var(--muted); font-weight:600; }
  td.null { color:#666; font-style:italic; }
  tr:hover td { background:#1a1e29; }
</style>
</head>
<body>
<header>
  <h1>Shop data explorer</h1>
  <span class="muted">read-only CQL &middot; keyspace <b>shop</b></span>
</header>
<div class="wrap">
  <div>
    <div class="muted" style="margin-bottom:6px">Preset queries</div>
    <div class="presets" id="presets"></div>
  </div>
  <div>
    <textarea id="cql" spellcheck="false">SELECT * FROM orders LIMIT 25</textarea>
    <div class="row" style="margin-top:8px">
      <button class="primary" id="run">Run query</button>
      <span class="status" id="status"></span>
    </div>
  </div>
  <div class="tablewrap" id="result"><div class="muted" style="padding:12px">Run a query to see results.</div></div>
</div>
<script>
const $ = (id) => document.getElementById(id);
async function loadPresets() {
  const res = await fetch('/api/v1/query/presets');
  const data = await res.json();
  const box = $('presets');
  box.innerHTML = '';
  data.presets.forEach(p => {
    const b = document.createElement('button');
    b.textContent = p.label;
    b.onclick = () => { $('cql').value = p.cql; run(); };
    box.appendChild(b);
  });
}
async function run() {
  const cql = $('cql').value.trim();
  $('status').className = 'status';
  $('status').textContent = 'running...';
  try {
    const res = await fetch('/api/v1/query', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({cql})
    });
    const data = await res.json();
    if (!res.ok) {
      $('status').className = 'status err';
      $('status').textContent = data.detail || 'query failed';
      return;
    }
    render(data);
    $('status').className = 'status ' + (data.truncated ? 'warn' : 'ok');
    $('status').textContent = data.row_count + ' row(s)' + (data.truncated ? ' (cap 200)' : '');
  } catch (e) {
    $('status').className = 'status err';
    $('status').textContent = 'request failed: ' + e.message;
  }
}
function render(data) {
  const box = $('result');
  if (!data.columns.length) { box.innerHTML = '<div class="muted" style="padding:12px">No columns.</div>'; return; }
  let html = '<table><thead><tr>' + data.columns.map(c => `<th>${esc(c)}</th>`).join('') + '</tr></thead><tbody>';
  if (!data.rows.length) {
    html += `<tr><td colspan="${data.columns.length}" class="muted">No rows.</td></tr>`;
  } else {
    for (const row of data.rows) {
      html += '<tr>' + data.columns.map(c => {
        const v = row[c];
        return v === null || v === undefined ? '<td class="null">null</td>' : `<td>${esc(v)}</td>`;
      }).join('') + '</tr>';
    }
  }
  box.innerHTML = html + '</tbody></table>';
}
function esc(v) {
  return String(v).replace(/[&<>"']/g, s => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[s]));
}
$('run').onclick = run;
$('cql').addEventListener('keydown', e => { if ((e.ctrlKey||e.metaKey) && e.key === 'Enter') run(); });
loadPresets();
</script>
</body>
</html>
"""
