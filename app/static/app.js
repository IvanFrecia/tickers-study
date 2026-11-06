const statusClass = {
  active: "status-active",
  under_review: "status-under_review",
  unknown: "status-unknown",
};

const alertSeverityClass = {
  critical: "severity-critical",
  warning: "severity-warning",
  info: "severity-info",
};

const businessSeverityClass = {
  critical: "severity-critical",
  warning: "severity-warning",
  info: "severity-info",
  good: "",
};

const HELP_TEXT = {
  Configured: "Ticker count declared in configs/tickers.toml.",
  "Visible Rows": "Total rows currently shown after merging configured, discovered, weekly-status, and ledger symbols.",
  "Current Forecasts": "Tickers that are on the current weekly target cycle.",
  "Stale Forecasts": "Tickers that are behind the current weekly cycle and need catch-up retraining or publishing.",
  "Low Accuracy": "Tickers with weak resolved forecast quality and a business-facing warning.",
  "Watch Accuracy": "Tickers with mixed resolved forecast quality that should be watched closely.",
  "Forecast Feeds": "Tickers with forward data available from ledger, weekly summary, or forecast files.",
  "Evaluation Feeds": "Tickers with backward/evaluation data available from evaluation files, prior-week resolution, or historical rollups.",
  "Avg MAE": "Average latest MAE across rows that currently have evaluated values.",
  Active: "Tickers currently marked active by the weekly model-quality gate.",
  "Under Review": "Tickers currently marked under_review by the weekly model-quality gate.",
  "Under review": "Tickers currently marked under_review by the weekly model-quality gate.",
  "Weighted Week Return": "Portfolio weighted expected return from week-start close to target week-end close.",
  "Hist Samples": "Total historical predicted-vs-actual points used for rollup metrics.",
  "Hist Avg MAPE": "Portfolio average absolute percent error across historical evaluation samples.",
  "Hist <=2% Error": "Share of historical samples with absolute percent error at or below 2%.",
  "Hist Weeks": "Resolved target-close weeks available for this ticker.",
  "Prior Week Resolved": "Tickers where the previous-week prediction already has an actual close to compare.",
  "Prior Week MAE": "Mean absolute error for resolved previous-week outcomes.",
  "Prior Direction Hit": "Percent of resolved previous-week outcomes where predicted direction matched realized direction.",
  "Prior-week accuracy": "Direction hit and MAE for resolved previous-week outcomes. Shown as unavailable when no week has resolved yet.",
  "Target Week-End": "Current market week-end close date targeted by the weekly workflow.",
  "Market Status": "Live NYSE regular-session status at the API server's current market time.",
  "Market Time": "Current exchange-local time used for target-week freshness checks.",
  "Latest Session": "Most recent exchange trading session on or before the current market date.",
  "Next Session": "Next exchange trading session after the current market date.",
  "Week Closure": "Named exchange closure inside the current Monday-Friday calendar week.",
  "Calendar Source": "Calendar backend used for market sessions and holiday closures.",
  "Open Alerts": "Current count of failed-ticker alert items from automation state and weekly file.",
  "Open / critical alerts": "Failed-ticker alerts that need triage before charts. Critical usually means a current failure state.",
  "Critical Alerts": "High-priority alerts that usually indicate current failure state.",
  "Warning Alerts": "Medium-priority alerts that need review but are not hard failures.",
  Freshness: "How many tickers are on the current target week versus stale and behind.",
  "Typical Gap": "Typical absolute weekly miss from forecast to actual, shown as a percentage of actual close.",
  "Latest Gap": "Most recent resolved weekly miss from forecast to actual, shown as a percentage of actual close.",
  "Direction Hit": "Share of resolved weeks where the forecast called the correct up/down move.",
  "Forecast Health": "Business-facing view of freshness and accuracy for this ticker.",
  Tone: "Directional tone from expected week return percent.",
  "Projected Move": "Expected percent move from current close to selected week-end projection.",
  MAE: "Latest mean absolute error from daily evaluation output.",
  "Target Close Date": "Expected market week-end close date for this ticker.",
  "Projected Week-End Close": "Projected close selected for the target market week-end date.",
  "Target Close": "Current projected close for the selected target market week-end date.",
  "Selected Date": "Actual forecast point selected by projection rules.",
  Coverage: "Whether this ticker is being refreshed live, still waiting for a first score, or only showing stale historical output.",
  Cohort: "Display coverage for the ticker: live automation, live with score pending, stale history, or forecast missing.",
  "Forecast Source": "Primary source currently supplying forward week-end projection data for the ticker.",
  "Evaluation Source": "Primary source currently supplying backward validation data for the ticker.",
  Ticker: "Ticker symbol selected for this detail panel.",
  Status: "Current status from weekly summary (active, under_review, or unknown).",
  "Last Close": "Most recent close used as the reference for week-forward projection.",
  "Week-End Target": "Target market close date for this weekly projection cycle.",
  "Selected Forecast Date": "Forecast date selected to represent target week-end close.",
  "Week Return": "Projected percent return from last close to selected week-end close.",
  "Live MAE": "Latest evaluation mean absolute error from reports/daily.",
  "Live RMSE": "Latest evaluation root mean squared error from reports/daily.",
  MAPE: "Latest evaluation absolute percent error from reports/daily.",
  "Model MAE": "Backtest MAE reported by the latest weekly retrain run.",
  "Model RMSE": "Backtest RMSE reported by the latest weekly retrain run.",
  "Eval Samples": "Number of points included in the latest evaluation payload.",
  "Projection Selection": "Rule used to select target row (exact close or nearest prior session).",
  "Prior Outcome": "Previous-week comparison resolution status.",
  "Prior Target Date": "Target week-end date from the previous weekly run.",
  "Prior Predicted Close": "Previous run's predicted close for its target week-end date.",
  "Prior Actual Close": "Realized close for the previous run target date.",
  "Prior Abs Error": "Absolute difference between previous predicted and realized close.",
  "Prior Error %": "Percent error between previous predicted and realized close.",
  "Prior Gap": "Predicted close minus actual close for the previous resolved weekly target.",
  "Prior Direction": "Whether previous predicted return direction matched realized direction.",
  "Cycle Status": "State of the current forecast cycle: open or resolved.",
  "Initial Forecast": "The first frozen week-ahead call for the current target close date.",
  initial_forecast: "The first frozen week-ahead call for the current target close date. Later revisions do not overwrite it.",
  "Latest Forecast": "The most recent revision for the current target close date.",
  latest_forecast: "The most recent revision for the current target close date. It does not replace the frozen initial_forecast.",
  "Resolved Actual": "Realized target close once the cycle has completed.",
  resolved_actual: "Realized target close once the cycle has completed. Shown as not resolved until an actual exists.",
  revisions: "Later calls in the same target-week cycle. They are additive history; they never overwrite initial_forecast.",
  "Current Initial Call": "First frozen predicted target close for the current open cycle.",
  "Current Latest Call": "Latest predicted target close for the current open cycle.",
  "Current Actual Close": "Latest realised close used as the live reference, or the resolved target close once the current cycle has completed.",
  "Rolling Gap": "Latest predicted target close minus the resolved actual close.",
  "First-Call KPI": "Week-ahead accuracy for the first frozen forecast.",
  "Rolling KPI": "Accuracy for the latest revision in the same target cycle.",
  "History Samples": "Total historical predicted-vs-actual rows collected for this ticker.",
  "History Forecast Dates": "Distinct forecast dates represented in historical samples.",
  "History Window": "Date window covered by this ticker's historical samples.",
  "History MAE": "Historical mean absolute error for this ticker.",
  "History RMSE": "Historical root mean squared error for this ticker.",
  "History MAPE": "Historical mean absolute percent error for this ticker.",
  "History Bias": "Average signed error (predicted minus actual) for this ticker.",
  "History Bias %": "Average signed percent error for this ticker.",
  "History Abs Error P50": "Median absolute error for this ticker.",
  "History Abs Error P90": "90th percentile absolute error for this ticker.",
  "History Abs Error Max": "Maximum absolute error observed for this ticker.",
  "History <=1/2/5%": "Coverage rates within 1%, 2%, and 5% absolute percent error.",
  "History Cycles": "Resolved forecast cycles available in target-close history.",
  "History Rolling MAE": "Mean absolute error for the latest revision in each resolved weekly cycle.",
  "History Direction Hit": "Percent of resolved weeks where the first frozen direction matched the realized move.",
  "Alert Severity": "Per-ticker alert severity derived from automation and weekly file signals.",
  "Alert Messages": "Number of alert messages currently open for this ticker.",
  "Alert Source": "Primary alert source for the selected ticker (automation, weekly file, or both).",
  "As of": "When this dashboard payload was generated by the API.",
  "Market clock": "Exchange-local session status and time used for freshness checks.",
  "Target week": "Current market week-end close date targeted by the weekly workflow.",
};

