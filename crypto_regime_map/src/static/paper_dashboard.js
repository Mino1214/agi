const $ = (id) => document.getElementById(id);

const STORAGE = {
  mode: "paperDashboard.mode",
  symbol: "paperDashboard.symbol",
  timeframe: "paperDashboard.timeframe",
  events: "paperDashboard.showEvents",
};

const state = {
  payload: null,
  health: null,
  flow: null,
  repairing: false,
  healthEvents: [],
  activeTab: "orders",
  signalView: "top",
  mode: localStorage.getItem(STORAGE.mode) || "simple",
  busy: false,
  loadingTimer: null,
  chart: {
    instance: null,
    candleSeries: null,
    volumeSeries: null,
    emaSeries: {},
    priceLines: [],
    payload: null,
    symbol: localStorage.getItem(STORAGE.symbol) || "",
    timeframe: localStorage.getItem(STORAGE.timeframe) || "1H",
    showEvents: localStorage.getItem(STORAGE.events) !== "false",
    logScale: false,
    resizeBound: false,
    resizeObserver: null,
    loadSeq: 0,
  },
};

const statusLabels = {
  normal: "normal",
  warning: "warning",
  critical: "critical",
  paused: "paused",
};

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function number(value, digits = 2) {
  if (value === null || value === undefined || value === "") return "-";
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return "-";
  return parsed.toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function signed(value, digits = 4) {
  if (value === null || value === undefined || value === "") return "-";
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return "-";
  const sign = parsed > 0 ? "+" : "";
  return `${sign}${parsed.toFixed(digits)}`;
}

function pct(value, digits = 2) {
  if (value === null || value === undefined || value === "") return "-";
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return "-";
  const sign = parsed > 0 ? "+" : "";
  return `${sign}${parsed.toFixed(digits)}%`;
}

function money(value, digits = 4) {
  if (value === null || value === undefined || value === "") return "-";
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return "-";
  return `$${parsed.toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}`;
}

function priceLabel(value) {
  if (value === null || value === undefined || value === "") return "-";
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return "-";
  return parsed.toLocaleString("en-US", { maximumFractionDigits: 6 });
}

function symbolLabel(symbol) {
  return String(symbol || "").replace(/USDT$/, "");
}

async function fetchJson(path, options = {}) {
  const controller = new AbortController();
  const timeoutMs = options.timeoutMs || 15000;
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(path, {
      cache: "no-store",
      ...options,
      signal: controller.signal,
    });
    const text = await response.text();
    let payload = {};
    try {
      payload = text ? JSON.parse(text) : {};
    } catch (parseError) {
      parseError.kind = "parse";
      throw parseError;
    }
    if (!response.ok || payload.error) {
      const error = new Error(payload.error || `HTTP ${response.status}`);
      error.status = response.status;
      throw error;
    }
    return payload;
  } finally {
    window.clearTimeout(timer);
  }
}

async function loadStatus() {
  if (state.busy) return;
  setBusy(true);
  armSlowLoadWarning();
  try {
    await refreshDashboardData({ preserveChart: Boolean(state.chart.payload) });
    hideLoadError();
  } catch (error) {
    const message = readableError(error, "대시보드 로딩 실패");
    showLoadError(message);
    showToast(message);
  } finally {
    clearSlowLoadWarning();
    setBusy(false);
  }
}

async function refreshDashboardData({ preserveChart = true } = {}) {
  const [flow, payload, events] = await Promise.all([
    fetchJson("/api/paper/health/flow"),
    fetchJson("/api/paper/status"),
    fetchJson("/api/paper/health/events").catch(() => ({ events: state.healthEvents })),
  ]);
  state.flow = flow;
  state.health = flow.health || payload.health || flow;
  state.payload = payload;
  state.healthEvents = events.events || [];
  render();
  await loadChart({ preserveView: preserveChart });
}

function readableError(error, prefix) {
  const raw = error?.message || String(error);
  if (error?.name === "AbortError") return `${prefix}: API 응답 없음`;
  if (error?.kind === "parse") return `${prefix}: 데이터 파싱 실패`;
  if (/failed to fetch|network|load failed/i.test(raw)) return `${prefix}: 서버 연결 실패`;
  if (/csv|no such file|not found|missing/i.test(raw)) return `${prefix}: CSV 없음 또는 파일 경로 오류`;
  return `${prefix}: ${raw}`;
}

function setBusy(isBusy) {
  state.busy = isBusy;
  for (const button of document.querySelectorAll("button:not(#liveButton)")) {
    button.disabled = isBusy;
  }
}

function armSlowLoadWarning() {
  clearSlowLoadWarning();
  state.loadingTimer = window.setTimeout(() => {
    showLoadError("API 응답 없음: 5초 이상 데이터 로딩이 지연됩니다.");
  }, 5000);
}

function clearSlowLoadWarning() {
  if (!state.loadingTimer) return;
  window.clearTimeout(state.loadingTimer);
  state.loadingTimer = null;
}

function showLoadError(message) {
  const target = $("loadError");
  if (!target) return;
  target.textContent = message;
  target.hidden = false;
}

function hideLoadError() {
  const target = $("loadError");
  if (!target) return;
  target.hidden = true;
}

function render() {
  if (!state.payload) return;
  renderMode();
  syncChartSymbols();
  renderTopbar();
  renderStatus();
  renderControls();
  renderMetrics();
  renderHealth();
  renderSignals();
  renderPositions();
  renderRecentEvents();
  renderLogs();
  renderRawResponse();
  renderChartStatus();
  if (window.lucide) window.lucide.createIcons();
}

function renderMode() {
  const root = $("dashboardRoot");
  if (root) root.dataset.mode = state.mode;
  $("simpleModeButton")?.classList.toggle("active", state.mode === "simple");
  $("advancedModeButton")?.classList.toggle("active", state.mode === "advanced");
}

