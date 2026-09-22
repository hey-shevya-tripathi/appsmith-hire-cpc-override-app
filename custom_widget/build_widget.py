"""Compile the custom-widget sources into an Appsmith DSL widget and a local preview.

Hand-editable sources live in this folder (`app.html` / `app.css` / `app.js`).
Running this script writes:

* ``pages/Page1/widgets/CpcOverride.json`` — the ``CUSTOM_WIDGET`` DSL that the
  Appsmith git integration reads. Path and formatting (flat, unescaped unicode,
  2-space indent) match what Appsmith itself writes back on sync, so a rebuild
  produces no spurious diff.
* ``custom_widget/preview.html`` — a standalone page that renders the widget in a
  browser against a stubbed API. No Appsmith needed.

Usage::

    python3 custom_widget/build_widget.py
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SRC = Path(__file__).parent
REPO = SRC.parent
WIDGET_NAME = "CpcOverride"
WIDGET_DIR = REPO / "pages" / "Page1" / "widgets"

EVENTS = ["onSearchCompanies", "onLoadJobs", "onSubmit", "onPoll", "onLoadHistory"]

# Appsmith query names this widget drives. Create these in the Appsmith UI against a
# REST datasource pointed at {mkt_backend host}/appsmith/v1 — see README.
Q_COMPANIES = "search_companies"
Q_JOBS = "get_overrides"
Q_SUBMIT = "submit_operation"
Q_POLL = "poll_operation"
Q_HISTORY = "list_operations"

# Event handlers.
#
# Each one snapshots the parameter out of the widget model into appsmith.store and then
# runs its query; the queries bind to the store, never to the widget model directly.
# The store is durable and is not touched when the Default Model expression
# re-evaluates, which happens on every query state change.
#
# `onSubmit` additionally captures the response — including a 422 — into
# `cpc_submit`, because a non-2xx REST response is not readable from `.data`.
HANDLERS: dict[str, str] = {
    "onSearchCompanies": (
        f"{{{{ storeValue('cpc_company_q', {WIDGET_NAME}.model.companyQuery)"
        f".then(() => {Q_COMPANIES}.run()) }}}}"
    ),
    "onLoadJobs": (
        f"{{{{ storeValue('cpc_job_query', {WIDGET_NAME}.model.jobQuery)"
        f".then(() => {Q_JOBS}.run()) }}}}"
    ),
    "onSubmit": (
        f"{{{{ storeValue('cpc_payload', {WIDGET_NAME}.model.pendingPayload)"
        f".then(() => {Q_SUBMIT}.run())"
        f".then((r) => storeValue('cpc_submit', {{ ok: true, data: r, at: Date.now() }}))"
        f".catch((e) => storeValue('cpc_submit', {{ ok: false, error: e, at: Date.now() }})) }}}}"
    ),
    "onPoll": (
        f"{{{{ storeValue('cpc_operation_id', {WIDGET_NAME}.model.pollOperationId)"
        f".then(() => {Q_POLL}.run()) }}}}"
    ),
    "onLoadHistory": (
        f"{{{{ storeValue('cpc_history_page', {WIDGET_NAME}.model.historyPage)"
        f".then(() => {Q_HISTORY}.run()) }}}}"
    ),
}

# The live Default Model.
#
# This MUST be a single string holding one `{{ ... }}` expression evaluating to the
# whole model object — NOT a JSON object whose values contain bindings. Appsmith
# evaluates the property as one binding; given an object it stores the inner
# "{{ ... }}" strings verbatim and the widget receives them as literal text.
#
# Keys the widget owns (companyQuery, jobQuery, pendingPayload, pollOperationId,
# historyPage) are deliberately NOT declared here. This expression re-evaluates on
# every query state change and would re-assert them, wiping what updateModel just
# wrote. The widget writes them; the handlers above read them.
BOUND_MODEL = f"""{{{{
  {{
    user: appsmith.user.email,
    companies: {Q_COMPANIES}.data || [],
    jobsData: {Q_JOBS}.data || null,
    jobsLoading: {Q_JOBS}.isLoading,
    submit: appsmith.store.cpc_submit || null,
    operation: {Q_POLL}.data || null,
    history: {Q_HISTORY}.data || null
  }}
}}}}"""


def read_sources() -> dict[str, str]:
    """Read the three widget source files."""
    return {
        "html": (SRC / "app.html").read_text(encoding="utf-8"),
        "css": (SRC / "app.css").read_text(encoding="utf-8"),
        "js": (SRC / "app.js").read_text(encoding="utf-8"),
    }


def build_dsl(src_doc: dict[str, str]) -> dict[str, Any]:
    """Assemble the CUSTOM_WIDGET DSL node for the Appsmith page."""
    widget: dict[str, Any] = {
        "animateLoading": True,
        "borderColor": "#E0DEDE",
        "borderRadius": "{{appsmith.theme.borderRadius.appBorderRadius}}",
        "borderWidth": "0",
        "bottomRow": 180,
        "boxShadow": "none",
        "defaultModel": BOUND_MODEL,
        "dynamicBindingPathList": [
            {"key": "theme"},
            {"key": "borderRadius"},
            {"key": "defaultModel"},
        ],
        "dynamicHeight": "FIXED",
        "dynamicTriggerPathList": [{"key": event} for event in EVENTS],
        "events": list(EVENTS),
        "isLoading": False,
        "isVisible": True,
        "key": "cpcovrwdgt",
        "leftColumn": 0,
        "maxDynamicHeight": 9000,
        "minDynamicHeight": 4,
        "minWidth": 280,
        "mobileBottomRow": 180,
        "mobileLeftColumn": 0,
        "mobileRightColumn": 64,
        "mobileTopRow": 0,
        "needsErrorInfo": False,
        "parentColumnSpace": 18.671875,
        "parentId": "0",
        "parentRowSpace": 10,
        "renderMode": "CANVAS",
        "responsiveBehavior": "fill",
        "rightColumn": 64,
        "srcDoc": src_doc,
        "theme": "{{appsmith.theme}}",
        "topRow": 0,
        "type": "CUSTOM_WIDGET",
        "uncompiledSrcDoc": src_doc,
        "version": 1,
        "widgetId": "cpcoverride2",
        "widgetName": WIDGET_NAME,
    }
    for event in EVENTS:
        widget[event] = HANDLERS.get(event, "")
    return widget


PREVIEW_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>HIRE CPC Override — local preview</title>
<style>
{css}
.preview-banner {{
  position: fixed; top: 0; left: 0; right: 0; z-index: 300;
  background: #16121a; color: #fff; font-family: var(--font);
  font-size: 11.5px; padding: 5px 16px; letter-spacing: .02em;
}}
.preview-banner b {{ color: #ff8dbd; }}
.app {{ padding-top: 26px; }}
</style>
</head>
<body>
<div class="preview-banner">
  <b>LOCAL PREVIEW</b> — stubbed API, no Appsmith. Try company "bau", or job IDs
  37990001, 37990002, 99. Events are logged to the console.
</div>
{html}
<script>
{stub}
</script>
<script>
{js}
</script>
</body>
</html>
"""