const UNAVAILABLE = "Unavailable";

const dom = {
  summaryCards: document.getElementById("summaryCards"),
  alertsSummary: document.getElementById("alertsSummary"),
  alertsList: document.getElementById("alertsList"),
  alertFilters: document.getElementById("alertFilters"),
  tickerGrid: document.getElementById("tickerGrid"),
  refreshButton: document.getElementById("refreshButton"),
  userName: document.getElementById("userName"),
  userRole: document.getElementById("userRole"),
  logoutLink: document.getElementById("logoutLink"),
  detailTitle: document.getElementById("detailTitle"),
  detailSubtitle: document.getElementById("detailSubtitle"),
  detailStatus: document.getElementById("detailStatus"),
  detailNotice: document.getElementById("detailNotice"),
  forecastChart: document.getElementById("forecastChart"),
  closeFocus: document.getElementById("closeFocus"),
  errorChart: document.getElementById("errorChart"),
  snapshotGrid: document.getElementById("snapshotGrid"),
  weekPathMeta: document.getElementById("weekPathMeta"),
  weekPathTable: document.getElementById("weekPathTable"),
  cycleMeta: document.getElementById("cycleMeta"),
  cycleTable: document.getElementById("cycleTable"),
  historyMeta: document.getElementById("historyMeta"),
  historyTable: document.getElementById("historyTable"),
  heroTargetWeek: document.getElementById("heroTargetWeek"),
  heroAsOf: document.getElementById("heroAsOf"),
  heroMarketClock: document.getElementById("heroMarketClock"),
  heroCohorts: document.getElementById("heroCohorts"),
  loadBanner: document.getElementById("loadBanner"),
  mainContent: document.getElementById("mainContent"),
  tickerDetail: document.getElementById("tickerDetail"),
};

const state = {
  overview: null,
  selectedSymbol: null,
  user: null,
  alertSeverityFilter: "all",
  lastTrackedSymbol: null,
};

let helpTipSeq = 0;

function track(eventName, props = {}) {
  const detail = { event: eventName, ts: Date.now(), ...props };
  try {
    window.dispatchEvent(new CustomEvent("tickers:analytics", { detail }));
  } catch (_err) {
    // Analytics is best-effort; never block the dashboard.
  }
}

