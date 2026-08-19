-- Read query behind the widget's `history` model key: the CPC change log for one job.
--
-- Appsmith binding (keep "Use prepared statements" ON — the value then binds as a
-- parameter rather than being pasted into the SQL string):
--
--     WHERE h.job_id = {{ CpcOverrideTool.model.searchJobId }}::bigint
--
-- The widget writes `searchJobId` into its model when Search is pressed, and the
-- onSearch event triggers this query. `{{Widget.model.x}}` is the documented way to
-- read a value out of a custom widget; the triggerEvent payload has no documented
-- accessor, so don't bind to that.
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
WHERE h.job_id = {{ CpcOverrideTool.model.searchJobId }}::bigint
  AND h.cost_per_click_cents IS NOT NULL
  AND h.created_at >= DATEADD(day, -90, CURRENT_DATE)
ORDER BY h.created_at DESC
LIMIT 500;