function setMode(mode, targetId = "") {
  state.mode = mode === "advanced" ? "advanced" : "simple";
  localStorage.setItem(STORAGE.mode, state.mode);
  renderMode();
  window.setTimeout(() => {
    resizeChart();
    renderChartMarkers();
    if (targetId) $(targetId)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, 50);
}

function renderTopbar() {
  const strategy = state.payload.strategy || {};
  const status = strategy.status || "normal";
  const badge = $("topStatusBadge");
  if (badge) {
    badge.textContent = statusLabels[status] || status;
    badge.dataset.status = status;
  }
  setText("topRegime", `regime ${strategy.current_regime || "-"}`);
  setText("topBias", `bias ${strategy.current_action_bias || "-"}`);
  setText("topCanEnter", strategy.can_enter ? "entry 가능" : "entry 불가");
}

function renderStatus() {
  const strategy = state.payload.strategy || {};
  const health = state.payload.health || state.health || {};
  const status = strategy.status || health.status || "normal";
  const badge = $("statusBadge");
  if (badge) {
    badge.textContent = statusLabels[status] || status;
    badge.dataset.status = status;
  }
  const message = beginnerMessageFor(strategy, health);
  setText("beginnerMessage", message);
  $("statusMetrics").innerHTML = [
    compactRow("신규 진입", strategy.can_enter ? "가능" : "불가"),
    compactRow("불가 사유", strategy.can_enter ? "-" : (strategy.pause_reason || health.final_block_reason || health.pause_reason || "-")),
    compactRow("현재 regime", strategy.current_regime || "-"),
    compactRow("action_bias", strategy.current_action_bias || "-"),
    compactRow("마지막 실행", strategy.last_run_at || "-"),
    compactRow("데이터", dataUpdateLabel(health, strategy)),
  ].join("");
}

function beginnerMessageFor(strategy, health) {
  const positions = state.payload.positions || [];
  const signals = state.payload.signals?.current || [];
  const dataStatus = health.component_status?.data;
  if (health.status === "paused" || strategy.status === "critical") return "위험 상태라 신규 진입을 막았습니다.";
  if (positions.length) return "현재 포지션을 보유 중입니다.";
  if (strategy.current_regime === "defensive" || strategy.current_action_bias === "reduce_risk") {
    return "현재 방어 모드라 신규 진입하지 않습니다.";
  }
  if (!strategy.can_enter && signals.some((signal) => signal.top_20_passed)) {
    return "후보는 있지만 주문 조건을 통과하지 못했습니다.";
  }
  if (dataStatus === "warning" || dataStatus === "critical") return "데이터 업데이트가 늦어지고 있습니다.";
  return strategy.can_enter ? "정상입니다. 봇이 대기 중입니다." : (strategy.beginner_message || "진입 조건을 기다리는 중입니다.");
}

function dataUpdateLabel(health, strategy) {
  const summary = health.data_gap_summary || {};
  if (summary.trading_failed_count || summary.unrepairable_count) return "확인 필요";
  return strategy.last_data_update_at || "-";
}

function renderControls() {
  const strategy = state.payload.strategy || {};
  const loop = strategy.loop || {};
  const loopBadge = $("loopBadge");
  if (loopBadge) {
    loopBadge.textContent = loop.running ? "loop on" : "loop off";
    loopBadge.dataset.running = loop.running ? "true" : "false";
  }
  setText("liveLockReason", strategy.live_lock?.reason || "paper only");
  const liveButton = $("liveButton");
  if (liveButton) liveButton.disabled = true;
}

function renderMetrics() {
  const target = $("performanceMetrics");
  if (!target) return;
  const metrics = state.payload.metrics || {};
  target.innerHTML = [
    metricTile("Equity", number(metrics.equity, 6)),
    metricTile("미실현 손익", signed(metrics.unrealized_pnl, 6), metrics.unrealized_pnl),
    metricTile("누적 손익", signed(metrics.cumulative_pnl, 6), metrics.cumulative_pnl),
    metricTile("최근 30일", pct(metrics.recent_30d_performance_pct), metrics.recent_30d_performance_pct),
    metricTile("최근 20거래 PF", metrics.recent_20_trade_pf === null ? "inf" : number(metrics.recent_20_trade_pf, 2)),
    metricTile("최근 20거래 승률", pct(metrics.recent_20_trade_win_rate_pct, 1)),
    metricTile("최대낙폭", pct(metrics.max_drawdown_pct), metrics.max_drawdown_pct),
  ].join("");
}

function renderHealth() {
  const health = state.health || state.payload.health || {};
  const flow = state.flow || {};
  const metrics = health.metrics || {};
  const components = health.component_status || {};
  const badge = $("healthBadge");
  if (!badge) return;
  badge.textContent = statusLabels[health.status] || health.status || "-";
  badge.dataset.status = health.status || "normal";
  setText("healthMessage", flow.beginner_message || health.beginner_message || "상태를 확인하는 중입니다");
  $("healthMetrics").innerHTML = [
    metricTile("신규 진입", health.new_entry_allowed ? "허용" : "금지"),
    metricTile("pause_reason", health.pause_reason || health.final_block_reason || "-"),
    metricTile("마지막 정상 실행", health.last_normal_run_at || "-"),
    metricTile("최근 20거래 PF", metrics.recent_20_trade_pf === null ? "-" : numberOrInf(metrics.recent_20_trade_pf)),
    metricTile("최근 50거래 PF", metrics.recent_50_trade_pf === null ? "-" : numberOrInf(metrics.recent_50_trade_pf)),
    metricTile("최근 30일 MDD", pct(metrics.recent_30d_mdd_pct), metrics.recent_30d_mdd_pct),
    metricTile("최근 7일 거래 수", number(metrics.recent_7d_trade_count, 0)),
    metricTile("최근 30일 거래 수", number(metrics.recent_30d_trade_count, 0)),
  ].join("");
  $("healthComponents").innerHTML = [
    componentPill("데이터 상태", components.data),
    componentPill("신호 상태", components.signal),
    componentPill("주문/포지션 상태", components.order_position),
    componentPill("리스크 상태", components.risk),
    componentPill("성과 상태", components.performance),
    componentPill("빈도 상태", components.frequency),
  ].join("");
  renderHealthFlow(flow);
}

function renderHealthFlow(flow) {
  const gates = flow.gates || {};
  const repair = state.repairing ? { status: "repairing" } : flow.repair || gates.data?.repair || {};
  $("healthFlowSteps").innerHTML = (flow.flow_steps || []).map((step) => `
    <div class="flow-step" data-status="${escapeHtml(step.status || "pending")}">
      <span>${escapeHtml(step.label || step.name)}</span>
      <strong>${escapeHtml(String(step.status || "pending").toUpperCase())}</strong>
    </div>
  `).join("");
  $("healthGateCards").innerHTML = [
    gateCard("Data Gate", gates.data?.status, [
      ["실패 사유", gates.data?.reason || gates.data?.failed_reason || "-"],
      ["영향 심볼", (gates.data?.affected_symbols || []).join(", ") || "-"],
      ["영향 timeframe", (gates.data?.affected_timeframes || []).join(", ") || "-"],
      ["매매 영향 gap", formatLogValue(gates.data?.affecting_gap_count)],
    ]),
    gateCard("Regime Gate", gates.regime?.status, [
      ["현재 regime", gates.regime?.regime || state.payload.strategy?.current_regime || "-"],
      ["현재 action_bias", gates.regime?.action_bias || state.payload.strategy?.current_action_bias || "-"],
      ["차단 사유", gates.regime?.reason || "-"],
    ]),
    gateCard("Risk Gate", gates.risk?.status, [
      ["liquidation buffer", formatLogValue(gates.risk?.liquidation_buffer)],
      ["applied_leverage", (gates.risk?.applied_leverage || []).map(leverageLabel).join(", ") || "-"],
      ["포지션 수", formatLogValue(gates.risk?.position_count)],
      ["청산 위험", gates.risk?.liquidation_risk ? "YES" : "NO"],
    ]),
    gateCard("Final Trading Gate", gates.final?.status, [
      ["New Entry Allowed", flow.new_entry_allowed ? "YES" : "NO"],
      ["최종 차단 사유", flow.final_block_reason || "-"],
    ]),
  ].join("");
  $("repairStatus").innerHTML = repairStatusHtml(repair);
  renderGapTable(gates.data?.data_gaps || flow.data_gaps || []);
  renderHealthLogPreview();
}

function gateCard(title, status, rows) {
  const value = status || "pending";
  return `
    <article class="gate-card" data-status="${escapeHtml(value)}">
      <div class="card-head">
        <h3>${escapeHtml(title)}</h3>
        <span class="card-badge">${escapeHtml(String(value).toUpperCase())}</span>
      </div>
      <dl>${rows.map(([label, value]) => dataRow(label, formatLogValue(value))).join("")}</dl>
    </article>
  `;
}

function repairStatusHtml(repair) {
  if (!repair?.status) return "";
  if (repair.status === "repairing") return `<div class="repair-line" data-status="running">repairing</div>`;
  return `
    <div class="repair-line" data-status="${escapeHtml(repair.validation_result || repair.status)}">
      <span>${escapeHtml(repair.status)}</span>
      <span>repaired ${escapeHtml(formatLogValue(repair.repaired_candle_count))}</span>
      <span>duplicate removed ${escapeHtml(formatLogValue(repair.duplicate_removed_count))}</span>
      <span>validation ${escapeHtml(formatLogValue(repair.validation_result))}</span>
    </div>
  `;
}

function renderGapTable(gaps) {
  const table = $("healthGapTable");
  if (!table) return;
  const columns = [
    ["symbol", "symbol"],
    ["timeframe", "timeframe"],
    ["gap_type", "gap_type"],
    ["missing_count", "missing_count"],
    ["start_time", "start_time"],
    ["end_time", "end_time"],
    ["affects_trading", "affects_trading"],
    ["repairable", "repairable"],
    ["status", "status"],
  ];
  renderTable(table, gaps.slice(0, 80), columns, "데이터 이상 상세가 없습니다");
}

function renderHealthLogPreview() {
  const target = $("healthLogPreview");
  if (!target || target.hidden) return;
  if (!state.healthEvents.length) {
    target.innerHTML = emptyState("상세 로그가 없습니다");
    return;
  }
  target.innerHTML = state.healthEvents.slice(0, 12).map((event) => `
    <div class="health-log-row">
      <strong>${escapeHtml(event.status || "-")}</strong>
      <span>${escapeHtml(event.section || "-")}.${escapeHtml(event.code || "-")}</span>
      <em>${escapeHtml(event.message || "")}</em>
    </div>
  `).join("");
}

function syncChartSymbols() {
  const select = $("chartSymbolSelect");
  if (!select || !state.payload) return;
  const payloadSymbols = state.payload.symbols || [];
  const symbols = [...new Set(payloadSymbols.length ? payloadSymbols : ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "LINKUSDT", "AVAXUSDT", "ADAUSDT", "TONUSDT"])];
  const preferred = defaultChartSymbol(symbols);
  if (!state.chart.symbol) state.chart.symbol = preferred;
  if (state.chart.symbol && !symbols.includes(state.chart.symbol)) symbols.unshift(state.chart.symbol);
  const current = select.value || state.chart.symbol || preferred;
  select.innerHTML = symbols
    .map((symbol) => `<option value="${escapeHtml(symbol)}">${escapeHtml(symbolLabel(symbol))}</option>`)
    .join("");
  select.value = symbols.includes(current) ? current : preferred;
  state.chart.symbol = select.value || preferred;
  $("chartTimeframeSelect").value = state.chart.timeframe;
  $("chartEventsToggle").checked = state.chart.showEvents;
}

