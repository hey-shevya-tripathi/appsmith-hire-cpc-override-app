// HIRE CPC Override Tool — Appsmith custom widget
//
// Model shape (bind in the Default Model tab; see README for the query bindings):
//   status:  'idle' | 'loading' | 'ready' | 'error'
//   error:   string
//   job:     { job_id, job_title, company_name, city }
//   rows:    [{ source, cost_per_click_cents, algorithmic_cpc_cents, is_override,
//               changed_by, changed_at, source_campaign_status }]
//   history: [{ created_at, source, cost_per_click_cents, changed_by,
//               change_type, reason }]
//   limits:  { min_cents, max_cents, max_multiplier }
//   toast:   { text, isError }   // optional, shown once per model update
//
// `rows` mirrors mkt_db.campaigns (one row per job × source, CPC in integer cents).
// `history` mirrors mkt_db.campaign_history_records, which stores *snapshots* — each
// row is the campaign as it stood after a change, not a diff. The widget derives the
// "was → became" pair by comparing consecutive snapshots of the same source.
//
// Events (Events tab):
//   onSearch({ jobId })
//   onSaveOverride({ jobId, source, cpcCents, previousCents, reason })
//   onRemoveOverride({ jobId, source, algorithmicCents, reason })
//   onRefresh()

const $ = (id) => document.getElementById(id);

const DEFAULT_LIMITS = { min_cents: 1, max_cents: 1000, max_multiplier: 5 };

// Every automated writer seen in campaign_history_records.changed_by. Anything outside
// this set is taken to be a person, which is how an override is detected — neither
// mkt_db.campaigns nor the history table stores an explicit override flag.
const PIPELINE_ACTORS = new Set([
  'hire_budget_updates', 'reach_budget_updates', 'JobModelCallback',
  'contract_group_excluded_sources_changed', 'contract_group_preference_cpc_changed',
  'remote_campaign_update_callback', 'remote_campaign_creation_callback',
  'remote_campaign_deletion_callback', 'remote_campaign_deactivate_callback',
  'remote_campaign_activation_callback', 'linkedin_jobslot_campaign_update',
  'sweep_unpublished_job_campaigns', 'SlaAutoResolveService', 'promote_to_hire',
  'repost_as_reach', 'handle_job_contract_switch',
]);

// The pipeline whose value counts as "the algorithmic CPC" for a HIRE job.
const ALGORITHMIC_ACTOR = 'hire_budget_updates';

const state = {
  bound: false,
  filter: 'active',
  rows: [],
  job: null,
  limits: DEFAULT_LIMITS,
  searchJobId: null, // last job ID submitted, mirrored into the model for the queries
  target: null,      // row being edited / reverted
  lastToast: null,
};

/* ── Formatting helpers ──────────────────────────────────── */

const model = () => appsmith.model || {};

// Keys owned by the Default Model bindings. A key written through updateModel() shadows
// the bound value, so these must never be echoed back in a patch — doing so freezes the
// widget on whatever those values were at the time of the write.
const BOUND_KEYS = ['rows', 'history', 'status', 'error', 'limits'];

/** Merge `patch` into the model without shadowing anything the bindings own. */
function patchModel(patch) {
  const carried = { ...model() };
  BOUND_KEYS.forEach((k) => delete carried[k]);
  try {
    if (appsmith.updateModel) appsmith.updateModel({ ...carried, ...patch });
  } catch (err) {
    console.error('updateModel failed', err);
  }
}
const limits = () => ({ ...DEFAULT_LIMITS, ...(model().limits || {}) });

/** Format a cents value as a euro string, e.g. 4200 -> "€42.00". */
function euro(cents) {
  if (cents === null || cents === undefined || cents === '') return '—';
  const n = Number(cents);
  return Number.isFinite(n) ? `€${(n / 100).toFixed(2)}` : '—';
}

