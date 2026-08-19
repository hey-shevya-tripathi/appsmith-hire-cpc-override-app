# HIRE Job-Level CPC Override Tool

Appsmith app for the PACS team to set and manage **CPC overrides per (HIRE job × source)**,
replacing the current manual Channable workflow.

Spec: [PACS H2 2026: HIRE Job-Level CPC Override Tool](https://heyjobs.atlassian.net/wiki/spaces/DMA/pages/5547360258/PACS+H2+2026+HIRE+Job-Level+CPC+Override+Tool)

Branch **`v1`** holds the UI build. The whole app is one Appsmith **custom widget**
(`CpcOverrideTool`), written as plain HTML/CSS/JS so it can be reviewed in git and
plugged into the APIs later without a rebuild.

> **Status: UI only.** No queries are wired yet — the widget ships with a sample model so
> it renders immediately. Two things are still outstanding on the backend side, per the spec:
> the read/write API endpoints, and the `update_restricted?`-style guard in
> `BudgetUpdates::Hire::UpdateCampaignBudget` that stops the daily BOS run from
> overwriting overrides. Until that guard exists, any override saved here would be
> wiped on the next BOS run.

## Layout

```
custom_widget/
  app.html            # widget markup      ← edit these
  app.css             # widget styles      ←
  app.js              # widget logic       ←
  build_widget.py     # compiles the three into the Appsmith DSL + preview
  preview.html        # generated: standalone browser preview with mock data
pages/Page1/widgets/CpcOverrideTool/
  CpcOverrideTool.json  # generated: the CUSTOM_WIDGET DSL Appsmith reads
```

After editing any source file:

```bash
python3 custom_widget/build_widget.py
```

## Previewing without Appsmith

Open `custom_widget/preview.html` in a browser. It stubs the `appsmith` runtime with
mock data and a fake backend, so search, override, remove and the validation guardrails
all behave like the real thing. Triggered events are logged to the console.

## What the UI does

| Spec requirement | UI |
|---|---|
| 3.1 Find & view jobs | Job ID search + status filter; job header (title, company, city, ID); per-source table with current CPC, algorithmic CPC, status badge, last modified by/at |
| 3.2 Create / edit override | Modal with € input, live before → after preview, min/max range validation, and a soft warning when the value exceeds `max_multiplier` × the algorithmic CPC (the 100× typo guardrail) |
| 3.3 Remove override | "Remove" action per overridden row → confirm modal showing the value it reverts to |
| 3.4 Data integrity | Algorithmic CPC is always displayed alongside the live value; the UI never treats the override as the only value |
| 3.5 Historical tracking | Change-history table per job; a **reason is mandatory** on both save and remove, so every event carries one |

## Wiring the APIs

The widget is driven entirely by its **Default Model** and four **Events**. Nothing in
the HTML/CSS/JS needs to change when the endpoints land — only these bindings.

### Default Model

Replace the sample values in the Default Model tab with query bindings:

```json
{
  "status": "{{Get_job.isLoading ? 'loading' : (Get_job.data ? 'ready' : 'idle')}}",
  "error": "{{Get_job.responseMeta.error?.message || ''}}",
  "job": "{{Get_job.data.job}}",
  "rows": "{{Get_job.data.sources}}",
  "history": "{{Get_history.data}}",
  "limits": { "min_cents": 5, "max_cents": 800, "max_multiplier": 5 },
  "toast": "{{appsmith.store.toast}}"
}
```

Field contract:

| Key | Shape |
|---|---|
| `status` | `'idle' \| 'loading' \| 'ready' \| 'error'` |
| `job` | `{ job_id, job_title, company_name, city }` |
| `rows[]` | `{ source_name, cost_per_click_cents, algorithmic_cpc_cents, is_override, changed_by, changed_at }` |
| `history[]` | `{ changed_at, source_name, old_value_cents, new_value_cents, changed_by, reason }` |
| `limits` | `{ min_cents, max_cents, max_multiplier }` |
| `toast` | `{ text, isError }` — optional, shown once |

All CPC values are **integer cents**, matching `mkt_db.campaigns.cost_per_click_cents`.
The UI does the €/cents conversion.

`is_override` is expected to come from the override flag on the live row — per the spec,
`changed_by` on `mkt_db.campaign_history_records` can serve as that signal (a non-pipeline
`changed_by` means the active value is manual).

### Events

| Event | Payload | Wire to |
|---|---|---|
| `onSearch` | `{ jobId }` | `Get_job.run({ jobId })` then `Get_history.run({ jobId })` |
| `onSaveOverride` | `{ jobId, source, cpcCents, previousCents, reason }` | `Save_override.run(...)` → re-run `Get_job` + `Get_history` |
| `onRemoveOverride` | `{ jobId, source, algorithmicCents, reason }` | `Remove_override.run(...)` → re-run `Get_job` + `Get_history` |
| `onRefresh` | — | re-run `Get_job` + `Get_history` |

The write endpoints own the history insert — the widget sends `reason` and expects the
backend to record the event against `mkt_db.campaign_history_records` with the acting user.

## Notes

- No external libraries — no CDN, no build step beyond the Python script.
- Accent colour is the HeyJobs brand token *Cosmo* `#d02879`; change `--accent` in
  `app.css` to restyle.
- All API/user text rendered into the DOM is HTML-escaped in `app.js`.
- Validation in the UI is a usability guardrail, not a security boundary — the write
  endpoints must enforce the min/max range server-side too.