function defaultChartSymbol(symbols) {
  const openPosition = state.payload?.positions?.[0]?.symbol;
  const topSignal = state.payload?.signals?.top_candidates?.[0]?.symbol;
  const currentSignal = state.payload?.signals?.current?.[0]?.symbol;
  const recentTrade = state.payload?.logs?.trades?.[0]?.symbol;
  return openPosition || topSignal || currentSignal || recentTrade || symbols[0] || "BTCUSDT";
}

async function loadChart(options = {}) {
  const symbolSelect = $("chartSymbolSelect");
  if (!symbolSelect || !state.payload) return;
  state.chart.symbol = symbolSelect.value || state.chart.symbol || defaultChartSymbol(state.payload.symbols || []);
  state.chart.timeframe = $("chartTimeframeSelect").value || state.chart.timeframe || "1H";
  localStorage.setItem(STORAGE.symbol, state.chart.symbol);
  localStorage.setItem(STORAGE.timeframe, state.chart.timeframe);
  const seq = ++state.chart.loadSeq;
  try {
    const query = new URLSearchParams({ symbol: state.chart.symbol, timeframe: state.chart.timeframe });
    const payload = await fetchJson(`/api/paper/chart?${query.toString()}`);
    if (seq !== state.chart.loadSeq) return;
    state.chart.payload = payload;
    state.chart.symbol = payload.symbol;
    state.chart.timeframe = payload.timeframe;
    symbolSelect.value = payload.symbol;
    $("chartTimeframeSelect").value = payload.timeframe;
    renderChart(payload, options.preserveView);
  } catch (error) {
    showChartMessage(readableError(error, "차트 로딩 실패"));
  }
}

