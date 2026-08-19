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
sql/
  20260819_read_job_cpc_by_source.sql   # reference read query (validated on main-dwh)
custom_widget/
  app.html            # widget markup      ← edit these
  app.css             # widget styles      ←
  app.js              # widget logic       ←
  build_widget.py     # compiles the three into the Appsmith DSL + preview
  preview.html        # generated: standalone browser preview with mock data
pages/Page1/widgets/
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
| 3.1 Find & view jobs | Job ID search + a "show" filter (active / overridden / priced / all); job header (title, company, city, ID); per-source table with current CPC, algorithmic CPC, status badge, last modified by/at |
| 3.2 Create / edit override | Modal with € input, live before → after preview, min/max range validation, and a soft warning when the value exceeds `max_multiplier` × the algorithmic CPC (the 100× typo guardrail) |
| 3.3 Remove override | "Remove" action per overridden row → confirm modal showing the value it reverts to |
| 3.4 Data integrity | Algorithmic CPC is always displayed alongside the live value; the UI never treats the override as the only value |
| 3.5 Historical tracking | Change-history table per job. `campaign_history_records` stores *snapshots*, not diffs, so the widget derives each "was → became" pair by comparing consecutive snapshots of the same source. A **reason is mandatory** on both save and remove — see gap 4 below on persisting it |

## Wiring the APIs

The widget is driven entirely by its **Default Model** and four **Events**. Nothing in
the HTML/CSS/JS needs to change when the endpoints land — only these bindings.

### Default Model

Replace the sample values in the Default Model tab with query bindings:

```json
{
  "status": "{{ !appsmith.store.cpc_job_id ? 'idle' : ... }}",
  "error":  "{{ cpc_all_sources_per_job.responseMeta... }}",
  "rows":    "{{ cpc_all_sources_per_job.data }}",
  "history": "{{ history.data }}",
  "limits": { "min_cents": 5, "max_cents": 300, "max_multiplier": 5 }
}
```

### Default Model must be ONE expression string

This is the trap that cost the most time. `defaultModel` has to be a **single string**
holding one `{{ ... }}` expression that evaluates to the whole model object:

```
{{
  {
    rows: cpc_all_sources_per_job.data || [],
    history: history.data || [],
    searchJobId: null,
    status: ...
  }
}}
```

**Not** a JSON object whose values contain bindings (`{"rows": "{{...}}"}`). Appsmith
evaluates the property as one binding; hand it an object and it stores the inner
`{{ ... }}` strings verbatim, so the widget receives them as literal text and renders
nothing. There is no error — it just sits there.

Declare `searchJobId: null` in that object so the key exists for the queries to bind to;
the widget overwrites it with `appsmith.updateModel()`.

### Other conventions worth copying

These come from the REACH-job-checker app (`feat/ui-redesign`), which runs the same
one-custom-widget architecture and is the reference for anything ambiguous here:

* **Don't carry a search value in the widget model.** The Default Model expression
  re-evaluates on every query state change, so a key declared in it is reset mid-search,
  while a key not declared in it may never be created. The job ID goes through
  `storeValue()` instead — durable, and untouched by re-evaluation. The queries read
  `{{ appsmith.store.cpc_job_id }}`, and `onSearch` writes it from `eventData.jobId`
  (the triggerEvent payload) with the model as a fallback.
* Binding a query to `{{CpcOverrideTool.model.x}}` while `defaultModel` binds back to
  that query's data is *not* a fatal cycle — the reference app does exactly this. It is
  only the lifetime of the value that makes the model a poor carrier.
* **Never use a form element.** Custom widgets render in a sandboxed iframe without
  `allow-forms`, so submission is blocked. Wire buttons with
  `addEventListener('click', ...)` and handle Enter explicitly.
* **Defer the event after `updateModel()`.** `updateModel` reaches the parent frame
  asynchronously, so trigger the event in a `setTimeout(..., 40)` or the query may run
  against the previous value.
* **Guard the API**: `appsmith.triggerEvent && appsmith.triggerEvent(...)`.
* Queries stay `MANUAL` and are run from event handlers.

## What the schema does and doesn't give us

Verified against the Redshift mirror of `mkt_db` (schema `backend_mkt`) on 2026-08-19.
Three gaps the endpoints have to close — `sql/20260819_read_job_cpc_by_source.sql` is a
runnable read query that closes the first two:

**1. There is no override flag column.** `mkt_db.campaigns` stores a single
`cost_per_click_cents` with no indication of where it came from. `is_override` has to be
derived: take the most recent `campaign_history_records` snapshot for that job × source
and check whether `changed_by` is a pipeline actor or not.

**2. There is no stored algorithmic value.** Same single-column problem — an override
destroys the algorithmic number in `campaigns`. It is recoverable only from history: the
most recent snapshot where `changed_by = 'hire_budget_updates'`. This satisfies spec 3.4
(the original value stays retrievable) but only for as long as history is retained, and
only if the write endpoint doesn't also write as `hire_budget_updates`.

**3. `changed_by` currently only ever holds system actors.** Every value in the last 30
days is a pipeline or callback name — `hire_budget_updates`, `reach_budget_updates`,
`JobModelCallback`, `contract_group_preference_cpc_changed` (the REACH override path),
and so on. No user emails. **The write endpoint must set `changed_by` to something
outside that set** — a user email, or a dedicated actor like `appsmith_cpc_override` —
or gaps 1 and 2 are both undetectable.

**4. `campaign_history_records` has no `reason` column.** The widget requires a reason on
every save and remove, per spec 3.5, and sends it in the event payload — but there is
nowhere to persist it today. This needs either a new column on the history table or a
side table keyed on the history record. Worth deciding before the endpoints are built;
the UI needs no change either way.

Also worth knowing for the UI: a single job carries **25–40 campaign rows**, most of them
`paused`/`excluded` with a NULL CPC. Live CPCs sit in the 25–150 cent range. That's why
the source table defaults to the "Active sources" filter and sorts overrides first, then
by CPC descending, with unpriced sources last.

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
