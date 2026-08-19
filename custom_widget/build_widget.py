"""Compile the custom-widget sources into an Appsmith DSL widget and a local preview.

The hand-editable sources live in this folder (`app.html` / `app.css` / `app.js`).
Running this script writes:

* ``pages/Page1/widgets/CpcOverrideTool/CpcOverrideTool.json`` — the Appsmith
  ``CUSTOM_WIDGET`` DSL that the Appsmith git integration reads on branch ``v1``.
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
WIDGET_DIR = REPO / "pages" / "Page1" / "widgets" / WIDGET_NAME

EVENTS = ["onSearch", "onSaveOverride", "onRemoveOverride", "onRefresh"]

# Sample model shipped as the widget default so the UI renders before the APIs
# exist. Swap each key for a `{{Query.data}}` binding once the endpoints land —
# see README.md > "Wiring the APIs".
MOCK_MODEL: dict[str, Any] = {
    "status": "ready",
    "error": "",
    "job": {
        "job_id": "8f3c1a2e-77b4-4d51-9a0c-2e11d3c9b840",
        "job_title": "Pflegefachkraft (m/w/d) — Vollzeit",
        "company_name": "Vitanas Gruppe",
        "city": "Berlin",
    },
    "limits": {"min_cents": 5, "max_cents": 800, "max_multiplier": 5},
    "rows": [
        {
            "source_name": "stepstone",
            "cost_per_click_cents": 185,
            "algorithmic_cpc_cents": 92,
            "is_override": True,
            "changed_by": "shevya.tripathi@heyjobs.de",
            "changed_at": "2026-08-14T09:41:00Z",
        },
        {
            "source_name": "indeed",
            "cost_per_click_cents": 74,
            "algorithmic_cpc_cents": 74,
            "is_override": False,
            "changed_by": "bos_pipeline",
            "changed_at": "2026-08-19T03:12:00Z",
        },
        {
            "source_name": "jobrapido",
            "cost_per_click_cents": 240,
            "algorithmic_cpc_cents": 61,
            "is_override": True,
            "changed_by": "justine.k@heyjobs.de",
            "changed_at": "2026-08-11T16:05:00Z",
        },
        {
            "source_name": "talent_com",
            "cost_per_click_cents": 58,
            "algorithmic_cpc_cents": 58,
            "is_override": False,
            "changed_by": "bos_pipeline",
            "changed_at": "2026-08-19T03:12:00Z",
        },
    ],
    "history": [
        {
            "changed_at": "2026-08-14T09:41:00Z",
            "source_name": "stepstone",
            "old_value_cents": 92,
            "new_value_cents": 185,
            "changed_by": "shevya.tripathi@heyjobs.de",
            "reason": "Underperforming slot — pushing visibility before contract review",
        },
        {
            "changed_at": "2026-08-11T16:05:00Z",
            "source_name": "jobrapido",
            "old_value_cents": 61,
            "new_value_cents": 240,
            "changed_by": "justine.k@heyjobs.de",
            "reason": "Client escalation, needs application volume this week",
        },
        {
            "changed_at": "2026-08-02T11:20:00Z",
            "source_name": "stepstone",
            "old_value_cents": 140,
            "new_value_cents": 92,
            "changed_by": "bos_pipeline",
            "reason": "Algorithmic recompute",
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


def build_dsl(src_doc: dict[str, str]) -> dict[str, Any]:
    """Assemble the CUSTOM_WIDGET DSL node for the Appsmith page."""
    widget: dict[str, Any] = {
        "animateLoading": True,
        "borderColor": "#E0DEDE",
        "borderRadius": "{{appsmith.theme.borderRadius.appBorderRadius}}",
        "borderWidth": "0",
        "bottomRow": 132,
        "boxShadow": "none",
        "defaultModel": MOCK_MODEL,
        "dynamicBindingPathList": [{"key": "borderRadius"}],
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
    # Each declared event needs an (initially empty) action property.
    for event in EVENTS:
        widget[event] = ""
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
    const rows = m.rows.map((r) => r.source_name === payload.source
      ? {{ ...r, cost_per_click_cents: payload.cpcCents, is_override: true,
           changed_by: 'you@heyjobs.de', changed_at: new Date().toISOString() }}
      : r);
    const history = [{{
      changed_at: new Date().toISOString(), source_name: payload.source,
      old_value_cents: payload.previousCents, new_value_cents: payload.cpcCents,
      changed_by: 'you@heyjobs.de', reason: payload.reason,
    }}, ...m.history];
    window.appsmith.updateModel({{ rows, history, toast: {{ text: 'Override saved', isError: false }} }});
    return;
  }}
  if (name === 'onRemoveOverride') {{
    const rows = m.rows.map((r) => r.source_name === payload.source
      ? {{ ...r, cost_per_click_cents: r.algorithmic_cpc_cents, is_override: false,
           changed_by: 'bos_pipeline', changed_at: new Date().toISOString() }}
      : r);
    const history = [{{
      changed_at: new Date().toISOString(), source_name: payload.source,
      old_value_cents: m.rows.find((r) => r.source_name === payload.source).cost_per_click_cents,
      new_value_cents: payload.algorithmicCents,
      changed_by: 'you@heyjobs.de', reason: payload.reason,
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
    widget_path.write_text(
        json.dumps(build_dsl(src), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    preview_path = SRC / "preview.html"
    preview_path.write_text(build_preview(src), encoding="utf-8")

    print(f"wrote {widget_path.relative_to(REPO)}")
    print(f"wrote {preview_path.relative_to(REPO)}")


if __name__ == "__main__":
    main()