function renderChart(payload, preserveView = false) {
  renderChartStatus();
  if (!window.LightweightCharts) {
    showChartMessage("차트 라이브러리를 불러오지 못했습니다");
    return;
  }
  if (!payload.candles?.length) {
    showChartMessage("표시할 캔들 데이터가 없습니다");
    return;
  }
  hideChartMessage();
  ensureChart();
  const previousRange = preserveView ? state.chart.instance.timeScale().getVisibleRange() : null;
  state.chart.candleSeries.setData(payload.candles);
  state.chart.volumeSeries.setData((payload.volume || []).map(enhanceVolumeBar));
  state.chart.emaSeries.ema20.setData(payload.ema20 || []);
  state.chart.emaSeries.ema50.setData(payload.ema50 || []);
  state.chart.emaSeries.ema200.setData(payload.ema200 || []);
  renderPriceLines(payload.price_lines || []);
  applyChartScale();
  resizeChart();
  if (previousRange) {
    state.chart.instance.timeScale().setVisibleRange(previousRange);
  } else {
    focusRecentBars(payload);
  }
  renderChartMarkers();
}

function ensureChart() {
  if (state.chart.instance) return;
  const container = $("paperChart");
  const chart = window.LightweightCharts.createChart(container, {
    width: container.clientWidth,
    height: container.clientHeight,
    autoSize: false,
    layout: {
      background: { type: "solid", color: "#131722" },
      textColor: "#d1d4dc",
      fontSize: 12,
    },
    grid: {
      vertLines: { color: "rgba(120, 144, 171, 0.18)" },
      horzLines: { color: "rgba(120, 144, 171, 0.18)" },
    },
    crosshair: {
      mode: window.LightweightCharts.CrosshairMode.Normal,
      vertLine: { color: "rgba(203, 213, 225, 0.32)", width: 1 },
      horzLine: { color: "rgba(203, 213, 225, 0.32)", width: 1 },
    },
    rightPriceScale: {
      borderColor: "rgba(148, 163, 184, 0.38)",
      scaleMargins: { top: 0.08, bottom: 0.24 },
    },
    timeScale: {
      borderColor: "rgba(148, 163, 184, 0.38)",
      timeVisible: true,
      secondsVisible: false,
      rightOffset: 12,
      barSpacing: 14,
      minBarSpacing: 5,
      lockVisibleTimeRangeOnResize: false,
      shiftVisibleRangeOnNewBar: false,
    },
    handleScroll: {
      mouseWheel: true,
      pressedMouseMove: true,
      horzTouchDrag: true,
      vertTouchDrag: true,
    },
    handleScale: {
      axisPressedMouseMove: true,
      mouseWheel: true,
      pinch: true,
    },
    kineticScroll: {
      touch: true,
      mouse: true,
    },
  });
  const candleSeries = chart.addCandlestickSeries({
    upColor: "#089981",
    downColor: "#f23645",
    borderUpColor: "#00e0a4",
    borderDownColor: "#ff6b75",
    wickUpColor: "#5eead4",
    wickDownColor: "#fca5a5",
    borderVisible: true,
    priceLineVisible: false,
  });
  const volumeSeries = chart.addHistogramSeries({
    priceFormat: { type: "volume" },
    priceScaleId: "volume",
    lastValueVisible: false,
    priceLineVisible: false,
  });
  chart.priceScale("volume").applyOptions({
    scaleMargins: { top: 0.82, bottom: 0 },
    borderVisible: false,
  });
  state.chart.instance = chart;
  state.chart.candleSeries = candleSeries;
  state.chart.volumeSeries = volumeSeries;
  state.chart.emaSeries = {
    ema20: chart.addLineSeries(lineSeriesOptions("#facc15")),
    ema50: chart.addLineSeries(lineSeriesOptions("#38bdf8")),
    ema200: chart.addLineSeries(lineSeriesOptions("#c084fc")),
  };
  chart.timeScale().subscribeVisibleTimeRangeChange(renderChartMarkers);
  if (!state.chart.resizeBound) {
    window.addEventListener("resize", () => {
      requestChartResize();
    });
    if (window.ResizeObserver) {
      state.chart.resizeObserver = new ResizeObserver(requestChartResize);
      state.chart.resizeObserver.observe($("paperChart"));
    }
    state.chart.resizeBound = true;
  }
}

function lineSeriesOptions(color) {
  return {
    color,
    lineWidth: 2,
    priceLineVisible: false,
    lastValueVisible: false,
    crosshairMarkerVisible: false,
  };
}

function requestChartResize() {
  window.requestAnimationFrame(() => {
    resizeChart();
    renderChartMarkers();
  });
}

function resizeChart() {
  if (!state.chart.instance) return;
  const container = $("paperChart");
  const width = Math.floor(container.clientWidth);
  const height = Math.floor(container.clientHeight);
  if (width <= 0 || height <= 0) return;
  if (typeof state.chart.instance.resize === "function") {
    state.chart.instance.resize(width, height, true);
  } else {
    state.chart.instance.applyOptions({ width, height });
  }
}