function prefersReducedMotion() {
  return Boolean(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function roleLabel(role) {
  if (role === "owner") {
    return "Owner / Superuser";
  }
  if (role === "admin") {
    return "Admin";
  }
  return "End User";
}

function isPresentNumber(value) {
  return typeof value === "number" && !Number.isNaN(value);
}

function formatNumber(value, digits = 2) {
  if (!isPresentNumber(value)) {
    return UNAVAILABLE;
  }
  return value.toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function formatPct(value, digits = 2) {
  if (!isPresentNumber(value)) {
    return UNAVAILABLE;
  }
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(digits)}%`;
}

function formatGapPct(value, digits = 2) {
  if (!isPresentNumber(value)) {
    return UNAVAILABLE;
  }
  return `+/- ${Math.abs(value).toFixed(digits)}%`;
}

function formatCount(value) {
  if (!isPresentNumber(value)) {
    return UNAVAILABLE;
  }
  return String(value);
}

function formatDateTime(value) {
  if (typeof value !== "string" || !value) {
    return UNAVAILABLE;
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    timeZoneName: "short",
  });
}

function setText(node, value) {
  if (node) {
    node.textContent = value;
  }
}

function marketStatusLabel(clock) {
  if (!clock || typeof clock !== "object") {
    return UNAVAILABLE;
  }
  if (clock.is_market_open_now) {
    return "Open";
  }
  if (clock.is_market_session) {
    return "Closed";
  }
  return "Closed / no session";
}

function weekClosureSummary(clock) {
  const closures = Array.isArray(clock?.week_closures) ? clock.week_closures : [];
  if (!closures.length) {
    return "None";
  }
  return closures
    .map((closure) => {
      const date = closure?.date || UNAVAILABLE;
      const name = closure?.name || "Exchange closed";
      return `${date} ${name}`;
    })
    .join(", ");
}

function businessHealthWarning(detail) {
  const health = detail?.business_health || {};
  const stateKey = health.state || "";
  if (!stateKey || stateKey === "on_track") {
    return null;
  }
  return {
    label: health.label || "Attention needed",
    message: health.message || "This ticker needs review.",
    severity: businessSeverityClass[health.severity] || "severity-info",
  };
}

function resolvedComparisonRows(detail) {
  const historyRows = Array.isArray(detail?.history_rows) ? detail.history_rows : [];
  if (historyRows.length) {
    return historyRows
      .filter(
        (row) =>
          typeof row?.target_week_end_date === "string" &&
          typeof row?.actual_close === "number" &&
          (typeof row?.initial_predicted_close === "number" || typeof row?.latest_predicted_close === "number")
      )
      .map((row) => ({
        forecast_date: row.target_week_end_date,
        predicted_close:
          typeof row.initial_predicted_close === "number" ? row.initial_predicted_close : row.latest_predicted_close,
        latest_predicted_close:
          typeof row.latest_predicted_close === "number" ? row.latest_predicted_close : row.initial_predicted_close,
        actual_close: row.actual_close,
        first_call_absolute_error: row.first_call_absolute_error,
        latest_absolute_error: row.latest_absolute_error,
        revision_count: row.revision_count,
      }));
  }

  const perDate = Array.isArray(detail?.evaluation?.per_date) ? detail.evaluation.per_date : [];
  if (perDate.length) {
    return perDate;
  }

  const previousWeek = detail?.previous_week_comparison || {};
  if (
    typeof previousWeek.predicted_close === "number" &&
    typeof previousWeek.actual_close === "number" &&
    typeof previousWeek.target_week_end_date === "string"
  ) {
    return [
      {
        forecast_date: previousWeek.target_week_end_date,
        predicted_close: previousWeek.predicted_close,
        actual_close: previousWeek.actual_close,
      },
    ];
  }

  const resolvedActual = detail?.resolved_actual || {};
  const latestForecast = detail?.latest_forecast || {};
  if (
    typeof resolvedActual.actual_target_close === "number" &&
    typeof latestForecast.predicted_target_close === "number" &&
    typeof detail?.target_week_end_date === "string"
  ) {
    return [
      {
        forecast_date: detail.target_week_end_date,
        predicted_close: latestForecast.predicted_target_close,
        actual_close: resolvedActual.actual_target_close,
      },
    ];
  }

  return [];
}

function helpLabel(label, helpKey = label) {
  const tip = HELP_TEXT[helpKey] || `Definition for ${label}.`;
  helpTipSeq += 1;
  const tipId = `tip-${String(helpKey)
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "")}-${helpTipSeq}`;
  return `<span class="help-label">${escapeHtml(label)}<button type="button" class="help-dot" aria-expanded="false" aria-controls="${tipId}" aria-label="About ${escapeHtml(label)}">?</button><span id="${tipId}" class="help-tip" role="tooltip">${escapeHtml(tip)}</span></span>`;
}

function closeAllTips() {
  document.querySelectorAll(".help-dot[aria-expanded='true']").forEach((btn) => {
    btn.setAttribute("aria-expanded", "false");
    btn.closest(".help-label")?.classList.remove("is-open");
  });
}

function initHelpTooltips() {
  document.addEventListener("click", (event) => {
    const btn = event.target.closest?.(".help-dot");
    if (!btn) {
      closeAllTips();
      document.body.classList.remove("hide-tips");
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    document.body.classList.remove("hide-tips");
    const expanded = btn.getAttribute("aria-expanded") === "true";
    closeAllTips();
    if (!expanded) {
      btn.setAttribute("aria-expanded", "true");
      btn.closest(".help-label")?.classList.add("is-open");
      track("tooltip_open", { field_key: btn.getAttribute("aria-label") || "" });
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") {
      return;
    }
    document.body.classList.add("hide-tips");
    closeAllTips();
  });
}

function resizeVisibleCharts() {
  if (!window.Plotly) {
    return;
  }
  [dom.forecastChart, dom.errorChart].forEach((node) => {
    if (!node || !node.offsetParent) {
      return;
    }
    try {
      Plotly.Plots.resize(node);
    } catch (_err) {
      // Plotly may not have a plot yet.
    }
  });
}

function selectDetailTab(tabId) {
  const tabs = [...document.querySelectorAll(".detail-tabs [role='tab']")];
  if (!tabs.length) {
    return;
  }
  const selected = tabs.find((tab) => tab.id === tabId) || tabs[0];
  tabs.forEach((tab) => {
    const on = tab === selected;
    tab.setAttribute("aria-selected", on ? "true" : "false");
    tab.tabIndex = on ? 0 : -1;
    const panel = document.getElementById(tab.getAttribute("aria-controls"));
    if (panel) {
      panel.hidden = !on;
    }
  });
  if (selected.id === "tabRevisions") {
    track("cycle_view", { ticker: state.selectedSymbol || "" });
  }
  requestAnimationFrame(() => {
    requestAnimationFrame(resizeVisibleCharts);
  });
}

function initDetailTabs() {
  const tabs = [...document.querySelectorAll(".detail-tabs [role='tab']")];
  tabs.forEach((tab, index) => {
    tab.addEventListener("click", () => selectDetailTab(tab.id));
    tab.addEventListener("keydown", (event) => {
      let next = null;
      if (event.key === "ArrowRight") {
        next = tabs[(index + 1) % tabs.length];
      } else if (event.key === "ArrowLeft") {
        next = tabs[(index - 1 + tabs.length) % tabs.length];
      } else if (event.key === "Home") {
        next = tabs[0];
      } else if (event.key === "End") {
        next = tabs[tabs.length - 1];
      }
      if (!next) {
        return;
      }
      event.preventDefault();
      next.focus();
      selectDetailTab(next.id);
    });
  });
}

function initAlertFilters() {
  if (!dom.alertFilters) {
    return;
  }
  dom.alertFilters.addEventListener("click", (event) => {
    const btn = event.target.closest?.(".alert-filter");
    if (!btn) {
      return;
    }
    const severity = btn.getAttribute("data-severity") || "all";
    state.alertSeverityFilter = severity;
    [...dom.alertFilters.querySelectorAll(".alert-filter")].forEach((node) => {
      node.setAttribute("aria-pressed", node === btn ? "true" : "false");
    });
    track("alert_severity_filter", { severity });
    if (state.overview) {
      renderAlerts(state.overview);
    }
  });
}

function setLoadBanner(kind, message) {
  if (!dom.loadBanner) {
    return;
  }
  if (!kind) {
    dom.loadBanner.hidden = true;
    dom.loadBanner.className = "load-banner";
    dom.loadBanner.textContent = "";
    if (dom.mainContent) {
      dom.mainContent.removeAttribute("aria-busy");
    }
    return;
  }
  dom.loadBanner.hidden = false;
  dom.loadBanner.className = `load-banner is-${kind}`;
  dom.loadBanner.textContent = message;
  if (dom.mainContent) {
    dom.mainContent.setAttribute("aria-busy", kind === "loading" ? "true" : "false");
  }
  if (kind === "empty") {
    track("empty_state_shown", { surface: "dashboard" });
  }
  if (kind === "error") {
    track("api_error", { surface: "dashboard" });
  }
}

function createInsightCard({ label, helpKey, valueHtml, subHtml = "", tone = "", empty = false }) {
  const card = document.createElement("article");
  card.className = `summary-card insight-card${tone ? ` insight-${tone}` : ""}${empty ? " insight-empty" : ""}`;
  card.innerHTML = `<span class="label">${helpLabel(label, helpKey || label)}</span><span class="value">${valueHtml}</span>${
    subHtml ? `<span class="insight-sub">${subHtml}</span>` : ""
  }`;
  return card;
}

function cohortCountLabel(overview) {
  const groups = Array.isArray(overview.groups) ? overview.groups : [];
  if (groups.length) {
    return groups
      .map((group) => `${formatCount(group.count)} ${group.label || "group"}`)
      .join(" · ");
  }
  const summary = overview.summary || {};
  const parts = [];
  if (isPresentNumber(summary.active_count)) {
    parts.push(`${summary.active_count} live`);
  }
  if (isPresentNumber(summary.under_review_count)) {
    parts.push(`${summary.under_review_count} under review`);
  }
  if (isPresentNumber(summary.stale_tickers)) {
    parts.push(`${summary.stale_tickers} stale`);
  }
  return parts.length ? parts.join(" · ") : UNAVAILABLE;
}

function renderHero(overview) {
  const summary = overview.summary || {};
  const clock = overview.market_clock || {};
  setText(dom.heroTargetWeek, summary.target_week_end_date || UNAVAILABLE);
  setText(dom.heroAsOf, formatDateTime(overview.generated_at));
  const status = marketStatusLabel(clock);
  const time = formatDateTime(clock.market_time);
  setText(dom.heroMarketClock, status === UNAVAILABLE && time === UNAVAILABLE ? UNAVAILABLE : `${status} · ${time}`);
  setText(dom.heroCohorts, cohortCountLabel(overview));
}

function renderSummary(overview) {
  const summary = overview.summary || {};
  const previousWeek = summary.previous_week_rollup || {};
  const cards = [];

  const critical = summary.critical_alerts;
  const open = summary.open_alerts;
  const warning = summary.warning_alerts;
  if (!isPresentNumber(critical) && !isPresentNumber(open)) {
    cards.push({
      label: "Open / critical alerts",
      valueHtml: escapeHtml(UNAVAILABLE),
      subHtml: "Alert counts were not in this payload.",
      tone: "info",
      empty: true,
    });
  } else {
    const criticalCount = isPresentNumber(critical) ? critical : 0;
    const openCount = isPresentNumber(open) ? open : 0;
    cards.push({
      label: "Open / critical alerts",
      valueHtml: escapeHtml(`${criticalCount} critical`),
      subHtml: escapeHtml(
        `${openCount} open · ${isPresentNumber(warning) ? warning : UNAVAILABLE} warning`
      ),
      tone: criticalCount > 0 ? "critical" : openCount > 0 ? "warning" : "good",
    });
  }

  const resolved = previousWeek.resolved_count;
  if (!isPresentNumber(resolved)) {
    cards.push({
      label: "Prior-week accuracy",
      valueHtml: escapeHtml(UNAVAILABLE),
      subHtml: "Prior-week rollup is missing.",
      empty: true,
      tone: "info",
    });
  } else if (resolved === 0) {
    cards.push({
      label: "Prior-week accuracy",
      valueHtml: "No resolved weeks yet",
      subHtml: "Accuracy is shown after a target week completes.",
      empty: true,
      tone: "info",
    });
  } else {
    cards.push({
      label: "Prior-week accuracy",
      valueHtml: escapeHtml(formatPct(previousWeek.direction_accuracy_pct, 0)),
      subHtml: escapeHtml(`MAE ${formatNumber(previousWeek.mae)} · ${resolved} resolved`),
      tone: "good",
    });
  }

  const current = summary.current_tickers;
  const stale = summary.stale_tickers;
  if (!isPresentNumber(current) && !isPresentNumber(stale)) {
    cards.push({
      label: "Freshness",
      valueHtml: escapeHtml(UNAVAILABLE),
      subHtml: "Freshness counts were not in this payload.",
      empty: true,
      tone: "info",
    });
  } else {
    const staleCount = isPresentNumber(stale) ? stale : 0;
    cards.push({
      label: "Freshness",
      valueHtml: escapeHtml(`${isPresentNumber(current) ? current : UNAVAILABLE} current`),
      subHtml: escapeHtml(
        `${staleCount} stale · ${isPresentNumber(summary.visible_tickers) ? summary.visible_tickers : UNAVAILABLE} visible`
      ),
      tone: staleCount > 0 ? "warning" : "good",
    });
  }

  const review = summary.under_review_count;
  if (!isPresentNumber(review)) {
    cards.push({
      label: "Under review",
      valueHtml: escapeHtml(UNAVAILABLE),
      subHtml: "Quality-gate counts were not in this payload.",
      empty: true,
      tone: "info",
    });
  } else {
    cards.push({
      label: "Under review",
      valueHtml: escapeHtml(String(review)),
      subHtml: escapeHtml(
        `${isPresentNumber(summary.active_count) ? summary.active_count : UNAVAILABLE} live / on track`
      ),
      tone: review > 0 ? "warning" : "good",
    });
  }

  dom.summaryCards.innerHTML = "";
  cards.forEach((card) => {
    dom.summaryCards.append(createInsightCard(card));
  });
}

function severityIcon(severity) {
  if (severity === "critical") {
    return `<svg class="sev-icon" viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" focusable="false"><path fill="currentColor" d="M8 1 15 14H1L8 1zm0 4.2c.4 0 .7.3.7.7v3.2c0 .4-.3.7-.7.7s-.8-.3-.8-.7V5.9c0-.4.4-.7.8-.7zm0 6.2a.85.85 0 1 1 0 1.7.85.85 0 0 1 0-1.7z"/></svg>`;
  }
  if (severity === "warning") {
    return `<svg class="sev-icon" viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" focusable="false"><path fill="currentColor" d="M8 2.2 13.8 8 8 13.8 2.2 8 8 2.2zM8 5.1a.7.7 0 0 0-.7.7v2.6c0 .4.3.7.7.7s.7-.3.7-.7V5.8a.7.7 0 0 0-.7-.7zm0 5.2a.8.8 0 1 0 0 1.6.8.8 0 0 0 0-1.6z"/></svg>`;
  }
  return `<svg class="sev-icon" viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" focusable="false"><path fill="currentColor" d="M8 1.4a6.6 6.6 0 1 1 0 13.2A6.6 6.6 0 0 1 8 1.4zm0 2.4a.8.8 0 1 0 0 1.6.8.8 0 0 0 0-1.6zM7.2 7.2h1.6v4.6H7.2V7.2z"/></svg>`;
}