/** Numeric cents, or null. Guards against Number(null) === 0 counting as a price. */
function cents(value) {
  if (value === null || value === undefined || value === '') return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

/** Escape user/API text before it goes into innerHTML. */
function esc(v) {
  if (v === null || v === undefined || v === '') return '';
  return String(v).replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

const dash = (v) => (v === null || v === undefined || v === '' ? '—' : esc(v));

/** Short, readable timestamp — falls back to the raw string if unparseable. */
function stamp(value) {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return esc(value);
  return d.toLocaleString('en-GB', {
    day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

/** Percentage delta of an override vs its algorithmic baseline. */
function deltaLabel(current, base) {
  if (!Number.isFinite(Number(current)) || !Number.isFinite(Number(base)) || !Number(base)) return '';
  const pct = ((Number(current) - Number(base)) / Number(base)) * 100;
  if (Math.abs(pct) < 0.5) return '';
  const cls = pct > 0 ? 'delta-up' : 'delta-down';
  return `<span class="delta ${cls}">${pct > 0 ? '+' : ''}${pct.toFixed(0)}%</span>`;
}

/* ── Deriving what the campaigns table doesn't store ─────── */

/**
 * `cpc_all_sources_per_job` reads mkt_db.campaigns, which holds a single CPC per source
 * with no record of where it came from. Fill in who last touched each source, whether
 * that was a person (an override), and the last value the HIRE pipeline itself wrote
 * (the algorithmic baseline) by walking the history rows for the same job.
 *
 * Anything the row already carries wins, so a future API that returns these fields
 * directly needs no change here.
 */
function enrichRows(rows, history) {
  const latest = new Map();
  const latestAlgorithmic = new Map();

  history
    .slice()
    .sort((a, b) => new Date(a.created_at) - new Date(b.created_at))
    .forEach((h) => {
      latest.set(h.source, h);
      if (h.changed_by === ALGORITHMIC_ACTOR) latestAlgorithmic.set(h.source, h);
    });

  return rows.map((row) => {
    const last = latest.get(row.source);
    const algorithmic = latestAlgorithmic.get(row.source);
    const isOverride = row.is_override !== undefined
      ? Boolean(row.is_override)
      : Boolean(last && last.changed_by && !PIPELINE_ACTORS.has(last.changed_by));

    return {
      ...row,
      is_override: isOverride,
      changed_by: row.changed_by ?? last?.changed_by ?? null,
      changed_at: row.changed_at ?? last?.created_at ?? row.updated_at ?? null,
      algorithmic_cpc_cents: row.algorithmic_cpc_cents
        ?? algorithmic?.cost_per_click_cents
        // No pipeline write on record — the live value is the best baseline we have.
        ?? row.cost_per_click_cents,
    };
  });
}

/* ── Rendering ───────────────────────────────────────────── */

function renderState(status, error) {
  const showState = status !== 'ready';
  $('state-card').hidden = !showState;
  $('result').hidden = showState;
  $('state-empty').hidden = status !== 'idle';
  $('state-loading').hidden = status !== 'loading';
  $('state-empty-result').hidden = status !== 'empty';
  $('state-error').hidden = status !== 'error';
  if (status === 'error') $('state-error-text').textContent = error || 'Could not load this job.';
  if (status === 'empty' && state.searchJobId) {
    $('state-empty-result-text').textContent =
      `Job ${state.searchJobId} has no campaigns with a CPC set. Check the job ID, or that it is a HIRE job.`;
  }
}

function renderJob(job, rows) {
  // The queries return campaign rows, not job attributes — so unless something binds
  // `job`, fall back to the ID the user searched for and drop the empty meta line.
  const hasMeta = Boolean(job.job_title || job.company_name || job.city);
  $('job-title').textContent =
    job.job_title || (job.job_id ? `Job ${job.job_id}` : 'Untitled job');
  $('job-company').textContent = job.company_name || '';
  $('job-city').textContent = job.city || '';
  $('job-company').hidden = !job.company_name;
  $('job-city').hidden = !job.city;
  document.querySelectorAll('.job-meta .dot').forEach((d, i) => {
    d.hidden = !hasMeta || (i === 0 ? !job.company_name : !job.city);
  });
  $('job-id').textContent = job.job_id || '—';

  const overrides = rows.filter((r) => r.is_override);
  const live = rows.map((r) => Number(r.cost_per_click_cents)).filter(Number.isFinite);
  const avg = live.length ? live.reduce((a, b) => a + b, 0) / live.length : null;

  $('stat-sources').textContent = rows.length;
  $('stat-overrides').textContent = overrides.length;
  $('stat-avg').textContent = avg === null ? '—' : euro(avg);
  $('override-chip').textContent =
    `${overrides.length} active override${overrides.length === 1 ? '' : 's'}`;
}

function rowHtml(row, idx) {
  const isOverride = Boolean(row.is_override);
  const badge = isOverride
    ? '<span class="badge badge-override">Override</span>'
    : '<span class="badge badge-algo">Algorithmic</span>';
  const delta = isOverride ? deltaLabel(row.cost_per_click_cents, row.algorithmic_cpc_cents) : '';
  const actions = isOverride
    ? `<button class="btn btn-ghost btn-sm" data-act="edit" data-idx="${idx}">Edit</button>
       <button class="btn-link" data-act="revert" data-idx="${idx}">Remove</button>`
    : `<button class="btn btn-ghost btn-sm" data-act="edit" data-idx="${idx}">Set override</button>`;

  return `<tr>
    <td><div class="stamp">
      <span class="src-name">${dash(row.source)}</span>
      <span class="stamp-when">${dash(row.source_campaign_status)}</span>
    </div></td>
    <td class="num"><span class="cpc ${isOverride ? 'cpc-override' : ''}">${euro(row.cost_per_click_cents)}</span> ${delta}</td>
    <td class="num"><span class="cpc-muted">${euro(row.algorithmic_cpc_cents)}</span></td>
    <td>${badge}</td>
    <td><div class="stamp">
      <span class="stamp-who">${dash(row.changed_by)}</span>
      <span class="stamp-when">${stamp(row.changed_at)}</span>
    </div></td>
    <td class="right"><div class="row-actions">${actions}</div></td>
  </tr>`;
}

/** A job carries 25+ source rows, most of them unpriced — filter to what's useful. */
function matchesFilter(row) {
  switch (state.filter) {
    case 'override': return Boolean(row.is_override);
    case 'priced': return cents(row.cost_per_click_cents) !== null;
    case 'active': return row.source_campaign_status === 'active' || Boolean(row.is_override);
    default: return true;
  }
}

/** Overrides first, then most expensive, with unpriced sources last. */
function sortRows(rows) {
  return rows.slice().sort((a, b) => {
    if (Boolean(a.is_override) !== Boolean(b.is_override)) return a.is_override ? -1 : 1;
    const av = cents(a.cost_per_click_cents);
    const bv = cents(b.cost_per_click_cents);
    if ((av === null) !== (bv === null)) return av === null ? 1 : -1;
    if (av !== null && av !== bv) return bv - av;
    return String(a.source || '').localeCompare(String(b.source || ''));
  });
}

function renderRows() {
  const rows = sortRows(state.rows.filter(matchesFilter));

  $('sources-body').innerHTML = rows.map((r) => rowHtml(r, state.rows.indexOf(r))).join('');
  $('sources-empty').hidden = rows.length > 0;
  $('rows-count').textContent =
    `${rows.length} of ${state.rows.length} source${state.rows.length === 1 ? '' : 's'}`;

  $('sources-body').querySelectorAll('button[data-act]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const row = state.rows[Number(btn.dataset.idx)];
      if (!row) return;
      if (btn.dataset.act === 'edit') openOverride(row);
      else openRevert(row);
    });
  });
}

/**
 * campaign_history_records stores snapshots, not diffs. Walk each source's
 * snapshots oldest-first so every event can show the value it replaced.
 */
function withPreviousValues(history) {
  const previous = new Map();
  return history
    .slice()
    .sort((a, b) => new Date(a.created_at) - new Date(b.created_at))
    .map((h) => {
      const was = previous.has(h.source) ? previous.get(h.source) : null;
      previous.set(h.source, h.cost_per_click_cents);
      return { ...h, was };
    })
    .reverse();
}

function renderHistory(rawHistory) {
  const history = withPreviousValues(rawHistory);
  $('history-body').innerHTML = history.map((h) => {
    const changed = h.was !== null && Number(h.was) !== Number(h.cost_per_click_cents);
    return `<tr>
      <td>${stamp(h.created_at)}</td>
      <td>${dash(h.source)}</td>
      <td class="num cpc-muted">${h.was === null ? '—' : euro(h.was)}</td>
      <td class="num ${changed ? 'cpc' : 'cpc-muted'}">${euro(h.cost_per_click_cents)}</td>
      <td>${dash(h.changed_by)}</td>
      <td>${dash(h.reason)}</td>
      <td class="muted">${dash(h.change_type)}</td>
    </tr>`;
  }).join('');
  $('history-empty').hidden = history.length > 0;
  $('history-count').textContent = `${history.length} event${history.length === 1 ? '' : 's'}`;
}

/**
 * Show what the widget last searched for versus what the model actually carries.
 * These must agree — the queries read the model value (snapshotted into the store by
 * the onSearch handler), so a mismatch is the difference between results and an empty
 * table, and is otherwise invisible.
 */
function renderEcho(m, status) {
  const el = $('search-echo');
  if (!state.searchJobId && m.searchJobId == null) { el.hidden = true; return; }
  const published = state.searchJobId ?? '—';
  const inModel = m.searchJobId ?? 'undefined';
  const agree = String(published) === String(inModel);
  el.hidden = false;
  el.classList.toggle('is-warn', !agree);
  el.textContent = agree
    ? `Job ${published} · ${status}`
    : `Searched ${published}, but the model carries ${inModel} — the queries will use ${inModel}.`;
}

function render(m) {
  const history = Array.isArray(m.history) ? m.history : [];
  const rawRows = Array.isArray(m.rows) ? m.rows : [];

  // The widget is the sole owner of searchJobId. If a Default Model re-evaluation drops
  // it while we still hold one, put it back — the queries bind to it, and a null there
  // means they run against no job at all.
  if (state.searchJobId && m.searchJobId == null && !state.restoringId) {
    state.restoringId = true;
    setTimeout(() => { state.restoringId = false; }, 200);
    patchModel({ searchJobId: state.searchJobId });
  }
  state.searchJobId = m.searchJobId ?? state.searchJobId;
  state.rows = enrichRows(rawRows, history);
  state.job = m.job || (state.searchJobId ? { job_id: state.searchJobId } : null);
  state.limits = limits();

  const status = m.status || (rawRows.length ? 'ready' : 'idle');
  renderEcho(m, status);
  renderState(status, m.error);

  if (status === 'ready') {
    renderJob(state.job || {}, state.rows);
    renderRows();
    renderHistory(history);
  } else {
    $('override-chip').textContent = '0 active overrides';
  }

  showToast(m.toast);
}

/* ── Toast ───────────────────────────────────────────────── */

let toastTimer = null;

function showToast(toast) {
  if (!toast || !toast.text) return;
  const key = `${toast.text}|${toast.isError}`;
  if (key === state.lastToast) return;   // don't re-fire on unrelated model updates
  state.lastToast = key;

  const el = $('toast');
  $('toast-text').textContent = toast.text;
  el.classList.toggle('is-error', Boolean(toast.isError));
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; state.lastToast = null; }, 3200);
}