function focusRecentBars(payload) {
  const candles = payload.candles || [];
  if (!candles.length) return;
  const barsByTimeframe = {
    "15M": 150,
    "1H": 140,
    "4H": 130,
    "1D": 120,
  };
  const bars = barsByTimeframe[state.chart.timeframe] || 140;
  const to = candles.length + 8;
  const from = Math.max(0, candles.length - bars);
  const timeScale = state.chart.instance.timeScale();
  if (typeof timeScale.setVisibleLogicalRange === "function") {
    timeScale.setVisibleLogicalRange({ from, to });
  } else {
    timeScale.fitContent();
  }
}

function enhanceVolumeBar(bar) {
  const color = String(bar.color || "");
  const isRed = color.includes("239") || color.includes("ef4444");
  return {
    ...bar,
    color: isRed ? "rgba(242, 54, 69, 0.72)" : "rgba(8, 153, 129, 0.68)",
  };
}

function applyChartScale() {
  if (!state.chart.instance || !window.LightweightCharts?.PriceScaleMode) return;
  const mode = state.chart.logScale
    ? window.LightweightCharts.PriceScaleMode.Logarithmic
    : window.LightweightCharts.PriceScaleMode.Normal;
  state.chart.instance.priceScale("right").applyOptions({ mode });
  $("chartScaleButton").classList.toggle("active", state.chart.logScale);
}

function renderPriceLines(lines) {
  if (!state.chart.candleSeries) return;
  for (const line of state.chart.priceLines) {
    state.chart.candleSeries.removePriceLine(line);
  }
  const merged = mergePositionPriceLines(lines);
  state.chart.priceLines = merged
    .filter((line) => Number.isFinite(Number(line.price)))
    .map((line) => state.chart.candleSeries.createPriceLine({
      price: Number(line.price),
      color: line.color,
      lineWidth: line.id === "current" ? 2 : 1,
      lineStyle: line.id === "current"
        ? window.LightweightCharts.LineStyle.Solid
        : window.LightweightCharts.LineStyle.Dashed,
      axisLabelVisible: true,
      title: line.title,
    }));
}

function mergePositionPriceLines(lines) {
  const out = [...lines];
  const ids = new Set(out.map((line) => line.id));
  const position = selectedPosition();
  const liq = toFinite(position?.liquidation_price_est || position?.liquidation_price);
  if (liq !== null && !ids.has("liquidation")) {
    out.push({ id: "liquidation", title: `Liq ${priceLabel(liq)}`, price: liq, color: "#ef4444" });
  }
  return out;
}

function renderChartMarkers() {
  const overlay = $("paperMarkerOverlay");
  if (!overlay) return;
  overlay.innerHTML = "";
  if (!state.chart.showEvents || !state.chart.payload?.events?.length || !state.chart.instance) return;
  const grouped = new Map();
  for (const event of state.chart.payload.events) {
    const key = `${event.time}:${event.placement}`;
    if (!grouped.has(key)) grouped.set(key, []);
    grouped.get(key).push(event);
  }
  for (const events of grouped.values()) {
    events.forEach((event, index) => {
      const x = state.chart.instance.timeScale().timeToCoordinate(Number(event.time));
      const y = state.chart.candleSeries.priceToCoordinate(Number(event.price));
      if (x === null || y === null) return;
      const offset = (index - (events.length - 1) / 2) * 14;
      const badge = document.createElement("div");
      badge.className = "chart-marker-badge";
      badge.dataset.tone = event.tone;
      badge.textContent = event.label;
      badge.title = `${event.event} · ${event.date} · ${money(event.price, 4)}${event.reason ? ` · ${event.reason}` : ""}`;
      badge.style.left = `${Math.round(x + offset)}px`;
      badge.style.top = `${Math.round(y + (event.placement === "below" ? 15 : -18))}px`;
      overlay.appendChild(badge);
    });
  }
}

function renderChartStatus() {
  const target = $("chartStatus");
  if (!target) return;
  const status = state.chart.payload?.status;
  const strategy = state.payload?.strategy || {};
  const positions = state.chart.payload?.status?.open_positions ?? state.payload?.positions?.length ?? 0;
  target.innerHTML = [
    chartStatusPill("Symbol", `${symbolLabel(state.chart.symbol || status?.symbol || "-")} ${state.chart.timeframe || ""}`.trim()),
    chartStatusPill("Regime", status?.regime || strategy.current_regime || "-"),
    chartStatusPill("Bias", status?.action_bias || strategy.current_action_bias || "-"),
    chartStatusPill("Status", status?.strategy_status || strategy.status || "-"),
    chartStatusPill("Positions", String(positions)),
    chartStatusPill("Updated", status?.last_update || strategy.last_data_update_at || "-"),
  ].join("");
}

function chartStatusPill(label, value) {
  return `<span><em>${escapeHtml(label)}</em>${escapeHtml(value)}</span>`;
}

function showChartMessage(message) {
  const empty = $("chartEmpty");
  if (!empty) return;
  empty.textContent = message;
  empty.hidden = false;
}

function hideChartMessage() {
  const empty = $("chartEmpty");
  if (empty) empty.hidden = true;
}

function renderSignals() {
  const signals = state.payload.signals?.current || [];
  const topCandidates = state.payload.signals?.top_candidates || signals.filter((signal) => signal.top_20_passed);
  const summary = state.payload.signals?.scan_summary || {};
  const sideRows = topCandidates.length ? topCandidates : signals.slice(0, 6);
  $("signalSummary").innerHTML = renderSignalSummary(summary);
  $("signalCards").innerHTML = sideRows.length
    ? sideRows.map(compactSignalRow).join("")
    : emptyState("현재 진입 후보가 없습니다");
  renderAdvancedSignalTable(signals);
}

function renderSignalSummary(summary) {
  if (!summary.scan_count) return `<span>스캔 결과가 없습니다</span>`;
  const reasonText = Object.entries(summary.reason_counts || {})
    .slice(0, 3)
    .map(([reason, count]) => `${escapeHtml(reason)} ${count}`)
    .join(" · ");
  return `
    <strong>${escapeHtml(summary.top_label || "-")}</strong>
    <span>스캔 ${escapeHtml(summary.scan_count)}개 · 실제 진입 후보 ${escapeHtml(summary.entry_count || 0)}개</span>
    ${reasonText ? `<span>${reasonText}</span>` : ""}
  `;
}