function severityBadge(severity) {
  const sev = severity || "info";
  const severityClass = alertSeverityClass[sev] || alertSeverityClass.info;
  return `<span class="severity-badge ${severityClass}">${severityIcon(sev)}<span class="severity-text">${escapeHtml(sev)}</span></span>`;
}

function renderAlerts(overview) {
  const alerts = overview.alerts || {};
  const items = Array.isArray(alerts.items) ? alerts.items : [];
  const sources = alerts.sources || {};
  const filter = state.alertSeverityFilter || "all";
  const visible = filter === "all" ? items : items.filter((item) => (item.severity || "info") === filter);

  if (dom.alertsSummary) {
    dom.alertsSummary.innerHTML = `
      <span class="alert-counter critical">${severityIcon("critical")} Critical: ${escapeHtml(formatCount(alerts.critical_count))}</span>
      <span class="alert-counter warning">${severityIcon("warning")} Warning: ${escapeHtml(formatCount(alerts.warning_count))}</span>
      <span class="alert-counter info">${severityIcon("info")} Info: ${escapeHtml(formatCount(alerts.info_count))}</span>
      <span class="alert-counter open">Open: ${escapeHtml(formatCount(alerts.open_count))}</span>
      <span class="alert-source">Automation: ${escapeHtml(sources.automation_state || UNAVAILABLE)}</span>
      <span class="alert-source">weekly file: ${escapeHtml(sources.weekly || UNAVAILABLE)}</span>
    `;
  }

  if (!items.length) {
    dom.alertsList.innerHTML = `<article class="alert-item severity-info"><div class="alert-head"><strong>No open failed-ticker alerts</strong>${severityBadge("info")}</div><p class="alert-empty">Automation and latest weekly file status are currently clear. This is a true zero, not a missing feed.</p></article>`;
    return;
  }

  if (!visible.length) {
    dom.alertsList.innerHTML = `<article class="alert-item severity-info"><div class="alert-head"><strong>No ${escapeHtml(filter)} alerts</strong>${severityBadge("info")}</div><p class="alert-empty">Nothing matches this severity filter. Choose All to see every open item.</p></article>`;
    return;
  }

  dom.alertsList.innerHTML = visible
    .map((item) => {
      const symbol = escapeHtml(item.symbol || "UNKNOWN");
      const severity = item.severity || "info";
      const severityClass = alertSeverityClass[severity] || alertSeverityClass.info;
      const messages = Array.isArray(item.messages) ? item.messages : [];
      const automation = item.automation || {};
      const bq = item.weekly || {};
      const canOpen = Boolean(item.symbol);
      return `
        <article class="alert-item ${severityClass}">
          <div class="alert-head">
            <strong>${symbol}</strong>
            ${severityBadge(severity)}
          </div>
          <ul class="alert-messages">
            ${messages.map((msg) => `<li>${escapeHtml(msg)}</li>`).join("")}
          </ul>
          <div class="alert-meta">
            <span>${helpLabel("Automation", "Alert Source")} <b>${escapeHtml(automation.last_status || UNAVAILABLE)}</b></span>
            <span>${helpLabel("BQ Status", "Alert Source")} <b>${escapeHtml(bq.status || UNAVAILABLE)}</b></span>
            <span>${helpLabel("Run Date", "Target Week-End")} <b>${escapeHtml(bq.run_date || UNAVAILABLE)}</b></span>
            <span>${helpLabel("Target Week-End", "Target Week-End")} <b>${escapeHtml(bq.target_week_end_date || UNAVAILABLE)}</b></span>
          </div>
          ${
            canOpen
              ? `<button type="button" class="alert-open" data-symbol="${escapeHtml(item.symbol)}" data-severity="${escapeHtml(severity)}">Open ${symbol}</button>`
              : ""
          }
        </article>
      `;
    })
    .join("");

  [...dom.alertsList.querySelectorAll(".alert-open")].forEach((node) => {
    node.addEventListener("click", () => {
      const symbol = node.getAttribute("data-symbol");
      if (!symbol) {
        return;
      }
      track("alert_open", { ticker: symbol, severity: node.getAttribute("data-severity") || "" });
      selectTicker(symbol, { userInitiated: true });
    });
  });
}

function sparkline(points) {
  if (!Array.isArray(points) || points.length < 2) {
    return `<span class="sparkline-empty">No curve yet</span>`;
  }

  const closes = points.map((point) =>
    typeof point.display_close === "number" ? point.display_close : point.predicted_close
  );
  const min = Math.min(...closes);
  const max = Math.max(...closes);
  const delta = max - min || 1;
  const width = 184;
  const height = 34;
  const step = width / (closes.length - 1);
  const path = closes
    .map((close, idx) => {
      const x = idx * step;
      const y = height - ((close - min) / delta) * height;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");

  return `<svg class="sparkline" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" role="img" aria-label="Projected close path">
    <polyline points="${path}"></polyline>
  </svg>`;
}

function cardMeta(label, value) {
  return `<div><span>${escapeHtml(label)}</span><b>${escapeHtml(value)}</b></div>`;
}

function buildAlertIndex(overview) {
  const index = new Map();
  const alerts = overview?.alerts?.items;
  if (!Array.isArray(alerts)) {
    return index;
  }
  alerts.forEach((item) => {
    if (item && typeof item.symbol === "string") {
      index.set(item.symbol.toUpperCase(), item);
    }
  });
  return index;
}

function bindTickerActivation(node, symbol) {
  const activate = () => selectTicker(symbol, { userInitiated: true });
  node.addEventListener("click", activate);
  node.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      activate();
    }
  });
}

