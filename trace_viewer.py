"""Trace viewer cục bộ: so sánh điểm giữa các lần chạy eval và giải thích nguyên nhân thay đổi.

Chạy:
    python3 trace_viewer.py                 # quét *.json trong thư mục này, mở http://127.0.0.1:8765
    python3 trace_viewer.py --port 9000 --dir path/to/results

Chỉ đọc file kết quả eval (có key 'summary' và 'cases'); không gọi API, không sửa file.
"""
import argparse
import json
import os
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


def find_runs(root):
    runs = []
    for name in sorted(os.listdir(root)):
        if not name.endswith('.json'):
            continue
        path = os.path.join(root, name)
        try:
            with open(path, encoding='utf-8') as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and 'cases' in data and 'summary' in data:
            runs.append({'name': name, 'mtime': os.path.getmtime(path),
                         'summary': data.get('summary'), 'config': data.get('config')})
    runs.sort(key=lambda r: r['mtime'])
    return runs


def make_handler(root):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code, body, ctype):
            data = body.encode('utf-8') if isinstance(body, str) else body
            self.send_response(code)
            self.send_header('Content-Type', ctype)
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            url = urlparse(self.path)
            if url.path == '/':
                return self._send(200, PAGE, 'text/html; charset=utf-8')
            if url.path == '/api/runs':
                return self._send(200, json.dumps(find_runs(root)), 'application/json')
            if url.path == '/api/run':
                name = (parse_qs(url.query).get('name') or [''])[0]
                if os.path.basename(name) != name or not name.endswith('.json'):
                    return self._send(400, '{"error":"bad name"}', 'application/json')
                path = os.path.join(root, name)
                if not os.path.isfile(path):
                    return self._send(404, '{"error":"not found"}', 'application/json')
                with open(path, 'rb') as fh:
                    return self._send(200, fh.read(), 'application/json')
            self._send(404, 'not found', 'text/plain')

        def log_message(self, *args):
            pass

    return Handler