# A stub of the Appsmith runtime plus a fake mkt_backend, faithful to the API doc:
# async operation, poll to a final status, partial failure, and a 422 for a price
# outside the range.
PREVIEW_STUB = """
const COMPANIES = [
  { company_id: 1039559, name: 'Beispiel Baumarkt GmbH' },
  { company_id: 677232, name: 'Muster Bau & Service KG' },
];

const JOBS = [
  { job_id: 37990001, title: 'Lagerhelfer (m/w/d)', status: 'published', country_code: 'DE',
    company: COMPANIES[0],
    overrides: [ { source: 'jooble', cpc_cents: 45, created_by: 'pacs.user@heyjobs.de',
                   reason: 'Q4 push on warehouse roles', operation_id: 12,
                   created_at: '2026-09-22T09:14:03.211Z' } ] },
  { job_id: 37990002, title: 'Staplerfahrer (m/w/d)', status: 'published', country_code: 'DE',
    company: COMPANIES[0], overrides: [] },
  { job_id: 37990003, title: 'Kommissionierer (m/w/d)', status: 'published', country_code: 'DE',
    company: COMPANIES[0],
    overrides: [ { source: 'adzuna', cpc_cents: 60, created_by: 'pacs.user@heyjobs.de',
                   reason: 'Autumn peak', operation_id: 11,
                   created_at: '2026-09-20T11:02:00.000Z' } ] },
];

const apiState = { ops: {}, nextId: 20, history: [] };

window.appsmith = {
  user: { email: 'pacs.user@heyjobs.de' },
  _model: { user: 'pacs.user@heyjobs.de' },
  _ready: null,
  get model() { return this._model; },
  onReady(fn) { this._ready = fn; fn(); },
  updateModel(p) { this._model = { ...this._model, ...p }; this._ready && this._ready(); },
  triggerEvent(name, payload) { console.log('[triggerEvent]', name, payload); handle(name); },
  _set(patch) { this._model = { ...this._model, ...patch }; this._ready && this._ready(); },
};

function handle(name) {
  const m = window.appsmith.model;
  if (name === 'onSearchCompanies') {
    const q = String(m.companyQuery || '').toLowerCase();
    setTimeout(() => window.appsmith._set({
      companies: COMPANIES.filter((c) => c.name.toLowerCase().includes(q)),
    }), 180);
    return;
  }
  if (name === 'onLoadJobs') {
    const q = m.jobQuery || {};
    setTimeout(() => {
      if (q.company_id) {
        window.appsmith._set({ jobsData: { jobs: JOBS.map(clone), rejected: [] } });
      } else {
        const ids = String(q.job_ids || '').split(/[\\s,]+/).filter(Boolean);
        const jobs = [], rejected = [];
        ids.forEach((raw) => {
          const job = JOBS.find((j) => String(j.job_id) === raw);
          if (job) jobs.push(clone(job));
          else rejected.push({ job_id: Number(raw), reason: 'not_found' });
        });
        window.appsmith._set({ jobsData: { jobs, rejected } });
      }
    }, 260);
    return;
  }
  if (name === 'onSubmit') { submit(m.pendingPayload); return; }
  if (name === 'onPoll') {
    const op = apiState.ops[m.pollOperationId];
    if (op) window.appsmith._set({ operation: clone(op) });
    return;
  }
  if (name === 'onLoadHistory') {
    const per = 20, page = Number(m.historyPage) || 1;
    setTimeout(() => window.appsmith._set({
      history: { data: apiState.history.slice((page - 1) * per, page * per),
                 total: apiState.history.length, page, per_page: per },
    }), 150);
  }
}

const clone = (o) => JSON.parse(JSON.stringify(o));

// jooble DE is 14-98 in the spec's example; anything outside rejects the whole request.
function submit(payload) {
  setTimeout(() => {
    const bad = [];
    (payload.items || []).forEach((item, index) => {
      if (payload.action === 'set' && item.source === 'jooble' &&
          (item.cpc_cents < 14 || item.cpc_cents > 98)) {
        bad.push({ index, job_id: item.job_id, source: item.source,
                   reason: 'cpc_out_of_bounds', min_cents: 14, max_cents: 98 });
      }
    });
    if (bad.length) {
      window.appsmith._set({ submit: { ok: false, at: Date.now(), error: { body: {
        error: 'invalid_items',
        message: bad.length + ' of ' + payload.items.length + ' items are invalid',
        errors: bad } } } });
      return;
    }

    const id = apiState.nextId++;
    // One item is made to fail so the partial-failure path is exercised.
    const applied = (payload.items || []).slice(0, Math.max(1, payload.items.length - 1));
    const op = {
      id, action: payload.action, status: 'pending', reason: payload.reason,
      requested_by: payload.requested_by, idempotency_key: payload.idempotency_key,
      target: payload.target,
      meta_data: { item_count: payload.items.length, applied_count: 0, failed_count: 0 },
      created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
      items: [],
    };
    apiState.ops[id] = op;
    window.appsmith._set({ submit: { ok: true, at: Date.now(), data: clone(op) } });

    setTimeout(() => {
      op.status = 'processing';
      op.meta_data.applied_count = Math.floor(applied.length / 2);
    }, 1200);
    setTimeout(() => {
      const failed = payload.items.length - applied.length;
      op.status = failed ? 'completed_with_errors' : 'completed';
      op.meta_data = { item_count: payload.items.length, applied_count: applied.length,
                       failed_count: failed, failures: failed ? { no_campaign: failed } : {} };
      op.items = applied.map((i) => ({ ...i,
        changed_by: payload.action === 'set' ? 'cpc_override_set' : 'cpc_override_removed',
        created_at: new Date().toISOString() }));
      apiState.history.unshift(clone(op));
    }, 3200);
  }, 400);
}
"""


def build_preview(src: dict[str, str]) -> str:
    """Render the standalone browser preview against the stubbed API."""
    return PREVIEW_TEMPLATE.format(
        css=src["css"], html=src["html"], js=src["js"], stub=PREVIEW_STUB
    )


def main() -> None:
    """Build the Appsmith widget JSON and the local preview page."""
    src = read_sources()

    WIDGET_DIR.mkdir(parents=True, exist_ok=True)
    widget_path = WIDGET_DIR / f"{WIDGET_NAME}.json"
    widget_path.write_text(
        json.dumps(build_dsl(src), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    preview_path = SRC / "preview.html"
    preview_path.write_text(build_preview(src), encoding="utf-8")

    print(f"wrote {widget_path.relative_to(REPO)}")
    print(f"wrote {preview_path.relative_to(REPO)}")


if __name__ == "__main__":
    main()