function renderTickerCards(overview) {
  const rows = overview.tickers || [];
  const alertIndex = buildAlertIndex(overview);
  dom.tickerGrid.innerHTML = "";

  if (!Array.isArray(rows) || !rows.length) {
    dom.tickerGrid.innerHTML = `<p class="empty-state">Watchlist is empty. No ticker rows were returned for this payload.</p>`;
    track("empty_state_shown", { surface: "watchlist" });
    return;
  }

  const renderCard = (row) => {
    const card = document.createElement("article");
    const isActive = state.selectedSymbol === row.symbol;
    const freshness = row.business_health?.forecast_freshness;
    card.className = `ticker-card${isActive ? " active" : ""}${freshness === "stale" ? " ticker-card-stale" : ""}`;
    card.tabIndex = 0;
    card.setAttribute("role", "button");
    card.setAttribute("aria-pressed", isActive ? "true" : "false");

    const status = row.status || "unknown";
    const statusPillClass = statusClass[status] || statusClass.unknown;
    const statusText = status.replace("_", " ");
    const projectedMove = isPresentNumber(row.week_return_pct) ? formatPct(row.week_return_pct) : UNAVAILABLE;
    const projectedClose = isPresentNumber(row.week_end_predicted_close)
      ? formatNumber(row.week_end_predicted_close)
      : UNAVAILABLE;
    const revisions = Array.isArray(row.revisions) ? row.revisions.length : null;
    const businessHealth = row.business_health || {};
    const healthSeverityClass = businessSeverityClass[businessHealth.severity] || "";
    const warningBlock =
      businessHealth.state && businessHealth.state !== "on_track"
        ? `<div class="ticker-card-warning ${healthSeverityClass}"><strong>${escapeHtml(
            row.business_warning_label || "Attention needed"
          )}</strong><span>${escapeHtml(row.business_warning_message || "")}</span></div>`
        : "";
    const alertItem = alertIndex.get(String(row.symbol || "").toUpperCase());
    const alertBadge = alertItem ? severityBadge(alertItem.severity) : "";
    const staleBadge =
      freshness === "stale" ? `<span class="source-chip source-chip-stale">Stale</span>` : "";
    const missingForecast =
      businessHealth.state === "missing_forecast"
        ? `<span class="source-chip source-chip-muted">Forecast missing</span>`
        : "";

    card.setAttribute(
      "aria-label",
      `${row.symbol}, ${statusText}, projected move ${projectedMove}`
    );

    card.innerHTML = `
      <div class="ticker-top">
        <strong>${escapeHtml(row.symbol)}</strong>
        <span class="status-pill ${statusPillClass}">${escapeHtml(statusText)}</span>
      </div>
      ${sparkline(row.forecast_points)}
      <div class="ticker-source-row">
        <span class="cohort-chip">${escapeHtml(row.cohort_label || "Unknown cohort")}</span>
        ${staleBadge}
        ${missingForecast}
        ${alertBadge}
      </div>
      <div class="ticker-meta ticker-meta-compact">
        ${cardMeta("Projected Move", projectedMove)}
        ${cardMeta("Target Close", projectedClose)}
        ${cardMeta("revisions", revisions === null ? "No ledger yet" : String(revisions))}
      </div>
      ${warningBlock}
    `;

    bindTickerActivation(card, row.symbol);
    return card;
  };

  const groups = Array.isArray(overview.groups) ? overview.groups : [];
  if (groups.length) {
    dom.tickerGrid.className = "ticker-board";
    const rowIndex = new Map(rows.map((row) => [String(row.symbol || "").toUpperCase(), row]));
    groups.forEach((group) => {
      const symbols = Array.isArray(group.symbols) ? group.symbols : [];
      const groupRows = symbols
        .map((symbol) => rowIndex.get(String(symbol || "").toUpperCase()))
        .filter((row) => row);
      if (!groupRows.length) {
        return;
      }
      const section = document.createElement("section");
      section.className = "ticker-group";
      section.innerHTML = `
        <div class="ticker-group-head">
          <div>
            <h3>${escapeHtml(group.label || "Tickers")}</h3>
            <p>${escapeHtml(group.description || "")}</p>
          </div>
          <span class="ticker-group-count">${escapeHtml(formatCount(group.count ?? groupRows.length))}</span>
        </div>
      `;
      const grid = document.createElement("div");
      grid.className = "ticker-grid ticker-group-grid";
      groupRows.forEach((row) => grid.append(renderCard(row)));
      section.append(grid);
      dom.tickerGrid.append(section);
    });
    return;
  }

  dom.tickerGrid.className = "ticker-grid";
  rows.forEach((row) => {
    dom.tickerGrid.append(renderCard(row));
  });
}

function snapshotItem(label, value, helpKey = label) {
  return `<div><span>${helpLabel(label, helpKey)}</span><b>${escapeHtml(value)}</b></div>`;
}

function renderSnapshot(detail) {
  const evaluationCount = detail.evaluation_count ?? detail.evaluation?.metrics?.count;
  const modelMae = formatNumber(detail.model_mae);
  const modelRmse = formatNumber(detail.model_rmse);
  const previousWeek = detail.previous_week_comparison || {};
  const history = detail.history_metrics || {};
  const alert = detail.alert || {};
  const health = detail.business_health || {};
  const clock = detail.market_clock || {};
  const initialForecast = detail.initial_forecast || {};
  const latestForecast = detail.latest_forecast || {};
  const resolvedActual = detail.resolved_actual || {};
  const kpis = detail.kpis || {};
  const firstCallKpi = kpis.first_call_week_ahead || {};
  const rollingKpi = kpis.rolling_revision_accuracy || {};
  const previousDirection =
    typeof previousWeek.direction_match === "boolean"
      ? previousWeek.direction_match
        ? "Matched"
        : "Mismatched"
      : UNAVAILABLE;
  const historicalCoverage = `${formatPct(history.coverage_within_1pct)} / ${formatPct(
    history.coverage_within_2pct
  )} / ${formatPct(history.coverage_within_5pct)}`;
  const historicalWindow = `${history.window_start || UNAVAILABLE} -> ${history.window_end || UNAVAILABLE}`;
  const historyDirection = formatPct(history.direction_accuracy_pct);
  const alertMessages = Array.isArray(alert.messages) ? alert.messages.length : 0;
  const hasAutomation = alert?.automation?.last_status ? "automation_state" : "";
  const hasBq = alert?.weekly?.status ? "weekly" : "";
  const alertSource = hasAutomation && hasBq ? "automation + weekly" : hasAutomation || hasBq || "none";
  const riskFlags = Array.isArray(detail.risk_flags) ? detail.risk_flags : [];
  const revisionCount = Array.isArray(detail.revisions) ? detail.revisions.length : null;

  if (!dom.snapshotGrid) {
    return;
  }

  dom.snapshotGrid.innerHTML = [
    snapshotItem("Ticker", detail.symbol),
    snapshotItem("Status", (detail.status || "unknown").replace("_", " ")),
    snapshotItem("Forecast Health", health.label || UNAVAILABLE, "Forecast Health"),
    snapshotItem("Coverage", detail.cohort_label || UNAVAILABLE),
    snapshotItem("Current Actual Close", formatNumber(detail.last_close), "Current Actual Close"),
    snapshotItem("Week-End Target", detail.target_week_end_date || UNAVAILABLE),
    snapshotItem("Selected Forecast Date", detail.final_forecast_date || UNAVAILABLE),
    snapshotItem("Market Status", marketStatusLabel(clock), "Market Status"),
    snapshotItem("Market Time", formatDateTime(clock.market_time), "Market Time"),
    snapshotItem("Latest Session", clock.latest_market_session_date || UNAVAILABLE, "Latest Session"),
    snapshotItem("Next Session", clock.next_market_session_date || UNAVAILABLE, "Next Session"),
    snapshotItem("Week Closure", weekClosureSummary(clock), "Week Closure"),
    snapshotItem("Calendar Source", clock.calendar_source || UNAVAILABLE, "Calendar Source"),
    snapshotItem("Target Close", formatNumber(detail.week_end_predicted_close), "Target Close"),
    snapshotItem("Week Return", formatPct(detail.week_return_pct)),
    snapshotItem("Forecast Band", health.forecast_risk_label || "Normal forecast band", "Forecast Health"),
    snapshotItem("Typical Gap", formatGapPct(detail.typical_gap_pct), "Typical Gap"),
    snapshotItem("Latest Gap", formatGapPct(detail.latest_gap_pct), "Latest Gap"),
    snapshotItem("Direction Hit", formatPct(detail.direction_hit_rate, 0), "Direction Hit"),
    snapshotItem("Risk Flags", riskFlags.length ? riskFlags.map((flag) => flag.label || "Risk flag").join(", ") : "None"),
    snapshotItem("Cycle Status", detail.cycle_status || UNAVAILABLE),
    snapshotItem("Forecast Source", detail.primary_forecast_source || UNAVAILABLE),
    snapshotItem("Evaluation Source", detail.primary_evaluation_source || UNAVAILABLE),
    snapshotItem("initial_forecast", formatNumber(initialForecast.predicted_target_close), "initial_forecast"),
    snapshotItem("latest_forecast", formatNumber(latestForecast.predicted_target_close), "latest_forecast"),
    snapshotItem(
      "resolved_actual",
      isPresentNumber(resolvedActual.actual_target_close)
        ? formatNumber(resolvedActual.actual_target_close)
        : "Not resolved yet",
      "resolved_actual"
    ),
    snapshotItem("revisions", revisionCount === null ? "No ledger yet" : String(revisionCount), "revisions"),
    snapshotItem("First-Call KPI", formatNumber(firstCallKpi.absolute_error)),
    snapshotItem("Rolling KPI", formatNumber(rollingKpi.absolute_error)),
    snapshotItem("Live MAE", formatNumber(detail.mae)),
    snapshotItem("Live RMSE", formatNumber(detail.rmse)),
    snapshotItem("MAPE", formatPct(detail.mape)),
    snapshotItem("Model MAE", modelMae),
    snapshotItem("Model RMSE", modelRmse),
    snapshotItem("Eval Samples", isPresentNumber(evaluationCount) ? String(evaluationCount) : UNAVAILABLE),
    snapshotItem("Projection Selection", detail.projection_selection || UNAVAILABLE),
    snapshotItem("Alert Severity", alert.severity || "none"),
    snapshotItem("Alert Messages", String(alertMessages)),
    snapshotItem("Alert Source", alertSource),
    snapshotItem("Prior Outcome", (previousWeek.status || UNAVAILABLE).replace(/_/g, " ")),
    snapshotItem("Prior Target Date", previousWeek.target_week_end_date || UNAVAILABLE),
    snapshotItem("Prior Predicted Close", formatNumber(previousWeek.predicted_close)),
    snapshotItem("Prior Actual Close", formatNumber(previousWeek.actual_close)),
    snapshotItem("Prior Abs Error", formatNumber(previousWeek.absolute_error)),
    snapshotItem("Prior Error %", formatPct(previousWeek.error_pct)),
    snapshotItem("Prior Direction", previousDirection),
    snapshotItem("History Samples", isPresentNumber(history.sample_count) ? String(history.sample_count) : UNAVAILABLE),
    snapshotItem("History Forecast Dates", isPresentNumber(history.forecast_date_count) ? String(history.forecast_date_count) : UNAVAILABLE),
    snapshotItem("History Window", historicalWindow),
    snapshotItem("History MAE", formatNumber(history.mae)),
    snapshotItem("History RMSE", formatNumber(history.rmse)),
    snapshotItem("History MAPE", formatPct(history.mape)),
    snapshotItem("History Bias", formatNumber(history.bias)),
    snapshotItem("History Bias %", formatPct(history.percent_bias)),
    snapshotItem("History Abs Error P50", formatNumber(history.abs_error_p50)),
    snapshotItem("History Abs Error P90", formatNumber(history.abs_error_p90)),
    snapshotItem("History Abs Error Max", formatNumber(history.abs_error_max)),
    snapshotItem("History Rolling MAE", formatNumber(history.latest_mae), "History Rolling MAE"),
    snapshotItem("History Direction Hit", historyDirection, "History Direction Hit"),
    snapshotItem("History <=1/2/5%", historicalCoverage),
    snapshotItem("History Cycles", isPresentNumber(history.source_file_count) ? String(history.source_file_count) : UNAVAILABLE, "History Cycles"),
  ].join("");
}