/* ── Override modal ──────────────────────────────────────── */

function openOverride(row) {
  state.target = row;
  const base = Number(row.algorithmic_cpc_cents);
  const { min_cents, max_cents } = state.limits;

  $('override-title').textContent = row.is_override ? 'Edit CPC override' : 'Set CPC override';
  $('override-sub').textContent = `${row.source} · ${state.job?.job_title || ''}`.trim();
  $('override-algo').textContent = euro(row.algorithmic_cpc_cents);
  $('override-hint').textContent =
    `Allowed range ${euro(min_cents)} – ${euro(max_cents)}.` +
    (Number.isFinite(base) && base ? ` Algorithmic value is ${euro(base)}.` : '');
  $('override-hint').classList.remove('is-error');
  $('override-input').value = row.is_override && Number.isFinite(Number(row.cost_per_click_cents))
    ? (Number(row.cost_per_click_cents) / 100).toFixed(2)
    : '';
  $('override-reason').value = '';
  $('override-error').hidden = true;
  $('override-warn').hidden = true;

  validateOverride();
  $('override-modal').classList.add('is-open');
  setTimeout(() => $('override-input').focus(), 40);
}

/** Validate the input, paint the preview/warnings, return cents or null. */
function validateOverride() {
  const raw = $('override-input').value.trim();
  const { min_cents, max_cents, max_multiplier } = state.limits;
  const base = Number(state.target?.algorithmic_cpc_cents);
  const errEl = $('override-error');
  const warnEl = $('override-warn');
  const preview = $('override-preview');

  warnEl.hidden = true;
  errEl.hidden = true;

  if (raw === '') { preview.textContent = '—'; return null; }

  const euros = Number(raw);
  if (!Number.isFinite(euros)) {
    preview.textContent = '—';
    return fail(errEl, 'Enter a numeric CPC value.');
  }

  const cents = Math.round(euros * 100);
  preview.textContent = euro(cents);

  if (cents < min_cents || cents > max_cents) {
    return fail(errEl, `CPC must be between ${euro(min_cents)} and ${euro(max_cents)}.`);
  }

  // Typo guardrail: flag (but don't block) large jumps off the algorithmic value.
  if (Number.isFinite(base) && base > 0 && cents / base > max_multiplier) {
    warnEl.textContent =
      `This is ${(cents / base).toFixed(1)}× the algorithmic CPC of ${euro(base)}. Double-check before saving.`;
    warnEl.hidden = false;
  }
  return cents;
}

