-- Read query behind the widget's `history` model key: the CPC change log for one job.
--
-- Appsmith binding (keep "Use prepared statements" ON — the value then binds as a
-- parameter rather than being pasted into the SQL string):
--
--     WHERE h.job_id = {{ appsmith.store.cpc_job_id }}::bigint
--
-- The ID goes through the Appsmith store, NOT `{{CpcOverrideTool.model.searchJobId}}`:
-- binding to the widget model creates a cycle (query.body -> widget.model ->
-- widget.defaultModel -> query.data), which Appsmith refuses to evaluate, silently.
-- onSearch writes the store via storeValue() and then runs this query.
--
-- Notes on the WHERE clause:
--   * `::bigint` — prepared-statement parameters arrive as text, and job_id is a bigint.
--   * `cost_per_click_cents IS NOT NULL` — the table snapshots the whole campaign row on
--     every change, so budget-only and status-only edits also land here. Without this
--     filter the log is mostly noise for a CPC tool.
--   * The date bound and LIMIT keep the result sane: this table takes ~7M rows a month
--     across all jobs, and a single job accumulates one snapshot per source per day.

SELECT h.created_at,
       h.source,
       h.cost_per_click_cents,
       h.changed_by,
       h.change_type
FROM backend_mkt.campaign_history_records h
WHERE h.job_id = {{ appsmith.store.cpc_job_id }}::bigint
  AND h.cost_per_click_cents IS NOT NULL
  AND h.created_at >= DATEADD(day, -90, CURRENT_DATE)
ORDER BY h.created_at DESC
LIMIT 500;