function closeFocusTile(label, value, helpKey = label, accentClass = "") {
  return `
    <article class="close-focus-tile ${accentClass}">
      <span>${helpLabel(label, helpKey)}</span>
      <strong>${escapeHtml(value)}</strong>
    </article>
  `;
}

function renderCloseFocus(detail) {
  const initialForecast = detail.initial_forecast || {};
  const latestForecast = detail.latest_forecast || {};
  const resolvedActual = detail.resolved_actual || {};
  const revisions = Array.isArray(detail.revisions) ? detail.revisions : null;

  const currentInitial = isPresentNumber(initialForecast.predicted_target_close)
    ? formatNumber(initialForecast.predicted_target_close)
    : UNAVAILABLE;
  const currentLatest = isPresentNumber(latestForecast.predicted_target_close)
    ? formatNumber(latestForecast.predicted_target_close)
    : UNAVAILABLE;
  const resolvedRaw = isPresentNumber(resolvedActual.actual_target_close)
    ? resolvedActual.actual_target_close
    : null;
  const revisionLabel = revisions === null ? "No ledger yet" : String(revisions.length);

  if (resolvedRaw !== null) {
    const rollingGapRaw = isPresentNumber(latestForecast.predicted_target_close)
      ? latestForecast.predicted_target_close - resolvedRaw
      : null;
    dom.closeFocus.innerHTML = [
      closeFocusTile("initial_forecast", currentInitial, "initial_forecast"),
      closeFocusTile("latest_forecast", currentLatest, "latest_forecast"),
      closeFocusTile("resolved_actual", formatNumber(resolvedRaw), "resolved_actual", "close-focus-good"),
      closeFocusTile("revisions", revisionLabel, "revisions"),
      closeFocusTile("Rolling Gap", formatNumber(rollingGapRaw), "Rolling Gap"),
    ].join("");
    return;
  }

  const targetClose = isPresentNumber(detail.week_end_predicted_close)
    ? formatNumber(detail.week_end_predicted_close)
    : UNAVAILABLE;

  dom.closeFocus.innerHTML = [
    closeFocusTile("initial_forecast", currentInitial, "initial_forecast"),
    closeFocusTile("latest_forecast", currentLatest, "latest_forecast"),
    closeFocusTile("resolved_actual", "Not resolved yet", "resolved_actual"),
    closeFocusTile("Target Close", targetClose, "Target Close"),
    closeFocusTile("revisions", revisionLabel, "revisions"),
  ].join("");
}

function renderWeekPath(detail) {
  const weekly = detail.weekly || {};
  let rows = Array.isArray(weekly.daily) ? weekly.daily : [];
  const perDate = Array.isArray(detail.evaluation?.per_date) ? detail.evaluation.per_date : [];
  const actualByDate = new Map();
  const referenceActualClose = typeof detail.last_close === "number" ? detail.last_close : null;
  perDate.forEach((row) => {
    if (!row || typeof row.forecast_date !== "string") {
      return;
    }
    actualByDate.set(row.forecast_date, typeof row.actual_close === "number" ? row.actual_close : null);
  });
  if (!rows.length && Array.isArray(detail.forecast)) {
    rows = detail.forecast.map((point) => {
      const close =
        typeof point.display_close === "number"
          ? point.display_close
          : typeof point.predicted_close === "number"
          ? point.predicted_close
          : null;
      const actualClose = actualByDate.get(point.date) ?? referenceActualClose ?? null;
      const gap =
        typeof close === "number" && typeof actualClose === "number" ? close - actualClose : null;
      return {
        date: point.date,
        predicted_close: close,
        actual_close: actualClose,
        gap,
        is_target_week_end: point.date === detail.target_week_end_date,
      };
    });
  } else {
    rows = rows.map((row) => {
      const actualClose = actualByDate.get(row.date) ?? referenceActualClose ?? null;
      const predictedClose =
        typeof row.display_close === "number"
          ? row.display_close
          : typeof row.predicted_close === "number"
          ? row.predicted_close
          : null;
      const gap =
        typeof predictedClose === "number" && typeof actualClose === "number"
          ? predictedClose - actualClose
          : null;
      return {
        ...row,
        actual_close: actualClose,
        gap,
      };
    });
  }

  const targetDate = detail.target_week_end_date || UNAVAILABLE;
  const selectedDate = detail.final_forecast_date || UNAVAILABLE;
  const selection = detail.projection_selection || UNAVAILABLE;
  const closure = weekClosureSummary(detail.market_clock || {});
  if (dom.weekPathMeta) {
    dom.weekPathMeta.textContent = `Target market close: ${targetDate} | Selected: ${selectedDate} | Rule: ${selection} | Week closure: ${closure} | Showing the target-anchored display path against the latest actual close, with resolved rows automatically swapping in realised closes.`;
  }

  if (!dom.weekPathTable) {
    return;
  }
  if (!rows.length) {
    dom.weekPathTable.innerHTML = `<tr><td colspan="4" class="sparkline-empty">No week path available.</td></tr>`;
    return;
  }
  dom.weekPathTable.innerHTML = rows
    .map((row) => {
      const cls = row.is_target_week_end ? "target-row" : "";
      return `
        <tr class="${cls}">
          <td>${escapeHtml(row.date || UNAVAILABLE)}</td>
          <td>${escapeHtml(row.actual_close === null ? "Pending" : formatNumber(row.actual_close))}</td>
          <td>${escapeHtml(formatNumber(row.predicted_close))}</td>
          <td>${escapeHtml(row.gap === null ? "Pending" : formatNumber(row.gap))}</td>
        </tr>
      `;
    })
    .join("");
}