function fail(el, message) {
  el.textContent = message;
  el.hidden = false;
  return null;
}

function submitOverride() {
  const cents = validateOverride();
  if (cents === null) {
    if ($('override-error').hidden) fail($('override-error'), 'Enter a CPC value.');
    return;
  }
  const reason = $('override-reason').value.trim();
  if (!reason) return fail($('override-error'), 'A reason is required — it is written to the history log.');

  appsmith.triggerEvent('onSaveOverride', {
    jobId: state.job?.job_id,
    source: state.target?.source,
    cpcCents: cents,
    previousCents: state.target?.cost_per_click_cents ?? null,
    reason,
  });
  closeModal('override-modal');
}

/* ── Revert modal ────────────────────────────────────────── */

function openRevert(row) {
  state.target = row;
  $('revert-sub').textContent = `${row.source} · ${state.job?.job_title || ''}`.trim();
  $('revert-current').textContent = euro(row.cost_per_click_cents);
  $('revert-algo').textContent = euro(row.algorithmic_cpc_cents);
  $('revert-reason').value = '';
  $('revert-error').hidden = true;
  $('revert-modal').classList.add('is-open');
  setTimeout(() => $('revert-reason').focus(), 40);
}

function submitRevert() {
  const reason = $('revert-reason').value.trim();
  if (!reason) return fail($('revert-error'), 'A reason is required — it is written to the history log.');

  appsmith.triggerEvent('onRemoveOverride', {
    jobId: state.job?.job_id,
    source: state.target?.source,
    algorithmicCents: state.target?.algorithmic_cpc_cents ?? null,
    reason,
  });
  closeModal('revert-modal');
}

