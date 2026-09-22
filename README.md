# HIRE CPC Override — Appsmith app

Lets PACS set and remove CPC overrides on HIRE job × MSG source pairs, replacing the
manual Channable feed rules.

Built against the **mkt_backend Appsmith API v1** spec (epic
[MTI-1753](https://heyjobs.atlassian.net/browse/MTI-1753)) and the Miro wireframe.
This branch (`v2`) is a clean build — nothing carries over from the earlier `v1`
prototype, which predated the API.

[Open the app](https://mkt-admin-app.production.heyjobs.de/applications/6a8566dec8557fcf8ed87adf/pages/6a8566dec8557fcf8ed87ae2) ·
[Edit](https://mkt-admin-app.production.heyjobs.de/applications/6a8566dec8557fcf8ed87adf/pages/6a8566dec8557fcf8ed87ae2/edit)

> **The write API changes live prices.** There is no dry run. Every accepted
> `POST /cpc_override_operations` sets real CPCs within seconds. The read endpoints are
> safe to poke at.

## Layout

```
custom_widget/
  app.html            widget markup    ← edit these three
  app.css             widget styles    ←
  app.js              widget logic     ←
  build_widget.py     compiles them into the Appsmith DSL + a local preview
  preview.html        generated: runs standalone against a stubbed API
pages/Page1/widgets/
  CpcOverride.json    generated: the CUSTOM_WIDGET Appsmith reads
```

After editing any source file:

```bash
python3 custom_widget/build_widget.py
```

Open `custom_widget/preview.html` in a browser to exercise the whole flow with no
Appsmith and no backend — company search, the grid, the editor, a 422 rejection, the
async run with partial failure, and the audit log. Try company **bau**, or job IDs
`37990001, 37990002, 99`.

## Appsmith setup

### 1. Datasource

Create a **REST API** datasource named `mkt_backend`:

| Field | Value |
|---|---|
| URL | `{mkt_backend host}/appsmith/v1` |
| Header | `X-Auth-Token: <mkt_backend_api_key>` |

The key is a secret — set it in the Appsmith UI, never in this repo.

### 2. Queries

Five queries on `Page1`, all **run manually** (the widget triggers them). Each reads its
parameter from `appsmith.store`, which the widget's event handlers populate.

| Name | Method | Path |
|---|---|---|
| `search_companies` | GET | `/cpc_override_companies?q={{appsmith.store.cpc_company_q}}` |
| `get_overrides` | GET | see below |
| `submit_operation` | POST | `/cpc_override_operations` · body `{{ appsmith.store.cpc_payload }}` |
| `poll_operation` | GET | `/cpc_override_operations/{{appsmith.store.cpc_operation_id}}` |
| `list_operations` | GET | `/cpc_override_operations?page={{appsmith.store.cpc_history_page}}&per_page=20` |

`get_overrides` takes exactly one of `company_id` or `job_ids` — sending both is a 400 —
so the path picks whichever the widget staged:

```
/cpc_overrides?{{ appsmith.store.cpc_job_query.company_id
  ? 'company_id=' + appsmith.store.cpc_job_query.company_id
  : 'job_ids=' + appsmith.store.cpc_job_query.job_ids }}
```

`submit_operation` needs **Content-Type: application/json**.

### 3. Widget

Drop a **Custom widget** on `Page1` and pull this branch; `CpcOverride.json` carries the
source, the Default Model and all five event handlers already wired. If Appsmith does
not pick the file up, paste `app.html` / `app.css` / `app.js` into the widget's three
source tabs and copy the Default Model and handlers out of `build_widget.py`.

## How state moves

Hard-won on the earlier prototype, and the reason the wiring looks the way it does:

* **Default Model is one expression string** returning the whole object — not a JSON
  object whose values contain bindings. Given an object, Appsmith stores the inner
  `{{ … }}` strings verbatim and the widget receives them as literal text, silently.
* **Parameters travel through `appsmith.store`, not the model.** The Default Model
  expression re-evaluates on every query state change, so any key it declares is
  re-asserted mid-flight. Handlers snapshot the widget's value into the store, then run
  the query; queries only ever bind to the store.
* **Never echo a bound key back through `updateModel`** — a key written that way shadows
  the bound value permanently. `patchModel()` strips them.
* **No form elements.** Custom widgets render in a sandboxed iframe without
  `allow-forms`, so submission is blocked and the submit event never fires. Buttons are
  wired by click.
* **The POST result is captured into `appsmith.store.cpc_submit`** by the handler with
  `.then`/`.catch`. A 422 is a non-2xx response and is not readable from `.data` — and
  the 422 body is exactly what tells the user which rows were rejected.
* **`eventData` does not exist** in this Appsmith version; referencing it fails the
  linter and the handler never runs. Payloads go through the model, not the event.

## Where this differs from the wireframe

Both open questions the wireframe flagged were settled by the API, and **both were
settled against the wireframe**. The build follows the API.

**1 · Overrides are CPC-only.** The API takes `cpc_cents` and nothing else, and rejects
non-CPC sources with `source_not_cpc`. The wireframe's facebook *daily budget* row and
jobworld *bid category* row cannot be built — there is no field to carry either. Only
per-click sources are offered.

**2 · One action per operation.** `action` sits on the operation, not the item, so an
operation is all-sets or all-removes. The wireframe applies adds and removals in a
single trip, which the API cannot express as one call. The editor still lets you stage
both — dropping one source and adding another is one thought — but **Apply posts up to
two operations in sequence** and says so before you commit
(`2 set + 1 removal = 3 items · 2 operations`). They appear as two rows in the audit
log, which is honest: they are two operations.

If either decision is revisited, both are contained — the value field and the item
expansion live in `buildItems()`.

**3 · Per-pair failure reasons are not available.** The detail endpoint returns the pairs
that *applied* plus an aggregate count per reason (`failures: {"no_campaign": 1}`). The
UI computes failed pairs as submitted-minus-applied, lists them, and shows the reason
counts separately — it cannot say which reason belongs to which pair.

## Behaviour worth knowing

* **Rows already at the requested price are skipped**, so the item count reflects real
  changes rather than the size of the selection.
* **A removal is only sent for jobs that actually carry that override**, rather than for
  every selected job — the rest would be guaranteed failures.
* **Polling** runs every 2.5s and gives up after 5 minutes, pointing the user at the
  audit log rather than spinning forever.
* **A fresh idempotency key per submit**, reused on retry, so a double-click cannot
  apply twice.

## Open asks for the backend team

1. **An endpoint listing overridable sources and their bounds.** Nothing exposes which
   sources are `use_cpc` for a country, so `SOURCES` in `app.js` is hardcoded from §6.3
   of the technical plan and will drift.
2. **Bounds before submit, not after.** The spec says the UI needs no copy of the ranges
   because a 422 returns them — true, but it means the only way to discover that `bild`
   tops out at 30¢ is to be rejected. With bounds up front the input can show the range
   and validate before the round trip. The endpoint in (1) would cover this.
3. **Per-item failure reasons on the operation detail.** See divergence 3.

## Not built

* **Undo** — v1 reverses a change by making the opposite change; both stay on the audit
  log. Matches rule 11 on the wireframe, and the API offers no undo endpoint.
* **Drill-down on an audit row.** `GET /cpc_override_operations/:id` returns the applied
  items, so a row could expand to show them. Worth adding: if the tab is closed
  mid-operation the audit log is the only record, and it currently has no item detail.