PAGE = r'''<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Eval Trace Viewer</title>
<style>
:root {
  --bg: #f7f7f5; --panel: #ffffff; --text: #1d1d1b; --muted: #6b6b66; --line: #e3e2dd;
  --a: #8a8f98; --b: #2f6fed; --up: #1a8a4a; --down: #c8372d; --warn: #b26b00;
  --chip: #efeee9; --code: #f2f1ec; --sel: #eaf1ff;
}
@media (prefers-color-scheme: dark) {
  :root { --bg: #141413; --panel: #1d1d1b; --text: #ecebe6; --muted: #9a9993; --line: #33322f;
    --a: #75797f; --b: #6c9bff; --up: #4cc27b; --down: #ff6b5f; --warn: #e3a33a;
    --chip: #2a2a27; --code: #232320; --sel: #1f2a40; }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text);
  font: 14px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
header { padding: 16px 24px; border-bottom: 1px solid var(--line); background: var(--panel);
  display: flex; flex-wrap: wrap; gap: 12px 24px; align-items: center; position: sticky; top: 0; z-index: 2; }
h1 { font-size: 16px; margin: 0; }
label { color: var(--muted); font-size: 12px; display: flex; gap: 6px; align-items: center; }
select { font: inherit; padding: 4px 8px; border: 1px solid var(--line); border-radius: 6px;
  background: var(--panel); color: var(--text); }
main { padding: 20px 24px; max-width: 1400px; margin: 0 auto; }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; margin-bottom: 20px; }
.card { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 12px 14px; }
.card .k { color: var(--muted); font-size: 12px; }
.card .v { font-size: 24px; font-weight: 600; font-variant-numeric: tabular-nums; }
.card .s { color: var(--muted); font-size: 12px; }
.up { color: var(--up); } .down { color: var(--down); } .warn { color: var(--warn); }
.panel { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 14px 16px; margin-bottom: 20px; }
.panel h2 { font-size: 14px; margin: 0 0 10px; }
.legend { display: flex; gap: 16px; font-size: 12px; color: var(--muted); margin-bottom: 6px; }
.sw { display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 4px; vertical-align: -1px; }
#chart { width: 100%; overflow-x: auto; }
#chart svg { display: block; }
.layout { display: grid; grid-template-columns: minmax(300px, 420px) 1fr; gap: 20px; align-items: start; }
@media (max-width: 900px) { .layout { grid-template-columns: 1fr; } header { padding: 12px 16px; } main { padding: 16px; } }
table { width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums; }
th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--line); vertical-align: top; }
th { color: var(--muted); font-weight: 500; font-size: 12px; cursor: pointer; user-select: none; }
tbody tr { cursor: pointer; }
tbody tr:hover { background: var(--chip); }
tbody tr.sel { background: var(--sel); }
.num { text-align: right; }
.chip { display: inline-block; padding: 1px 8px; border-radius: 999px; background: var(--chip); font-size: 12px; margin: 0 4px 4px 0; }
.chip.err { color: var(--down); } .chip.ok { color: var(--up); } .chip.w { color: var(--warn); }
.detail h3 { margin: 0 0 4px; font-size: 16px; }
.q { color: var(--muted); margin-bottom: 12px; }
.causes { margin: 0; padding-left: 18px; }
.causes li { margin-bottom: 4px; }
.cols { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
@media (max-width: 700px) { .cols { grid-template-columns: 1fr; } }
.col h4 { margin: 0 0 6px; font-size: 13px; }
.col h4 .sw { width: 8px; height: 8px; }
.answer { white-space: pre-wrap; background: var(--code); border-radius: 8px; padding: 10px; font-size: 13px; max-height: 340px; overflow: auto; }
.dims { display: grid; grid-template-columns: 110px 1fr 70px; gap: 4px 10px; align-items: center; font-size: 13px; }
.bar { position: relative; height: 14px; background: var(--chip); border-radius: 3px; overflow: hidden; }
.bar i { position: absolute; left: 0; height: 7px; }
.bar i.a { top: 0; background: var(--a); } .bar i.b { bottom: 0; background: var(--b); }
.ev { border-left: 2px solid var(--line); padding: 2px 0 6px 10px; margin-left: 4px; font-size: 13px; }
.ev.tool { border-color: var(--b); } .ev.bad { border-color: var(--down); } .ev.val { border-color: var(--warn); }
details summary { cursor: pointer; }
pre { white-space: pre-wrap; word-break: break-word; background: var(--code); border-radius: 6px; padding: 8px;
  font-size: 12px; max-height: 260px; overflow: auto; margin: 4px 0; }
.muted { color: var(--muted); }
.empty { color: var(--muted); padding: 40px; text-align: center; }
</style>
</head>
<body>
<header>
  <h1>Eval Trace Viewer</h1>
  <label><span class="sw" style="background:var(--a)"></span>Lần A <select id="selA"></select></label>
  <label><span class="sw" style="background:var(--b)"></span>Lần B <select id="selB"></select></label>
  <label>Lọc <select id="filter">
    <option value="all">Tất cả case</option><option value="changed">Có thay đổi điểm</option>
    <option value="down">Giảm điểm</option><option value="up">Tăng điểm</option>
    <option value="unscored">Unscored / lỗi</option></select></label>
  <span class="muted" id="hint" style="font-size:12px"></span>
</header>
<main>
  <div class="cards" id="cards"></div>
  <div class="panel"><h2>Điểm theo case</h2>
    <div class="legend"><span><span class="sw" style="background:var(--a)"></span>A</span>
      <span><span class="sw" style="background:var(--b)"></span>B</span>
      <span>Bấm vào cột hoặc dòng để xem chi tiết</span></div>
    <div id="chart"></div></div>
  <div class="layout">
    <div class="panel"><h2>Danh sách case</h2><table><thead><tr>
      <th data-k="id">Case</th><th data-k="a" class="num">A</th><th data-k="b" class="num">B</th>
      <th data-k="d" class="num">Δ</th><th>Nguyên nhân chính</th></tr></thead><tbody id="rows"></tbody></table></div>
    <div class="panel detail" id="detail"><div class="empty">Chọn một case để xem trace và nguyên nhân.</div></div>
  </div>
</main>
<script>
const DIMS = {factuality: 40, completeness: 25, evidence: 20, boundaries: 15};
const DIM_VI = {factuality: 'Đúng sự thật', completeness: 'Đầy đủ', evidence: 'Dẫn chứng', boundaries: 'Giới hạn/phạm vi'};
const state = {runs: [], A: null, B: null, nameA: '', nameB: '', sel: null, sort: {k: 'id', dir: 1}};
const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt = v => v == null ? '—' : v;
const delta = (a, b) => (a == null || b == null) ? null : b - a;
const sign = d => d == null ? '—' : (d > 0 ? '+' + d : String(d));
const cls = d => d == null ? '' : d > 0 ? 'up' : d < 0 ? 'down' : '';
const store = {get(k){try{return localStorage.getItem(k)}catch(e){return null}}, set(k,v){try{localStorage.setItem(k,v)}catch(e){}}};

async function load() {
  state.runs = await (await fetch('/api/runs')).json();
  if (!state.runs.length) { $('#cards').innerHTML = '<div class="empty">Không tìm thấy file kết quả eval (*.json có summary và cases).</div>'; return; }
  const opts = state.runs.map(r => `<option value="${esc(r.name)}">${esc(r.name)} — ${r.summary?.score_0_100 ?? 'null'}</option>`).join('');
  $('#selA').innerHTML = opts; $('#selB').innerHTML = opts;
  const names = state.runs.map(r => r.name);
  const pick = (k, dflt) => names.includes(store.get(k)) ? store.get(k) : dflt;
  $('#selA').value = pick('tv.A', names.includes('eval_before.json') ? 'eval_before.json' : names[0]);
  $('#selB').value = pick('tv.B', names.includes('eval_after.json') ? 'eval_after.json' : names[names.length - 1]);
  $('#hint').textContent = state.runs.length < 2 ? 'Chỉ có một file kết quả: chạy thêm eval (ví dụ --output eval_after.json) để so sánh.' : '';
  await select();
}

async function getRun(name) { return (await fetch('/api/run?name=' + encodeURIComponent(name))).json(); }

async function select() {
  state.nameA = $('#selA').value; state.nameB = $('#selB').value;
  store.set('tv.A', state.nameA); store.set('tv.B', state.nameB);
  [state.A, state.B] = await Promise.all([getRun(state.nameA), getRun(state.nameB)]);
  render();
}

function caseMap(run) { const m = {}; (run?.cases || []).forEach(c => m[c.id] = c); return m; }
function score(c) { return c?.grade?.status === 'scored' ? c.grade.score : null; }

/* ---------- Phân tích trace ---------- */
function analyze(c) {
  if (!c) return null;
  const tr = c.result?.trace || [];
  const tools = tr.filter(t => t.event === 'tool');
  const toolErr = tools.filter(t => t.result && t.result.ok === false);
  const urls = new Set((String(c.result?.answer || '').match(/https?:\/\/[^\s)\]>"'`]+/g) || []).map(u => u.replace(/[.,;:]+$/, '')));
  const seen = new Set();
  tools.forEach(t => { const u = t.result?.url; if (u) seen.add(u); });
  const out = (c.result?.usage || []).reduce((s, u) => s + (u?.output_tokens || 0), 0);
  return {
    steps: tr.filter(t => t.event === 'model').length,
    tools, toolErr,
    names: tools.map(t => t.name),
    errNames: toolErr.map(t => `${t.name}: ${t.result.error || 'lỗi'}`),
    validations: tr.filter(t => t.event === 'validation_missing_source').length,
    finals: tr.some(t => t.event === 'final'),
    status: c.result?.status, error: c.result?.error,
    urls, seenUrls: seen,
    unsourced: [...urls].filter(u => seen.size && ![...seen].some(s => u.startsWith(s) || s.startsWith(u))),
    outTokens: out, answerLen: String(c.result?.answer || '').length,
    violations: c.grade?.mechanical?.violations || [], cap: c.grade?.mechanical?.score_cap,
  };
}

function countDiff(a, b) {
  const m = {}; a.forEach(x => m[x] = (m[x] || 0) - 1); b.forEach(x => m[x] = (m[x] || 0) + 1);
  return Object.entries(m).filter(([, v]) => v);
}

/* Trả list {w: trọng số, sev: 'up'|'down'|'warn'|'', text} */
function causes(a, b) {
  const out = [];
  if (!a || !b) { out.push({w: 100, sev: 'warn', text: `Case chỉ có trong lần ${a ? 'A' : 'B'}.`}); return out; }
  const ga = a.grade || {}, gb = b.grade || {}, xa = analyze(a), xb = analyze(b);
  if (gb.status !== 'scored') out.push({w: 100, sev: 'down', text: `B chưa được chấm: ${gb.reason || gb.status}` + (xb.error ? ` (agent: ${xb.error})` : '')});
  if (ga.status !== 'scored' && gb.status === 'scored') out.push({w: 90, sev: 'up', text: `A chưa được chấm (${ga.reason || ga.status}); B đã chấm được.`});
  if (xa.status !== xb.status) out.push({w: 80, sev: xb.status === 'completed' ? 'up' : 'down', text: `Trạng thái agent: ${xa.status} → ${xb.status}` + (xb.error ? ` (${xb.error})` : '')});
  const vAdd = xb.violations.filter(v => !xa.violations.includes(v)), vDel = xa.violations.filter(v => !xb.violations.includes(v));
  vAdd.forEach(v => out.push({w: 75, sev: 'down', text: `Vi phạm kiểm tra bằng code mới: ${v}` + (xb.cap != null ? ` → điểm bị chặn ở ${xb.cap}` : '')}));
  vDel.forEach(v => out.push({w: 70, sev: 'up', text: `Đã hết vi phạm: ${v}`}));
  if (gb.status === 'scored' && gb.raw_judge_score != null && gb.raw_judge_score > gb.score && !vAdd.length)
    out.push({w: 60, sev: 'down', text: `Judge cho ${gb.raw_judge_score} nhưng bị chặn còn ${gb.score} do: ${xb.violations.join('; ')}`});
  if (ga.status === 'scored' && gb.status === 'scored') {
    for (const k in DIMS) {
      const d = (gb.dimensions?.[k] ?? 0) - (ga.dimensions?.[k] ?? 0);
      if (d) out.push({w: 40 + Math.abs(d), sev: d > 0 ? 'up' : 'down', text: `${DIM_VI[k]} (${k}) ${sign(d)}: ${ga.dimensions[k]} → ${gb.dimensions[k]} / ${DIMS[k]}`});
    }
  }
  const nd = countDiff(xa.names, xb.names);
  if (nd.length) out.push({w: 35, sev: '', text: `Tool calls ${xa.tools.length} → ${xb.tools.length}: ` + nd.map(([n, v]) => `${v > 0 ? '+' : ''}${v} ${n}`).join(', ')});
  if (xa.toolErr.length !== xb.toolErr.length) out.push({w: 30, sev: 'warn', text: `Tool lỗi ${xa.toolErr.length} → ${xb.toolErr.length}` + (xb.errNames.length ? ` (B: ${xb.errNames.join('; ')})` : '')});
  if (xa.validations !== xb.validations) out.push({w: 30, sev: 'warn', text: `Nhắc thiếu URL nguồn (validation_missing_source): ${xa.validations} → ${xb.validations} lần`});
  if (xb.unsourced.length && !xa.unsourced.length) out.push({w: 45, sev: 'down', text: `B dẫn URL không thấy trong tool result: ${xb.unsourced.join(', ')}`});
  if (xa.unsourced.length && !xb.unsourced.length) out.push({w: 45, sev: 'up', text: `B không còn dẫn URL ngoài tool result.`});
  if (xa.urls.size && !xb.urls.size) out.push({w: 40, sev: 'down', text: `B không còn dẫn URL nào trong câu trả lời.`});
  if (!xa.urls.size && xb.urls.size) out.push({w: 40, sev: 'up', text: `B đã dẫn URL: ${[...xb.urls].join(', ')}`});
  if (xa.steps !== xb.steps) out.push({w: 15, sev: '', text: `Model steps ${xa.steps} → ${xb.steps}`});
  const lr = xa.answerLen ? xb.answerLen / xa.answerLen : 1;
  if (lr > 1.5 || lr < 0.67) out.push({w: 10, sev: '', text: `Độ dài câu trả lời ${xa.answerLen} → ${xb.answerLen} ký tự`});
  out.sort((p, q) => q.w - p.w);
  return out;
}

function mainCause(list, d) {
  if (!list.length) return '<span class="muted">Không có khác biệt đáng kể</span>';
  const pref = d == null ? list : list.filter(x => d < 0 ? x.sev === 'down' : d > 0 ? x.sev === 'up' : true);
  const c = (pref[0] || list[0]);
  return `<span class="${c.sev}">${esc(c.text)}</span>`;
}

/* ---------- Render ---------- */
function rowsData() {
  const ma = caseMap(state.A), mb = caseMap(state.B);
  const ids = [...new Set([...Object.keys(ma), ...Object.keys(mb)])];
  const order = id => ({E: 0, A: 1, H: 2}[id[0]] ?? 3) * 1000 + (parseInt(id.slice(1)) || 0);
  return ids.map(id => {
    const a = ma[id], b = mb[id], sa = score(a), sb = score(b), d = delta(sa, sb);
    return {id, a, b, sa, sb, d, ord: order(id), causes: causes(a, b),
      bad: (b && b.grade?.status !== 'scored') || (a && a.grade?.status !== 'scored') || b?.result?.status !== 'completed'};
  });
}

function render() {
  const sA = state.A.summary || {}, sB = state.B.summary || {};
  const all = rowsData();
  const up = all.filter(r => r.d > 0).length, down = all.filter(r => r.d < 0).length;
  const td = delta(sA.score_0_100, sB.score_0_100);
  const same = state.nameA === state.nameB;
  $('#cards').innerHTML = [
    card('Điểm tổng A', fmt(sA.score_0_100), `${sA.scored_cases ?? '?'}/${sA.total_cases ?? '?'} case đã chấm` + (sA.score_0_100 == null && sA.partial_mean_0_100 != null ? ` · partial ${sA.partial_mean_0_100}` : '')),
    card('Điểm tổng B', fmt(sB.score_0_100), `${sB.scored_cases ?? '?'}/${sB.total_cases ?? '?'} case đã chấm` + (sB.score_0_100 == null && sB.partial_mean_0_100 != null ? ` · partial ${sB.partial_mean_0_100}` : '')),
    card('Thay đổi', `<span class="${cls(td)}">${td == null ? '—' : sign(+td.toFixed(2))}</span>`, same ? 'A và B là cùng một file' : `${up} case tăng · ${down} case giảm`),
    card('Cấu hình B', esc(state.B.config?.model || '?'), `judge ${esc(state.B.config?.judge_model || '?')} · max_steps ${state.B.config?.max_steps ?? '?'}`),
  ].join('');
  drawChart(all);
  drawTable(all);
  if (state.sel) showDetail(state.sel);
}
const card = (k, v, s) => `<div class="card"><div class="k">${k}</div><div class="v">${v}</div><div class="s">${s}</div></div>`;

function filtered(all) {
  const f = $('#filter').value;
  return all.filter(r => f === 'all' || (f === 'changed' && r.d) || (f === 'down' && r.d < 0) || (f === 'up' && r.d > 0) || (f === 'unscored' && r.bad));
}

function drawChart(all) {
  const rows = [...all].sort((p, q) => p.ord - q.ord);
  const W = Math.max(720, rows.length * 46), H = 220, pl = 32, pb = 40, pt = 10, ch = H - pb - pt;
  const lo = 0, y = v => pt + ch - (v - lo) / (100 - lo) * ch, bw = (W - pl) / rows.length;
  let s = `<svg width="${W}" height="${H}" role="img" aria-label="Điểm theo case">`;
  for (const g of [0, 25, 50, 75, 100]) s += `<line x1="${pl}" x2="${W}" y1="${y(g)}" y2="${y(g)}" stroke="var(--line)"/><text x="${pl - 6}" y="${y(g) + 4}" text-anchor="end" font-size="10" fill="var(--muted)">${g}</text>`;
  rows.forEach((r, i) => {
    const x = pl + i * bw, w = Math.min(14, bw / 2 - 4), cx = x + bw / 2;
    const bar = (v, dx, col) => v == null
      ? `<text x="${cx + dx + w / 2}" y="${y(0) - 4}" text-anchor="middle" font-size="10" fill="var(--down)">✕</text>`
      : `<rect x="${cx + dx}" y="${y(v)}" width="${w}" height="${y(0) - y(v)}" rx="2" fill="${col}"><title>${r.id}: ${v}</title></rect>`;
    s += `<g style="cursor:pointer" data-id="${r.id}"><rect x="${x}" y="${pt}" width="${bw}" height="${ch + pb}" fill="${state.sel === r.id ? 'var(--sel)' : 'transparent'}"/>`;
    s += bar(r.sa, -w - 1, 'var(--a)') + bar(r.sb, 1, 'var(--b)');
    s += `<text x="${cx}" y="${H - pb + 14}" text-anchor="middle" font-size="11" fill="var(--text)">${r.id}</text>`;
    if (r.d) s += `<text x="${cx}" y="${H - pb + 28}" text-anchor="middle" font-size="10" fill="var(--${r.d > 0 ? 'up' : 'down'})">${sign(r.d)}</text>`;
    s += '</g>';
  });
  $('#chart').innerHTML = s + '</svg>';
  $('#chart').querySelectorAll('g[data-id]').forEach(g => g.onclick = () => showDetail(g.dataset.id));
}

function drawTable(all) {
  const {k, dir} = state.sort;
  const key = r => k === 'id' ? r.ord : k === 'a' ? (r.sa ?? -1) : k === 'b' ? (r.sb ?? -1) : (r.d ?? -999);
  const rows = filtered(all).sort((p, q) => (key(p) - key(q)) * dir);
  $('#rows').innerHTML = rows.map(r => `<tr data-id="${r.id}" class="${state.sel === r.id ? 'sel' : ''}">
    <td><b>${r.id}</b></td><td class="num">${fmt(r.sa)}</td><td class="num">${fmt(r.sb)}</td>
    <td class="num ${cls(r.d)}">${sign(r.d)}</td><td>${mainCause(r.causes, r.d)}</td></tr>`).join('')
    || '<tr><td colspan="5" class="muted">Không có case phù hợp bộ lọc.</td></tr>';
  $('#rows').querySelectorAll('tr[data-id]').forEach(tr => tr.onclick = () => showDetail(tr.dataset.id));
}

function showDetail(id) {
  state.sel = id;
  const r = rowsData().find(x => x.id === id);
  if (!r) return;
  document.querySelectorAll('#rows tr').forEach(tr => tr.classList.toggle('sel', tr.dataset.id === id));
  drawChart(rowsData());
  const c = r.b || r.a;
  const list = r.causes;
  let h = `<h3>${esc(id)} <span class="chip">${esc(c.scenario || '')}</span>
    <span class="${cls(r.d)}" style="font-size:14px">${fmt(r.sa)} → ${fmt(r.sb)} (${sign(r.d)})</span></h3>
    <div class="q">${esc(c.question)}</div>
    <div class="panel" style="background:var(--bg)"><h2>Nguyên nhân thay đổi</h2>`;
  h += state.nameA === state.nameB
    ? '<div class="muted">A và B là cùng một file. Chọn hai lần chạy khác nhau để thấy nguyên nhân thay đổi; bên dưới vẫn hiển thị đánh giá của judge.</div>'
    : (list.length ? `<ul class="causes">${list.map(x => `<li class="${x.sev}">${esc(x.text)}</li>`).join('')}</ul>` : '<div class="muted">Không có khác biệt đáng kể về trace hay điểm thành phần.</div>');
  h += `<div style="margin-top:8px"><b>Expected:</b> <span class="muted">${esc(c.expected)}</span></div></div>`;
  h += `<h2 style="font-size:14px">Điểm thành phần</h2><div class="dims">`;
  for (const k in DIMS) {
    const va = r.a?.grade?.dimensions?.[k], vb = r.b?.grade?.dimensions?.[k];
    h += `<div>${DIM_VI[k]}</div><div class="bar"><i class="a" style="width:${(va ?? 0) / DIMS[k] * 100}%"></i><i class="b" style="width:${(vb ?? 0) / DIMS[k] * 100}%"></i></div>
      <div class="${cls(delta(va, vb))}">${fmt(va)} → ${fmt(vb)}</div>`;
  }
  h += `</div><div class="cols" style="margin-top:16px">${side('A', r.a)}${side('B', r.b)}</div>`;
  $('#detail').innerHTML = h;
}

function side(label, c) {
  if (!c) return `<div class="col"><h4>Lần ${label}</h4><div class="muted">Không có case này.</div></div>`;
  const g = c.grade || {}, x = analyze(c);
  let h = `<div class="col"><h4><span class="sw" style="background:var(--${label.toLowerCase()})"></span>Lần ${label}: ${esc(label === 'A' ? state.nameA : state.nameB)}</h4>`;
  h += `<div><span class="chip ${x.status === 'completed' ? 'ok' : 'err'}">${esc(x.status)}</span>
    <span class="chip ${g.status === 'scored' ? 'ok' : 'err'}">${esc(g.status)}</span>
    <span class="chip">${x.steps} steps</span><span class="chip">${x.tools.length} tools</span>
    <span class="chip">${x.outTokens} output tokens</span>
    ${x.validations ? `<span class="chip w">${x.validations}× nhắc URL</span>` : ''}
    ${x.violations.map(v => `<span class="chip err">${esc(v)}</span>`).join('')}</div>`;
  if (x.error) h += `<div class="down" style="margin:6px 0">${esc(x.error)}</div>`;
  h += `<p><b>Judge:</b> ${esc(g.reason || '—')}</p>`;
  if (g.improvement) h += `<p class="muted"><b>Gợi ý:</b> ${esc(g.improvement)}</p>`;
  h += `<details open><summary><b>Câu trả lời</b></summary><div class="answer">${esc(c.result?.answer || '(rỗng)')}</div></details>`;
  h += `<details><summary><b>Trace (${(c.result?.trace || []).length} events)</b></summary>`;
  for (const t of c.result?.trace || []) {
    if (t.event === 'tool') {
      const bad = t.result && t.result.ok === false;
      h += `<div class="ev tool ${bad ? 'bad' : ''}">step ${t.step} · <b>${esc(t.name)}</b> ${bad ? `<span class="down">${esc(t.result.error || 'lỗi')}</span>` : ''}
        <pre>${esc(t.arguments)}</pre>${(t.notes || []).map(n => `<div class="warn" style="font-size:12px">⚑ ${esc(n)}</div>`).join('')}<details><summary class="muted">result</summary><pre>${esc(JSON.stringify(t.result, null, 2))}</pre></details></div>`;
    } else {
      const extra = Object.entries(t).filter(([k]) => !['event', 'step'].includes(k)).map(([k, v]) => `${k}=${esc(typeof v === 'object' ? JSON.stringify(v) : v)}`).join(' ');
      const kind = t.event === 'validation_missing_source' ? 'val' : /error|max_steps/.test(t.event) ? 'bad' : '';
      h += `<div class="ev ${kind}">step ${t.step ?? ''} · <b>${esc(t.event)}</b> <span class="muted">${extra}</span></div>`;
    }
  }
  return h + '</details></div>';
}

$('#selA').onchange = select; $('#selB').onchange = select;
$('#filter').onchange = () => drawTable(rowsData());
document.querySelectorAll('th[data-k]').forEach(th => th.onclick = () => {
  const k = th.dataset.k; state.sort = {k, dir: state.sort.k === k ? -state.sort.dir : (k === 'id' ? 1 : -1)}; drawTable(rowsData());
});
load();
</script>
</body>
</html>
'''


def main():
    parser = argparse.ArgumentParser(description='Trace viewer cho kết quả eval')
    parser.add_argument('--dir', default=os.path.dirname(os.path.abspath(__file__)), help='Thư mục chứa file *.json kết quả eval')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    root = os.path.abspath(args.dir)
    server = ThreadingHTTPServer(('127.0.0.1', args.port), make_handler(root))
    url = f'http://127.0.0.1:{args.port}/'
    runs = find_runs(root)
    print(f'Trace viewer: {url}  ({len(runs)} file kết quả trong {root})')
    print('Ctrl+C để dừng.')
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
