/* =================================================================
   edit-mode.js — in-browser WYSIWYG text editing for StoryReports.
   Drop-in: include AFTER render.js. Works with any report built by
   render.js (it walks the standard rendered DOM structure).

   What it does
   ------------
   • Adds a floating "✏️ edit text" button. In edit mode every text
     element becomes contentEditable.
   • Edits autosave to localStorage (survive reload) and can be
     EXPORTED to a JSON file (report_overrides.json).
   • Numbers, charts, tables and any element containing complex
     children are PROTECTED — never editable.

   Re-applying edits at build time
   -------------------------------
   The exported JSON maps stable keys → HTML. Keys mirror REPORT:
     {sectionId}::title | lede | sub
     {sectionId}::body::{i}
     {sectionId}::items::{j}::{field}     (kpis/recs/limits)
     {sectionId}::steps::{j}::{field}     (flow)
   An agent (or a build script) applies them back onto window.REPORT
   before regenerating content.js, so rebuilds never lose edits.

   Config (optional, set before this script loads):
     window.EDIT_MODE = { storageKey:'report_edits', exportName:'report_overrides.json' }
   ================================================================= */
(function () {
  var CFG = window.EDIT_MODE || {};
  var LSK = CFG.storageKey || 'report_edits';
  var EXPORT_NAME = CFG.exportName || 'report_overrides.json';

  function load() { try { return JSON.parse(localStorage.getItem(LSK) || '{}'); } catch (e) { return {}; } }
  function save(o) { localStorage.setItem(LSK, JSON.stringify(o)); }
  // an element is NOT editable if it wraps structural/interactive children
  function complex(el) { return !el || !!el.querySelector('div,table,svg,canvas,select,input,img,h1,h2'); }

  // Walk the rendered DOM → [{el, key}] mirroring the REPORT structure.
  function editables() {
    var out = [];
    function add(el, key) { if (el && !complex(el)) out.push({ el: el, key: key }); }
    document.querySelectorAll('main section[id]').forEach(function (sec) {
      var id = sec.id;
      add(sec.querySelector('.measure h2') || sec.querySelector('.fig-title'), id + '::title');
      add(sec.querySelector('.lede'), id + '::lede');
      add(sec.querySelector('.fig-sub'), id + '::sub');
      sec.querySelectorAll('.body-col > p').forEach(function (p, i) { add(p, id + '::body::' + i); });
      sec.querySelectorAll('.rec').forEach(function (r, j) {
        add(r.querySelector('h4'), id + '::items::' + j + '::title');
        add(r.querySelector('p'), id + '::items::' + j + '::body');
      });
      sec.querySelectorAll('.step').forEach(function (r, j) {
        add(r.querySelector('h4'), id + '::steps::' + j + '::title');
        add(r.querySelector('p'), id + '::steps::' + j + '::body');
      });
      sec.querySelectorAll('.kpi').forEach(function (r, j) {
        add(r.querySelector('.lab'), id + '::items::' + j + '::label');
        add(r.querySelector('.note'), id + '::items::' + j + '::note');
      });
      sec.querySelectorAll('.limit').forEach(function (r, j) { add(r.querySelector('p'), id + '::items::' + j + '::html'); });
    });
    return out;
  }

  function applyEdits() {
    var e = load();
    editables().forEach(function (o) { if (e[o.key] != null) o.el.innerHTML = e[o.key]; });
  }

  var editing = false;
  function setEdit(on) {
    editing = on;
    editables().forEach(function (o) {
      o.el.contentEditable = on; o.el.classList.toggle('ek-on', on);
      if (on) {
        o.el.dataset.ek = o.key;
        o.el.oninput = function () { var s = load(); s[o.key] = o.el.innerHTML; save(s); count(); };
      } else { o.el.removeAttribute('contenteditable'); }
    });
    document.getElementById('ek-toolbar').style.display = on ? 'flex' : 'none';
    tg.textContent = on ? '✓ סיום עריכה' : '✏️ עריכת טקסט';
    tg.classList.toggle('on', on);
  }
  function count() { document.getElementById('ek-count').textContent = Object.keys(load()).length + ' שינויים'; }
  function download(name, text) {
    var b = new Blob([text], { type: 'application/json;charset=utf-8' });
    var a = document.createElement('a'); a.href = URL.createObjectURL(b); a.download = name; a.click();
    setTimeout(function () { URL.revokeObjectURL(a.href); }, 2000);
  }

  // ---- UI ----
  var st = document.createElement('style');
  st.textContent =
    '.ek-on{outline:1px dashed #1CA8C4;outline-offset:3px;border-radius:3px}' +
    '.ek-on:hover{background:rgba(28,168,196,.07)}' +
    '.ek-on:focus{outline:2px solid #1CA8C4;background:#fff;box-shadow:0 0 0 4px rgba(28,168,196,.12)}' +
    '#ek-toggle{position:fixed;left:18px;bottom:18px;z-index:9999;background:#14273F;color:#fff;border:1px solid #1CA8C4;border-radius:10px;padding:10px 16px;font:700 14px/1 inherit;cursor:pointer;box-shadow:0 4px 14px rgba(0,0,0,.25)}' +
    '#ek-toggle.on{background:#1CA8C4;color:#06222b}' +
    '#ek-toolbar{position:fixed;left:18px;bottom:64px;z-index:9999;display:none;gap:8px;background:#0E2036;border:1px solid #294155;border-radius:10px;padding:10px 12px;box-shadow:0 6px 20px rgba(0,0,0,.3);align-items:center}' +
    '#ek-toolbar button{font:700 13px/1 inherit;border:1px solid #35506a;background:#1B3450;color:#EAF4F8;border-radius:8px;padding:8px 12px;cursor:pointer}' +
    '#ek-toolbar button:hover{border-color:#1CA8C4}#ek-toolbar .x{color:#8DA7BE;font-size:12px;margin-inline-start:4px}';
  document.head.appendChild(st);

  var tg = document.createElement('button'); tg.id = 'ek-toggle'; tg.textContent = '✏️ עריכת טקסט';
  var tb = document.createElement('div'); tb.id = 'ek-toolbar';
  tb.innerHTML = '<button id="ek-export">⬇ ייצוא עריכות</button><button id="ek-reset">↺ איפוס</button><span class="x" id="ek-count"></span>';
  document.body.appendChild(tg); document.body.appendChild(tb);
  tg.onclick = function () { setEdit(!editing); };
  tb.querySelector('#ek-export').onclick = function () { download(EXPORT_NAME, JSON.stringify(load(), null, 2)); };
  tb.querySelector('#ek-reset').onclick = function () {
    if (confirm('לאפס את כל העריכות ולחזור למקור?')) { localStorage.removeItem(LSK); location.reload(); }
  };

  function init() { applyEdits(); count(); }
  window.addEventListener('report:ready', function () { setTimeout(init, 60); });
  if (window.REPORT && document.querySelector('main section')) setTimeout(init, 60);
})();
