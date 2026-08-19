"""Compile the custom-widget sources into an Appsmith DSL widget and a local preview.

The hand-editable sources live in this folder (`app.html` / `app.css` / `app.js`).
Running this script writes:

* ``pages/Page1/widgets/CpcOverrideTool.json`` — the Appsmith ``CUSTOM_WIDGET`` DSL
  that the Appsmith git integration reads on branch ``v1``. This path and its
  formatting (unescaped unicode, 2-space indent) match what Appsmith itself writes
  back on sync, so a rebuild produces no spurious diff.
* ``custom_widget/preview.html`` — a standalone page that renders the widget in a
  browser against mock data, with a stub ``appsmith`` object. No Appsmith needed.

Usage::

    python3 custom_widget/build_widget.py
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SRC = Path(__file__).parent
REPO = SRC.parent
WIDGET_NAME = "CpcOverrideTool"
WIDGET_DIR = REPO / "pages" / "Page1" / "widgets"

EVENTS = ["onSearch", "onSaveOverride", "onRemoveOverride", "onRefresh"]

# Sample model shipped as the widget default so the UI renders before the APIs
# exist. Swap each key for a `{{Query.data}}` binding once the endpoints land —
# see README.md > "Wiring the APIs".
def _source(source: str, cpc: int | None, algo: int | None, **kwargs: Any) -> dict[str, Any]:
    """One `mkt_db.campaigns` row, shaped as the widget expects it."""
    return {
        "source": source,
        "cost_per_click_cents": cpc,
        "algorithmic_cpc_cents": algo,
        "is_override": kwargs.get("is_override", False),
        "changed_by": kwargs.get("changed_by", "hire_budget_updates"),
        "changed_at": kwargs.get("changed_at", "2026-08-19T05:30:08Z"),
        "source_campaign_status": kwargs.get("status", "active"),
    }


# Values and source names below mirror real rows in mkt_db.campaigns — CPCs sit in the
# 25–150 cent range and most of a job's ~25 sources carry no CPC at all.
MOCK_MODEL: dict[str, Any] = {
    "status": "ready",
    "error": "",
    "job": {
        "job_id": 34052274,
        "job_title": "Pflegefachkraft (m/w/d) — Vollzeit",
        "company_name": "Vitanas Gruppe",
        "city": "Berlin",
    },
    "limits": {"min_cents": 5, "max_cents": 300, "max_multiplier": 5},
    "rows": [
        _source("joblift", 250, 85, is_override=True,
                changed_by="shevya.tripathi@heyjobs.de", changed_at="2026-08-14T09:41:00Z"),
        _source("jobrapido", 96, 32, is_override=True,
                changed_by="justine.k@heyjobs.de", changed_at="2026-08-11T16:05:00Z"),
        _source("jobtome", 47, 47),
        _source("adzuna", 45, 45),
        _source("stellenonline", 41, 41),
        _source("jobworld", 35, 35),
        _source("jooble", 30, 30, changed_at="2026-07-22T12:20:02Z"),
        _source("allthetopbananas", 25, 25),
        _source("xing", 90, 90, changed_at="2026-06-03T20:26:26Z"),
        _source("talent_platform", 100, 100, changed_at="2026-07-22T12:20:02Z"),
        _source("facebook", None, None, changed_at="2026-06-03T20:26:21Z"),
        _source("ebay-kleinanzeigen", None, None, changed_at="2026-06-03T20:30:13Z"),
        _source("indeed", 0, 0, status="excluded", changed_at="2026-06-03T20:26:20Z"),
        _source("careerjet", 50, 50, status="paused", changed_at="2026-06-03T20:26:19Z"),
    ],
    # Snapshot rows, exactly as campaign_history_records stores them.
    "history": [
        {
            "created_at": "2026-08-19T05:30:09Z", "source": "jobtome",
            "cost_per_click_cents": 47, "changed_by": "hire_budget_updates",
            "change_type": "update", "reason": None,
        },
        {
            "created_at": "2026-08-18T05:06:09Z", "source": "jobtome",
            "cost_per_click_cents": 48, "changed_by": "hire_budget_updates",
            "change_type": "update", "reason": None,
        },
        {
            "created_at": "2026-08-14T09:41:00Z", "source": "joblift",
            "cost_per_click_cents": 250, "changed_by": "shevya.tripathi@heyjobs.de",
            "change_type": "update",
            "reason": "Underperforming slot — pushing visibility before contract review",
        },
        {
            "created_at": "2026-08-13T05:48:21Z", "source": "joblift",
            "cost_per_click_cents": 85, "changed_by": "hire_budget_updates",
            "change_type": "update", "reason": None,
        },
        {
            "created_at": "2026-08-11T16:05:00Z", "source": "jobrapido",
            "cost_per_click_cents": 96, "changed_by": "justine.k@heyjobs.de",
            "change_type": "update",
            "reason": "Client escalation, needs application volume this week",
        },
        {
            "created_at": "2026-08-10T05:48:24Z", "source": "jobrapido",
            "cost_per_click_cents": 32, "changed_by": "hire_budget_updates",
            "change_type": "update", "reason": None,
        },
    ],
}


def read_sources() -> dict[str, str]:
    """Read the three widget source files."""
    return {
        "html": (SRC / "app.html").read_text(encoding="utf-8"),
        "css": (SRC / "app.css").read_text(encoding="utf-8"),
        "js": (SRC / "app.js").read_text(encoding="utf-8"),
    }


# Names of the Appsmith queries this widget is wired to.
Q_SOURCES = "cpc_all_sources_per_job"
Q_HISTORY = "history"

RUN_QUERIES = f"{{{{ {Q_SOURCES}.run(); {Q_HISTORY}.run(); }}}}"

# The live Default Model.
#
# This MUST be a single string holding one `{{ ... }}` expression that evaluates to the
# whole model object — NOT a JSON object whose values happen to contain bindings.
# Appsmith evaluates the property as one binding; given an object it stores the inner
# "{{ ... }}" strings verbatim and the widget receives them as literal text.
#
# `searchJobId: null` declares the key so the queries can bind to
# `CpcOverrideTool.model.searchJobId`; the widget overwrites it via updateModel().
# `job` is absent because neither query returns job attributes — the widget falls back
# to the ID typed into its own search box.
BOUND_MODEL = f"""{{{{
  {{
    rows: {Q_SOURCES}.data || [],
    history: {Q_HISTORY}.data || [],
    searchJobId: null,
    limits: {{ min_cents: 5, max_cents: 300, max_multiplier: 5 }},
    status: ({Q_SOURCES}.isLoading || {Q_HISTORY}.isLoading)
      ? 'loading'
      : ({Q_SOURCES}.responseMeta && {Q_SOURCES}.responseMeta.error)
        ? 'error'
        : Array.isArray({Q_SOURCES}.data)
          ? ({Q_SOURCES}.data.length ? 'ready' : 'empty')
          : 'idle',
    error: ({Q_SOURCES}.responseMeta && {Q_SOURCES}.responseMeta.error
             && {Q_SOURCES}.responseMeta.error.message)
        || ({Q_HISTORY}.responseMeta && {Q_HISTORY}.responseMeta.error
             && {Q_HISTORY}.responseMeta.error.message)
        || ''
  }}
}}}}"""


def build_dsl(src_doc: dict[str, str]) -> dict[str, Any]:
    """Assemble the CUSTOM_WIDGET DSL node for the Appsmith page."""
    widget: dict[str, Any] = {
        "animateLoading": True,
        "borderColor": "#E0DEDE",
        "borderRadius": "{{appsmith.theme.borderRadius.appBorderRadius}}",
        "borderWidth": "0",
        "bottomRow": 132,
        "boxShadow": "none",
        "defaultModel": BOUND_MODEL,
        "dynamicBindingPathList": [
            {"key": "theme"},
            {"key": "borderRadius"},
            {"key": "defaultModel"},
        ],
        "dynamicHeight": "FIXED",
        "maxDynamicHeight": 9000,
        "minDynamicHeight": 4,
        "theme": "{{appsmith.theme}}",
        "dynamicTriggerPathList": [{"key": event} for event in EVENTS],
        "events": list(EVENTS),
        "isLoading": False,
        "isVisible": True,
        "key": "cpcovrwdgt",
        "leftColumn": 0,
        "minWidth": 280,
        "mobileBottomRow": 132,
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
        "topRow": 0,
        "type": "CUSTOM_WIDGET",
        "uncompiledSrcDoc": src_doc,
        "version": 1,
        "widgetId": "cpcoverride1",
        "widgetName": WIDGET_NAME,
    }
    # Read events fetch; the write events stay empty until the endpoints exist.
    actions = {"onSearch": RUN_QUERIES, "onRefresh": RUN_QUERIES}
    for event in EVENTS:
        widget[event] = actions.get(event, "")
    return widget


PREVIEW_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>HIRE CPC Override Tool — local preview</title>
<style>
{css}
/* preview-only chrome */
.preview-banner {{
  position: fixed; top: 0; left: 0; right: 0; z-index: 300;
  background: #14181f; color: #fff; font-family: var(--font);
  font-size: 12px; padding: 6px 16px; letter-spacing: .02em;
}}
.preview-banner b {{ color: #ff8dbd; }}
.app {{ padding-top: 48px; }}
</style>
</head>
<body>
<div class="preview-banner">
  <b>LOCAL PREVIEW</b> — mock data, no Appsmith. Events are logged to the browser console.
</div>
{html}
<script>
// ── Stub of the Appsmith custom-widget runtime ──────────────
const MOCK_MODEL = {model};
window.appsmith = {{
  model: MOCK_MODEL,
  _ready: null,
  onReady(fn) {{ this._ready = fn; fn(); }},
  updateModel(patch) {{
    this.model = {{ ...this.model, ...patch }};
    if (this._ready) this._ready();
  }},
  triggerEvent(name, payload) {{
    console.log('[appsmith.triggerEvent]', name, payload);
    simulate(name, payload);
  }},
}};

// Fake backend so the preview behaves like the real thing.
function simulate(name, payload) {{
  const m = window.appsmith.model;
  if (name === 'onSearch') {{
    window.appsmith.updateModel({{ status: 'loading' }});
    setTimeout(() => window.appsmith.updateModel({{
      status: 'ready',
      job: {{ ...m.job, job_id: payload.jobId }},
      toast: {{ text: 'Job loaded', isError: false }},
    }}), 500);
    return;
  }}
  if (name === 'onSaveOverride') {{
    const rows = m.rows.map((r) => r.source === payload.source
      ? {{ ...r, cost_per_click_cents: payload.cpcCents, is_override: true,
           changed_by: 'you@heyjobs.de', changed_at: new Date().toISOString() }}
      : r);
    const history = [{{
      created_at: new Date().toISOString(), source: payload.source,
      cost_per_click_cents: payload.cpcCents, changed_by: 'you@heyjobs.de',
      change_type: 'update', reason: payload.reason,
    }}, ...m.history];
    window.appsmith.updateModel({{ rows, history, toast: {{ text: 'Override saved', isError: false }} }});
    return;
  }}
  if (name === 'onRemoveOverride') {{
    const rows = m.rows.map((r) => r.source === payload.source
      ? {{ ...r, cost_per_click_cents: r.algorithmic_cpc_cents, is_override: false,
           changed_by: 'hire_budget_updates', changed_at: new Date().toISOString() }}
      : r);
    const history = [{{
      created_at: new Date().toISOString(), source: payload.source,
      cost_per_click_cents: payload.algorithmicCents, changed_by: 'you@heyjobs.de',
      change_type: 'update', reason: payload.reason,
    }}, ...m.history];
    window.appsmith.updateModel({{ rows, history, toast: {{ text: 'Override removed', isError: false }} }});
    return;
  }}
  if (name === 'onRefresh') {{
    window.appsmith.updateModel({{ toast: {{ text: 'Refreshed', isError: false }} }});
  }}
}}
</script>
<script>
{js}
</script>
</body>
</html>
"""


def build_preview(src: dict[str, str]) -> str:
    """Render the standalone browser preview with mock data and an appsmith stub."""
    return PREVIEW_TEMPLATE.format(
        css=src["css"],
        html=src["html"],
        js=src["js"],
        model=json.dumps(MOCK_MODEL, indent=2),
    )


def main() -> None:
    """Build the Appsmith widget JSON and the local preview page."""
    src = read_sources()

    WIDGET_DIR.mkdir(parents=True, exist_ok=True)
    widget_path = WIDGET_DIR / f"{WIDGET_NAME}.json"
    # ensure_ascii=False mirrors Appsmith's own serialisation — it rewrites escaped
    # unicode back to literal characters on sync, which would otherwise churn the diff.
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