function closeModal(id) { $(id).classList.remove('is-open'); }

/* ── Wiring ──────────────────────────────────────────────── */

/**
 * Publish the entered job ID, then ask Appsmith to fetch.
 *
 * The onSearch handler copies `searchJobId` into the Appsmith store, and the queries
 * bind to the store rather than to this widget's model — binding them to the model
 * would close a loop (query -> model -> defaultModel -> query.data) that Appsmith
 * silently refuses to evaluate.
 */
function submitSearch() {
  const jobId = $('search-input').value.trim();
  if (!jobId) return;
  state.searchJobId = Number(jobId) || jobId;

  // Write the ID into the model, which the queries bind to, then let Appsmith settle
  // before triggering the fetch — updateModel propagates to the parent frame
  // asynchronously, so firing the event in the same tick can run the queries against
  // the previous ID.
  patchModel({ searchJobId: state.searchJobId });
  setTimeout(() => {
    if (appsmith.triggerEvent) appsmith.triggerEvent('onSearch', { jobId: state.searchJobId });
  }, 40);
}

function bindEvents() {
  if (state.bound) return;
  state.bound = true;

  // Click + Enter rather than form submit — see the note in app.html.
  $('search-btn').addEventListener('click', submitSearch);
  $('search-input').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); submitSearch(); }
  });

  $('filter-status').addEventListener('change', (e) => {
    state.filter = e.target.value;
    renderRows();
  });

  $('refresh').addEventListener('click', () => appsmith.triggerEvent('onRefresh'));

  $('override-input').addEventListener('input', validateOverride);
  $('override-submit').addEventListener('click', submitOverride);
  $('revert-submit').addEventListener('click', submitRevert);

  [['override-close', 'override-modal'], ['override-cancel', 'override-modal'],
   ['revert-close', 'revert-modal'], ['revert-cancel', 'revert-modal']]
    .forEach(([btn, modal]) => $(btn).addEventListener('click', () => closeModal(modal)));

  ['override-modal', 'revert-modal'].forEach((id) => {
    $(id).addEventListener('click', (e) => { if (e.target.id === id) closeModal(id); });
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') ['override-modal', 'revert-modal'].forEach(closeModal);
  });
}

// appsmith.onReady fires on initial load AND on every model update.
appsmith.onReady(() => {
  bindEvents();
  render(model());
});