function compactSignalRow(signal) {
  const flowSignal = signalFlowBySymbol(signal.symbol);
  const blockReason = flowSignal.block_reason || signal.order_reason || signal.rejection_reason || "";
  const statusText = signal.entry_allowed ? "진입 가능" : signal.top_20_passed ? "후보 통과" : "제외";
  const tone = signal.entry_allowed ? "good" : signal.top_20_passed ? "warn" : "muted";
  const reason = signal.reason_label || reasonLabel(blockReason) || "-";
  return `
    <article class="signal-row">
      <div class="signal-row-head">
        <span class="symbol-name">${escapeHtml(symbolLabel(signal.symbol))}</span>
        <span class="mini-badge ${tone}">${escapeHtml(statusText)}</span>
      </div>
      <div class="row-note">alpha ${escapeHtml(number(signal.alpha_score, 2))} · rank ${escapeHtml(formatLogValue(signal.rank))}/${escapeHtml(formatLogValue(signal.universe_size))}</div>
      <div class="row-note">${escapeHtml(reason)}</div>
    </article>
  `;
}

function signalFlowBySymbol(symbol) {
  return flowSignals().find((row) => row.symbol === symbol) || {};
}

function flowSignals() {
  return state.flow?.signals || state.flow?.gates?.final?.signals || [];
}

function renderAdvancedSignalTable(signals) {
  const table = $("advancedSignalTable");
  if (!table) return;
  const topCandidates = state.payload.signals?.top_candidates || signals.filter((signal) => signal.top_20_passed);
  const rows = state.signalView === "all" ? signals : topCandidates;
  for (const button of document.querySelectorAll(".signal-view-toggle .tab-button")) {
    button.classList.toggle("active", button.dataset.view === state.signalView);
  }
  renderTable(table, rows, [
    ["symbol", "symbol", symbolLabel],
    ["alpha_score", "alpha", (value) => number(value, 2)],
    ["rank", "rank"],
    ["top_20_passed", "top20", yesNo],
    ["selected", "entry", yesNo],
    ["reason_label", "reason"],
    ["expected_entry_price", "expected_entry", money],
    ["stop_price", "stop", money],
    ["raw_leverage", "raw_lev", (value) => number(value, 3)],
    ["applied_leverage", "lev", leverageLabel],
  ], "표시할 signal이 없습니다");
}

function renderPositions() {
  const positions = state.payload.positions || [];
  $("positionCards").innerHTML = positions.length
    ? positions.map(compactPositionRow).join("")
    : emptyState("현재 포지션이 없습니다");
  renderAdvancedPositionTable(positions);
}

function compactPositionRow(position) {
  return `
    <article class="position-row">
      <div class="position-row-head">
        <span class="symbol-name">${escapeHtml(symbolLabel(position.symbol))}</span>
        <span class="mini-badge good">보유 중</span>
      </div>
      <div class="row-note">Entry ${escapeHtml(priceLabel(position.entry_price))} · Stop ${escapeHtml(priceLabel(position.stop_price))}</div>
      <div class="row-note">Lev ${escapeHtml(leverageLabel(position.applied_leverage))} · PnL ${escapeHtml(signed(position.unrealized_pnl_number ?? position.unrealized_pnl, 6))}</div>
      <div class="row-note">보유 ${escapeHtml(holdTimeLabel(position))}${position.liquidation_price_est ? ` · Liq ${escapeHtml(priceLabel(position.liquidation_price_est))}` : ""}</div>
    </article>
  `;
}

function renderAdvancedPositionTable(positions) {
  const table = $("advancedPositionTable");
  if (!table) return;
  renderTable(table, positions, [
    ["symbol", "symbol", symbolLabel],
    ["side", "side"],
    ["entry_price", "entry", money],
    ["last_price", "current", money],
    ["stop_price", "stop", money],
    ["liquidation_price_est", "liq_est", money],
    ["applied_leverage", "lev", leverageLabel],
    ["unrealized_pnl", "unrealized", (value) => signed(value, 6)],
    ["liquidation_buffer_pct", "liq_buffer", pct],
    ["liquidation_risk", "liq_risk", yesNo],
    ["opened_at_date", "opened"],
  ], "현재 포지션이 없습니다");
}

function renderRecentEvents() {
  const logs = state.payload.logs || {};
  const signals = state.payload.signals?.recent || [];
  const groups = [
    eventGroup("Signals", signals.slice(0, 5), signalEventRow),
    eventGroup("Orders", (logs.orders || []).slice(0, 5), orderEventRow),
    eventGroup("Trades", (logs.trades || []).slice(0, 5), tradeEventRow),
    eventGroup("Health", state.healthEvents.slice(0, 5), healthEventRow),
  ];
  $("recentEvents").innerHTML = groups.join("");
}

function eventGroup(title, rows, formatter) {
  return `
    <div class="event-group">
      <h3>${escapeHtml(title)}</h3>
      ${rows.length ? rows.map(formatter).join("") : emptyState("최근 기록이 없습니다")}
    </div>
  `;
}

function signalEventRow(row) {
  const status = row.entry_allowed ? "진입 가능" : row.top_20_passed ? "후보 통과" : "제외";
  const tone = row.entry_allowed ? "good" : row.top_20_passed ? "warn" : "muted";
  return compactEventRow(symbolLabel(row.symbol), status, row.reason_label || row.rejection_reason || "-", tone);
}

function orderEventRow(row) {
  const tone = String(row.status || "").toLowerCase() === "filled" ? "good" : "warn";
  return compactEventRow(symbolLabel(row.symbol), row.status || "order", row.reason || row.created_date || "-", tone);
}

function tradeEventRow(row) {
  const pnl = toFinite(row.position_total_pnl || row.pnl);
  const tone = pnl === null ? "muted" : pnl >= 0 ? "good" : "bad";
  return compactEventRow(symbolLabel(row.symbol), row.event_type || "trade", `${row.reason || "-"} · ${signed(pnl, 6)}`, tone);
}