function renderCycleTimeline(detail) {
  const revisions = Array.isArray(detail.revisions) ? detail.revisions : [];
  const resolvedActual = detail.resolved_actual || {};
  const resolvedClose = isPresentNumber(resolvedActual.actual_target_close)
    ? formatNumber(resolvedActual.actual_target_close)
    : "Not resolved yet";
  if (dom.cycleMeta) {
    dom.cycleMeta.textContent = `Cycle: ${detail.cycle_status || UNAVAILABLE} | revisions: ${revisions.length} | resolved_actual: ${resolvedClose} | initial_forecast is the first frozen call.`;
  }

  if (!dom.cycleTable) {
    return;
  }
  if (!revisions.length) {
    dom.cycleTable.innerHTML = `<tr><td colspan="6" class="sparkline-empty">No forecast cycle revisions are available yet. This is an empty ledger, not a zero forecast.</td></tr>`;
    return;
  }

  dom.cycleTable.innerHTML = revisions
    .map((revision) => {
      const kind = revision.origin_kind || "revision";
      const kindLabel = kind === "initial_weekly" ? "initial_forecast" : kind;
      const target = revision.target_week_end_date || detail.target_week_end_date || UNAVAILABLE;
      return `
        <tr class="${kind === "initial_weekly" ? "target-row" : ""}">
          <td>${escapeHtml(`${revision.revision_index ?? 0} / ${kindLabel}`)}</td>
          <td>${escapeHtml(revision.last_observation_date || UNAVAILABLE)}</td>
          <td>${escapeHtml(target)}</td>
          <td>${escapeHtml(formatNumber(revision.predicted_target_close))}</td>
          <td>${escapeHtml(formatPct(revision.predicted_target_return_pct))}</td>
          <td>${escapeHtml(revision.projection_selection || UNAVAILABLE)}</td>
        </tr>
      `;
    })
    .join("");
}

function renderHistoryTable(detail) {
  const rows = resolvedComparisonRows(detail);
  if (!rows.length) {
    if (dom.historyMeta) {
      dom.historyMeta.textContent = "Resolved target-close history is not available yet.";
    }
    if (dom.historyTable) {
      dom.historyTable.innerHTML = `<tr><td colspan="7" class="sparkline-empty">No resolved weekly history is available. Pending cycles are not shown as zeros.</td></tr>`;
    }
    return;
  }

  const windowStart = rows[0]?.forecast_date || UNAVAILABLE;
  const windowEnd = rows[rows.length - 1]?.forecast_date || UNAVAILABLE;
  if (dom.historyMeta) {
    dom.historyMeta.textContent = `Resolved weeks: ${rows.length} | Window: ${windowStart} -> ${windowEnd} | Showing frozen initial_forecast, latest_forecast, and resolved_actual for each completed target week.`;
  }

  dom.historyTable.innerHTML = [...rows]
    .reverse()
    .map((row) => {
      const latestClose =
        typeof row.latest_predicted_close === "number" ? row.latest_predicted_close : row.predicted_close;
      const firstError =
        typeof row.first_call_absolute_error === "number"
          ? row.first_call_absolute_error
          : typeof row.predicted_close === "number" && typeof row.actual_close === "number"
          ? Math.abs(row.predicted_close - row.actual_close)
          : null;
      const latestError =
        typeof row.latest_absolute_error === "number"
          ? row.latest_absolute_error
          : typeof latestClose === "number" && typeof row.actual_close === "number"
          ? Math.abs(latestClose - row.actual_close)
          : null;
      const revisionCount = isPresentNumber(row.revision_count) ? String(row.revision_count) : UNAVAILABLE;
      return `
        <tr>
          <td>${escapeHtml(row.forecast_date || UNAVAILABLE)}</td>
          <td>${escapeHtml(formatNumber(row.predicted_close))}</td>
          <td>${escapeHtml(formatNumber(latestClose))}</td>
          <td>${escapeHtml(formatNumber(row.actual_close))}</td>
          <td>${escapeHtml(formatNumber(firstError))}</td>
          <td>${escapeHtml(formatNumber(latestError))}</td>
          <td>${escapeHtml(revisionCount)}</td>
        </tr>
      `;
    })
    .join("");
}

function emptyChart(target, message) {
  if (!target) {
    return;
  }
  target.innerHTML = `<p class="sparkline-empty">${escapeHtml(message)}</p>`;
}

function renderForecastChart(detail) {
  const weeklyDaily = Array.isArray(detail.weekly?.daily) ? detail.weekly.daily : [];
  const points = weeklyDaily.length
    ? weeklyDaily
        .map((point, idx) => ({
          date: point.date || point.forecast_date,
          predicted_close:
            typeof point.display_close === "number"
              ? point.display_close
              : typeof point.predicted_close === "number"
              ? point.predicted_close
              : null,
          horizon: idx + 1,
        }))
        .filter((point) => typeof point.date === "string" && typeof point.predicted_close === "number")
    : detail.forecast || [];
  if (!points.length || !window.Plotly) {
    emptyChart(dom.forecastChart, "Forecast points are unavailable.");
    return;
  }

  const dates = points.map((point) => point.date);
  const closes = points.map((point) =>
    typeof point.display_close === "number" ? point.display_close : point.predicted_close
  );
  const baseline = typeof detail.last_close === "number" ? detail.last_close : null;

  const traces = [
    {
      x: dates,
      y: closes,
      mode: "lines+markers",
      name: "latest_forecast path",
      line: { color: "#2ad5c1", width: 3 },
      marker: { color: "#f3c969", size: 7 },
      fill: "tozeroy",
      fillcolor: "rgba(42, 213, 193, 0.12)",
    },
  ];

  const shapes = [];
  if (baseline !== null) {
    shapes.push({
      type: "line",
      x0: dates[0],
      x1: dates[dates.length - 1],
      y0: baseline,
      y1: baseline,
      line: { color: "rgba(243, 201, 105, 0.8)", dash: "dash", width: 1.5 },
    });
  }
  if (detail.target_week_end_date && dates.includes(detail.target_week_end_date)) {
    shapes.push({
      type: "line",
      x0: detail.target_week_end_date,
      x1: detail.target_week_end_date,
      y0: Math.min(...closes),
      y1: Math.max(...closes),
      line: { color: "rgba(125, 227, 158, 0.9)", dash: "dot", width: 1.8 },
    });
  }

  Plotly.react(
    dom.forecastChart,
    traces,
    {
      margin: { l: 40, r: 16, t: 10, b: 42 },
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      font: { family: "Space Grotesk, sans-serif", color: "#edf7ff" },
      xaxis: { gridcolor: "rgba(136,200,217,0.18)" },
      yaxis: { gridcolor: "rgba(136,200,217,0.18)" },
      shapes,
      showlegend: false,
    },
    { displayModeBar: false, responsive: true }
  );
}

