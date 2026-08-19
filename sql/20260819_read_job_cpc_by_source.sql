-- Read query behind the widget's `rows` model key: current CPC per source for one
-- HIRE job, with the algorithmic baseline and the override flag reconstructed from
-- campaign_history_records.
--
-- Written against the Redshift mirror (mkt_db -> backend_mkt). The production
-- endpoint will run the equivalent against mkt_db directly.
--
-- Two things this query has to reconstruct, because neither is stored on
-- mkt_db.campaigns:
--   1. algorithmic_cpc_cents — the last value the BOS pipeline itself wrote, i.e. the
--      most recent history snapshot with changed_by = 'hire_budget_updates'.
--   2. is_override — whether the *currently active* value came from a human rather
--      than a pipeline, judged by the changed_by of the latest snapshot.
--
-- `pipeline_actors` below is the allowlist of system writers seen in the last 30 days;
-- anything else is treated as a manual change. The override-writing endpoint must use
-- a changed_by value outside this list (a user email, or a dedicated actor such as
-- 'appsmith_cpc_override') or overrides will not be detectable.

WITH pipeline_actors AS (
    SELECT actor
    FROM (
        SELECT 'hire_budget_updates' AS actor
        UNION ALL SELECT 'reach_budget_updates'
        UNION ALL SELECT 'JobModelCallback'
        UNION ALL SELECT 'contract_group_excluded_sources_changed'
        UNION ALL SELECT 'contract_group_preference_cpc_changed'
        UNION ALL SELECT 'remote_campaign_update_callback'
        UNION ALL SELECT 'remote_campaign_creation_callback'
        UNION ALL SELECT 'remote_campaign_deletion_callback'
        UNION ALL SELECT 'remote_campaign_deactivate_callback'
        UNION ALL SELECT 'remote_campaign_activation_callback'
        UNION ALL SELECT 'linkedin_jobslot_campaign_update'
        UNION ALL SELECT 'sweep_unpublished_job_campaigns'
        UNION ALL SELECT 'SlaAutoResolveService'
        UNION ALL SELECT 'promote_to_hire'
        UNION ALL SELECT 'repost_as_reach'
        UNION ALL SELECT 'handle_job_contract_switch'
    )
),

-- Most recent history snapshot per source, whoever wrote it.
latest_change AS (
    SELECT h.source,
           h.changed_by,
           h.created_at,
           ROW_NUMBER() OVER (PARTITION BY h.source ORDER BY h.created_at DESC) AS rn
    FROM backend_mkt.campaign_history_records h
    WHERE h.job_id = :job_id
),

-- Most recent value the HIRE steering pipeline wrote — the algorithmic baseline.
latest_algorithmic AS (
    SELECT h.source,
           h.cost_per_click_cents,
           ROW_NUMBER() OVER (PARTITION BY h.source ORDER BY h.created_at DESC) AS rn
    FROM backend_mkt.campaign_history_records h
    WHERE h.job_id = :job_id
      AND h.changed_by = 'hire_budget_updates'
)

SELECT c.source,
       c.cost_per_click_cents,
       -- Fall back to the live value so an untouched source doesn't render as "—".
       COALESCE(a.cost_per_click_cents, c.cost_per_click_cents) AS algorithmic_cpc_cents,
       CASE
           WHEN l.changed_by IS NULL THEN FALSE
           WHEN l.changed_by IN (SELECT actor FROM pipeline_actors) THEN FALSE
           ELSE TRUE
       END AS is_override,
       l.changed_by,
       COALESCE(l.created_at, c.updated_at) AS changed_at,
       c.source_campaign_status,
       c.manual_min_cpc_cents,
       c.manual_max_cpc_cents
FROM backend_mkt.campaigns c
LEFT JOIN latest_change l
       ON l.source = c.source AND l.rn = 1
LEFT JOIN latest_algorithmic a
       ON a.source = c.source AND a.rn = 1
WHERE c.job_id = :job_id
ORDER BY is_override DESC,
         c.cost_per_click_cents DESC NULLS LAST,
         c.source;