function healthEventRow(row) {
  const tone = row.status === "critical" ? "bad" : row.status === "warning" ? "warn" : "muted";
  const label = `${row.section || "-"} ${row.code || ""}`.trim();
  return compactEventRow(label, row.status || "health", row.message || "-", tone);
}

function compactEventRow(title, status, note, tone) {
  return `
    <article class="event-row">
      <div class="event-row-head">
        <span class="symbol-name">${escapeHtml(title || "-")}</span>
        <span class="mini-badge ${tone || "muted"}">${escapeHtml(status || "-")}</span>
      </div>
      <div class="row-note">${escapeHtml(note || "-")}</div>
    </article>
  `;
}

function renderLogs() {
  const logs = state.payload.logs || {};
  const rows = logs[state.activeTab] || [];
  const table = $("logTable");
  if (!table) return;
  for (const button of document.querySelectorAll(".tabs .tab-button")) {
    button.classList.toggle("active", button.dataset.tab === state.activeTab);
  }
  renderTable(table, rows, logColumns(state.activeTab), "최근 로그가 없습니다");
}

function logColumns(tab) {
  if (tab === "orders") {
    return [
      ["created_date", "시간"],
      ["symbol", "심볼", symbolLabel],
      ["status", "상태"],
      ["reason", "사유"],
      ["alpha_score", "alpha"],
      ["applied_leverage", "lev", leverageLabel],
    ];
  }
  if (tab === "trades") {
    return [
      ["date", "시간"],
      ["symbol", "심볼", symbolLabel],
      ["event_type", "종류"],
      ["reason", "사유"],
      ["pnl", "손익"],
      ["hold_hours", "보유시간"],
    ];
  }
  if (tab === "signals") {
    return [
      ["signal_date", "시간"],
      ["symbol", "심볼", symbolLabel],
      ["alpha_score", "alpha"],
      ["selected", "진입", yesNo],
      ["top_20_passed", "top20", yesNo],
      ["rejection_reason", "사유"],
    ];
  }
  return [
    ["date", "시간"],
    ["path", "위치"],
    ["message", "오류"],
  ];
}

function renderRawResponse() {
  const target = $("rawApiResponse");
  if (!target) return;
  target.textContent = JSON.stringify({
    status: state.payload,
    health_flow: state.flow,
    health_events: state.healthEvents.slice(0, 20),
  }, null, 2);
}

async function postAction(path, options = {}) {
  if (state.busy) return;
  if (options.confirmText && !window.confirm(options.confirmText)) return;
  setBusy(true);
  try {
    const payload = await fetchJson(path, { method: "POST" });
    if (payload.status) state.payload = payload.status;
    if (payload.health) state.health = payload.health;
    if (payload.flow) {
      state.flow = payload.flow;
      state.health = payload.flow.health || state.health;
    }
    await refreshDashboardData({ preserveChart: false });
    showToast(options.success || payload.message || "완료했습니다");
  } catch (error) {
    const message = readableError(error, "요청 실패");
    showToast(message);
  } finally {
    setBusy(false);
  }
}

async function postHealthAction(path, success) {
  if (state.busy) return;
  const reason = window.prompt("reason");
  if (!reason || !reason.trim()) {
    showToast("reason 입력이 필요합니다");
    return;
  }
  setBusy(true);
  try {
    await fetchJson(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason: reason.trim() }),
    });
    await refreshDashboardData({ preserveChart: true });
    showToast(success);
  } catch (error) {
    showToast(readableError(error, "Health 요청 실패"));
  } finally {
    setBusy(false);
  }
}

async function runDataRepair() {
  if (state.busy) return;
  setBusy(true);
  state.repairing = true;
  renderHealth();
  try {
    await fetchJson("/api/paper/health/repair", { method: "POST", timeoutMs: 30000 });
    state.repairing = false;
    await refreshDashboardData({ preserveChart: true });
    showToast("데이터 복구 실행 완료");
  } catch (error) {
    state.repairing = false;
    showToast(readableError(error, "데이터 복구 실패"));
  } finally {
    setBusy(false);
  }
}

async function recheckHealth() {
  if (state.busy) return;
  setBusy(true);
  try {
    await fetchJson("/api/paper/health/recheck", { method: "POST" });
    await refreshDashboardData({ preserveChart: true });
    showToast("Health 재검사 완료");
  } catch (error) {
    showToast(readableError(error, "Health 재검사 실패"));
  } finally {
    setBusy(false);
  }
}

async function toggleHealthLogs() {
  const target = $("healthLogPreview");
  if (!target) return;
  target.hidden = !target.hidden;
  if (target.hidden) return;
  try {
    const payload = await fetchJson("/api/paper/health/events");
    state.healthEvents = payload.events || [];
    renderHealthLogPreview();
  } catch (error) {
    showToast(readableError(error, "Health 로그 로딩 실패"));
  }
}

function compactRow(label, value) {
  return `
    <div class="compact-row">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
    </div>
  `;
}

function metricTile(label, value, rawValue = null) {
  const tone = rawValue === null ? "" : Number(rawValue) < 0 ? "bad" : Number(rawValue) > 0 ? "good" : "";
  return `
    <div class="metric-tile ${tone}">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
    </div>
  `;
}

function numberOrInf(value) {
  if (value === "inf" || value === Infinity) return "inf";
  return number(value, 2);
}

function componentPill(label, status) {
  const value = status || "normal";
  return `
    <div class="health-component" data-status="${escapeHtml(value)}">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(statusLabels[value] || value)}</strong>
    </div>
  `;
}

function dataRow(label, value) {
  return `
    <div>
      <dt>${escapeHtml(label)}</dt>
      <dd>${escapeHtml(value)}</dd>
    </div>
  `;
}

function renderTable(table, rows, columns, emptyMessage) {
  if (!rows.length) {
    table.innerHTML = `<tbody><tr><td class="empty-cell">${escapeHtml(emptyMessage)}</td></tr></tbody>`;
    return;
  }
  table.innerHTML = `
    <thead><tr>${columns.map((column) => `<th>${escapeHtml(column[1])}</th>`).join("")}</tr></thead>
    <tbody>
      ${rows.map((row) => `
        <tr>${columns.map(([key, , format]) => `<td>${escapeHtml(format ? format(row[key]) : formatLogValue(row[key]))}</td>`).join("")}</tr>
      `).join("")}
    </tbody>
  `;
}