function renderErrorChart(detail) {
  const rows = resolvedComparisonRows(detail);
  if (!rows.length || !window.Plotly) {
    emptyChart(dom.errorChart, "Resolved predicted-vs-actual close points are unavailable.");
    return;
  }

  const dates = rows.map((row) => row.forecast_date);
  const predicted = rows.map((row) => row.predicted_close);
  const latestPredicted = rows.map((row) =>
    typeof row.latest_predicted_close === "number" ? row.latest_predicted_close : row.predicted_close
  );
  const actual = rows.map((row) => row.actual_close);
  const showLatestTrace = rows.some(
    (row) =>
      typeof row.latest_predicted_close === "number" &&
      typeof row.predicted_close === "number" &&
      row.latest_predicted_close !== row.predicted_close
  );

  Plotly.react(
    dom.errorChart,
    [
      {
        x: dates,
        y: predicted,
        mode: "lines+markers",
        name: "initial_forecast",
        line: { color: "#f3c969", width: 3 },
        marker: { color: "#f3c969", size: 7 },
      },
      ...(showLatestTrace
        ? [
            {
              x: dates,
              y: latestPredicted,
              mode: "lines+markers",
              name: "latest_forecast",
              line: { color: "#2ad5c1", width: 3 },
              marker: { color: "#2ad5c1", size: 7 },
            },
          ]
        : []),
      {
        x: dates,
        y: actual,
        mode: "lines+markers",
        name: "resolved_actual",
        line: { color: "#7de39e", width: 3 },
        marker: { color: "#7de39e", size: 7 },
      },
    ],
    {
      margin: { l: 40, r: 16, t: 10, b: 42 },
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      font: { family: "Space Grotesk, sans-serif", color: "#edf7ff" },
      xaxis: { gridcolor: "rgba(136,200,217,0.18)" },
      yaxis: { gridcolor: "rgba(136,200,217,0.18)" },
      showlegend: true,
      legend: {
        orientation: "h",
        x: 0,
        y: 1.14,
      },
    },
    { displayModeBar: false, responsive: true }
  );
}

function renderDetail(detail) {
  const previousSymbol = state.selectedSymbol;
  state.selectedSymbol = detail.symbol;
  setText(dom.detailTitle, `${detail.symbol} Detail`);
  const resolvedActual = detail.resolved_actual || {};
  let outcomeSuffix = "resolved_actual pending";
  if (isPresentNumber(resolvedActual.actual_target_close)) {
    outcomeSuffix = `resolved_actual ${formatNumber(resolvedActual.actual_target_close)}`;
  }
  setText(
    dom.detailSubtitle,
    `Observation ${detail.last_observation_date || UNAVAILABLE} | target close ${
      detail.target_week_end_date || UNAVAILABLE
    } | ${outcomeSuffix}`
  );

  const status = detail.status || "unknown";
  if (dom.detailStatus) {
    dom.detailStatus.className = `status-pill ${statusClass[status] || statusClass.unknown}`;
    dom.detailStatus.textContent = status.replace("_", " ");
  }

  const warning = businessHealthWarning(detail);
  if (dom.detailNotice) {
    if (warning) {
      dom.detailNotice.hidden = false;
      dom.detailNotice.className = `detail-notice ${warning.severity}`;
      dom.detailNotice.innerHTML = `<strong>${escapeHtml(warning.label)}</strong><span>${escapeHtml(
        warning.message
      )}</span>`;
    } else {
      dom.detailNotice.hidden = true;
      dom.detailNotice.className = "detail-notice";
      dom.detailNotice.textContent = "";
    }
  }

  if (previousSymbol !== detail.symbol) {
    selectDetailTab("tabOverview");
  }

  renderCloseFocus(detail);
  renderSnapshot(detail);
  renderWeekPath(detail);
  renderCycleTimeline(detail);
  renderHistoryTable(detail);
  renderForecastChart(detail);
  renderErrorChart(detail);
  if (state.overview) {
    renderTickerCards(state.overview);
  }

  if (state.lastTrackedSymbol !== detail.symbol) {
    state.lastTrackedSymbol = detail.symbol;
    const initialForecast = detail.initial_forecast || {};
    const latestForecast = detail.latest_forecast || {};
    const resolved = detail.resolved_actual || {};
    track("ticker_detail_open", {
      ticker: detail.symbol,
      forecast_cycle_id: detail.forecast_cycle_id || detail.cycle?.forecast_cycle_id || "",
      has_initial: isPresentNumber(initialForecast.predicted_target_close),
      has_latest: isPresentNumber(latestForecast.predicted_target_close),
      has_actual: isPresentNumber(resolved.actual_target_close),
    });
  }

  requestAnimationFrame(resizeVisibleCharts);
}

async function apiGet(path) {
  const response = await fetch(path, { credentials: "same-origin" });
  if (response.status === 401) {
    window.location.href = "/login";
    return null;
  }
  if (!response.ok) {
    throw new Error(`${path} failed with HTTP ${response.status}`);
  }
  return response.json();
}

async function loadUser() {
  const payload = await apiGet("/api/me");
  if (!payload) {
    return;
  }
  state.user = payload;
  const name = payload.name || payload.email || "Authenticated user";
  setText(dom.userName, name);
  setText(dom.userRole, roleLabel(payload.role));
}

async function selectTicker(symbol, { userInitiated = false } = {}) {
  try {
    const detail = await apiGet(`/api/ticker/${encodeURIComponent(symbol)}`);
    if (!detail) {
      return;
    }
    renderDetail(detail);
    if (userInitiated && dom.tickerDetail) {
      dom.tickerDetail.scrollIntoView({
        block: "start",
        behavior: prefersReducedMotion() ? "auto" : "smooth",
      });
    }
  } catch (err) {
    console.error(err);
    setLoadBanner("error", `Unable to load ${symbol} detail. Refresh to retry.`);
  }
}

async function refresh() {
  if (dom.refreshButton) {
    dom.refreshButton.disabled = true;
  }
  setLoadBanner("loading", "Loading portfolio…");
  try {
    const overview = await apiGet("/api/overview");
    if (!overview) {
      return;
    }
    state.overview = overview;
    renderHero(overview);
    renderSummary(overview);
    renderAlerts(overview);

    const tickers = Array.isArray(overview.tickers) ? overview.tickers : [];
    if (!tickers.length) {
      setLoadBanner("empty", "Overview loaded, but the watchlist has no ticker rows.");
    } else {
      setLoadBanner(null);
    }

    if (!state.selectedSymbol && tickers.length) {
      state.selectedSymbol = tickers[0].symbol;
    }
    renderTickerCards(overview);

    track("dashboard_view", {
      cohort: cohortCountLabel(overview),
      alert_count: overview.alerts?.open_count ?? null,
    });

    if (state.selectedSymbol) {
      await selectTicker(state.selectedSymbol);
    }
  } catch (err) {
    console.error(err);
    setLoadBanner("error", "Unable to load dashboard data. Refresh to retry.");
    setText(dom.heroTargetWeek, UNAVAILABLE);
    setText(dom.heroAsOf, UNAVAILABLE);
    setText(dom.heroMarketClock, UNAVAILABLE);
    setText(dom.heroCohorts, UNAVAILABLE);
    if (dom.summaryCards) {
      dom.summaryCards.innerHTML = "";
    }
    if (dom.alertsList) {
      dom.alertsList.innerHTML = `<article class="alert-item severity-critical"><div class="alert-head"><strong>Dashboard failed to load</strong>${severityBadge("critical")}</div><p class="alert-empty">Overview request failed. Counts are not shown as zeros.</p></article>`;
    }
    if (dom.tickerGrid) {
      dom.tickerGrid.innerHTML = `<p class="empty-state">Watchlist is unavailable until overview loads.</p>`;
    }
    setText(dom.detailSubtitle, "Unable to load dashboard data.");
  } finally {
    if (dom.refreshButton) {
      dom.refreshButton.disabled = false;
    }
  }
}

initHelpTooltips();
initDetailTabs();
initAlertFilters();

if (dom.logoutLink) {
  dom.logoutLink.addEventListener("click", (event) => {
    event.preventDefault();
    window.location.href = "/auth/logout";
  });
}

if (dom.refreshButton) {
  dom.refreshButton.addEventListener("click", () => {
    refresh().catch((err) => {
      console.error(err);
    });
  });
}

window.addEventListener("resize", () => {
  requestAnimationFrame(resizeVisibleCharts);
});

Promise.resolve()
  .then(loadUser)
  .then(refresh)
  .catch((err) => {
    console.error(err);
    setText(dom.detailSubtitle, "Unable to load dashboard data.");
    setLoadBanner("error", "Unable to load dashboard data. Refresh to retry.");
  });