function emptyState(message) {
  return `<div class="empty-state">${escapeHtml(message)}</div>`;
}

function formatLogValue(value) {
  if (value === true || value === "True") return "yes";
  if (value === false || value === "False") return "no";
  if (value === null || value === undefined || value === "") return "-";
  return value;
}

function leverageLabel(value) {
  if (value === null || value === undefined || value === "") return "-";
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return "-";
  return `${Math.trunc(parsed)}x`;
}

function yesNo(value) {
  if (value === true || value === "True" || value === "true") return "yes";
  if (value === false || value === "False" || value === "false") return "no";
  return formatLogValue(value);
}

function reasonLabel(reason) {
  const labels = {
    "": "진입 가능",
    defensive_no_entry: "reduce_risk로 주문 금지",
    regime_no_entry: "현재 레짐에서 신규 진입 금지",
    alpha_score_below_min: "alpha_score 부족",
    alpha_score_not_top_20pct: "top 20% 미통과",
    liquidation_buffer_unavailable: "liquidation buffer 실패",
    applied_leverage_liquidation_buffer: "정수 레버리지 적용 시 청산 안전거리가 부족합니다",
    max_positions: "보유 한도에 도달했습니다",
  };
  return labels[reason] || reason;
}

function holdTimeLabel(position) {
  const openedAt = toFinite(position.opened_at);
  if (openedAt === null) return "-";
  const reference = toFinite(state.health?.last_check_timestamp) || Math.floor(Date.now() / 1000);
  const hours = Math.max(0, (reference - openedAt) / 3600);
  if (hours < 1) return `${Math.round(hours * 60)}분`;
  if (hours < 48) return `${number(hours, 1)}시간`;
  return `${number(hours / 24, 1)}일`;
}

function selectedPosition() {
  return (state.payload?.positions || []).find((position) => position.symbol === state.chart.symbol);
}

function toFinite(value) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function setText(id, value) {
  const target = $(id);
  if (target) target.textContent = value;
}

function showToast(message) {
  const toast = $("toast");
  toast.textContent = message;
  toast.hidden = false;
  setTimeout(() => {
    toast.hidden = true;
  }, 4200);
}

function bindEvents() {
  $("refreshButton").addEventListener("click", loadStatus);
  $("simpleModeButton").addEventListener("click", () => setMode("simple"));
  $("advancedModeButton").addEventListener("click", () => setMode("advanced"));
  for (const button of document.querySelectorAll(".detail-button")) {
    button.addEventListener("click", () => setMode("advanced", button.dataset.detailTarget));
  }
  $("chartSymbolSelect").addEventListener("change", () => {
    state.chart.symbol = $("chartSymbolSelect").value;
    localStorage.setItem(STORAGE.symbol, state.chart.symbol);
    loadChart({ preserveView: false });
  });
  $("chartTimeframeSelect").addEventListener("change", () => {
    state.chart.timeframe = $("chartTimeframeSelect").value;
    localStorage.setItem(STORAGE.timeframe, state.chart.timeframe);
    loadChart({ preserveView: false });
  });
  $("chartFitButton").addEventListener("click", () => {
    if (state.chart.instance) {
      state.chart.instance.timeScale().fitContent();
      renderChartMarkers();
    }
  });
  $("chartScaleButton").addEventListener("click", () => {
    state.chart.logScale = !state.chart.logScale;
    applyChartScale();
  });
  $("chartFullscreenButton").addEventListener("click", () => {
    const panel = $("chartPanel");
    if (document.fullscreenElement) {
      document.exitFullscreen();
    } else if (panel.requestFullscreen) {
      panel.requestFullscreen();
    }
  });
  $("chartEventsToggle").addEventListener("change", () => {
    state.chart.showEvents = $("chartEventsToggle").checked;
    localStorage.setItem(STORAGE.events, String(state.chart.showEvents));
    renderChartMarkers();
  });
  $("showTopSignalsButton").addEventListener("click", () => {
    state.signalView = "top";
    renderSignals();
  });
  $("showAllSignalsButton").addEventListener("click", () => {
    state.signalView = "all";
    renderSignals();
  });
  $("runOnceButton").addEventListener("click", () => postAction("/api/paper/run-once", { success: "Run Once 완료" }));
  $("startLoopButton").addEventListener("click", () => postAction("/api/paper/start-loop", { success: "Loop 시작" }));
  $("stopLoopButton").addEventListener("click", () => postAction("/api/paper/stop-loop", { success: "Loop 중지 요청 완료" }));
  $("exportButton").addEventListener("click", () => {
    window.location.href = "/api/paper/export";
  });
  $("forceCloseButton").addEventListener("click", () => postAction("/api/paper/force-close", {
    confirmText: "열린 paper 포지션을 현재 기록 가격으로 강제 종료할까요?",
    success: "Paper 포지션 강제 종료 완료",
  }));
  $("clearStateButton").addEventListener("click", () => postAction("/api/paper/clear-state", {
    confirmText: "paper CSV 상태를 비웁니다. 계속할까요?",
    success: "Paper 상태 초기화 완료",
  }));
  $("manualPauseButton").addEventListener("click", () => postHealthAction("/api/paper/health/pause", "Health manual pause 완료"));
  $("manualResumeButton").addEventListener("click", () => postHealthAction("/api/paper/health/resume", "Health manual resume 완료"));
  $("dataRepairButton").addEventListener("click", runDataRepair);
  $("healthRecheckButton").addEventListener("click", recheckHealth);
  $("healthLogButton").addEventListener("click", toggleHealthLogs);
  for (const button of document.querySelectorAll(".tabs .tab-button")) {
    button.addEventListener("click", () => {
      state.activeTab = button.dataset.tab;
      renderLogs();
    });
  }
}

bindEvents();
setMode(state.mode);
loadStatus();
setInterval(loadStatus, 60000);
