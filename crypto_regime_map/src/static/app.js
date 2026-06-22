const $ = (id) => document.getElementById(id);

const state = {
  payload: null,
  chart: null,
  candleSeries: null,
  ema50Series: null,
  ema200Series: null,
  pointsByTime: new Map(),
};

function money(value) {
  if (value === null || value === undefined) return "-";
  return Number(value).toLocaleString("en-US", { maximumFractionDigits: 2 });
}

function number(value, digits = 1) {
  if (value === null || value === undefined) return "-";
  return Number(value).toFixed(digits);
}

function pct(value, digits = 2) {
  if (value === null || value === undefined) return "-";
  const number = Number(value) * 100;
  const sign = number > 0 ? "+" : "";
  return `${sign}${number.toFixed(digits)}%`;
}

function ratio(value, digits = 2) {
  if (value === null || value === undefined) return "-";
  return `${(Number(value) * 100).toFixed(digits)}%`;
}

function dateLabel(seconds) {
  return new Date(Number(seconds) * 1000).toLocaleDateString("ko-KR", {
    year: "2-digit",
    month: "2-digit",
    day: "2-digit",
  });
}

function fullDate(seconds) {
  return new Date(Number(seconds) * 1000).toLocaleString("ko-KR", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

async function loadData(refresh = false) {
  setLoading(true);
  try {
    const interval = $("interval").value || "1d";
    const response = await fetch(`/api/regime?interval=${encodeURIComponent(interval)}&refresh=${refresh ? "1" : "0"}`, {
      cache: "no-store",
    });
    const payload = await response.json();
    if (!response.ok || payload.error) {
      throw new Error(payload.error || `HTTP ${response.status}`);
    }
    state.payload = payload;
    state.pointsByTime = new Map(payload.points.map((point) => [String(point.time), point]));
    renderAll();
  } catch (error) {
    showToast(error.message || String(error));
  } finally {
    setLoading(false);
  }
}

function setLoading(isLoading) {
  const button = $("refreshButton");
  button.disabled = isLoading;
  $("chartMeta").textContent = isLoading ? "loading market data" : $("chartMeta").textContent;
}

function showToast(message) {
  const toast = $("toast");
  toast.textContent = message;
  toast.hidden = false;
  setTimeout(() => {
    toast.hidden = true;
  }, 5000);
}

function ensureChart() {
  if (!window.LightweightCharts) {
    $("chart").innerHTML = "<div class='chart-error'>TradingView chart library failed to load.</div>";
    return false;
  }
  if (state.chart) return true;

  const chartElement = $("chart");
  state.chart = LightweightCharts.createChart(chartElement, {
    width: chartElement.clientWidth,
    height: chartElement.clientHeight,
    layout: {
      background: { color: "transparent" },
      textColor: "#d8dee9",
      fontFamily: "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
    },
    grid: {
      vertLines: { color: "rgba(148, 163, 184, 0.12)" },
      horzLines: { color: "rgba(148, 163, 184, 0.12)" },
    },
    rightPriceScale: { borderColor: "rgba(148, 163, 184, 0.28)" },
    timeScale: {
      borderColor: "rgba(148, 163, 184, 0.28)",
      timeVisible: true,
      secondsVisible: false,
    },
    crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
  });

  state.candleSeries = state.chart.addCandlestickSeries({
    upColor: "#16c784",
    downColor: "#ea3943",
    borderUpColor: "#16c784",
    borderDownColor: "#ea3943",
    wickUpColor: "#16c784",
    wickDownColor: "#ea3943",
  });
  state.ema50Series = state.chart.addLineSeries({
    color: "#f2c94c",
    lineWidth: 2,
    priceLineVisible: false,
    title: "EMA50",
  });
  state.ema200Series = state.chart.addLineSeries({
    color: "#56ccf2",
    lineWidth: 2,
    priceLineVisible: false,
    title: "EMA200",
  });

  state.chart.timeScale().subscribeVisibleTimeRangeChange(drawRegimeOverlay);
  state.chart.subscribeCrosshairMove((param) => {
    if (!param || param.time === undefined) {
      renderSnapshot("cursorSnapshot", state.payload.latest);
      return;
    }
    const point = nearestPoint(normalizeTime(param.time));
    renderSnapshot("cursorSnapshot", point || state.payload.latest);
  });

  const resizeObserver = new ResizeObserver(() => {
    state.chart.applyOptions({
      width: chartElement.clientWidth,
      height: chartElement.clientHeight,
    });
    drawRegimeOverlay();
  });
  resizeObserver.observe(chartElement);
  return true;
}

function renderAll() {
  const payload = state.payload;
  if (!payload || !ensureChart()) return;
  state.candleSeries.setData(payload.candles);
  state.ema50Series.setData(payload.ema50);
  state.ema200Series.setData(payload.ema200);
  state.chart.timeScale().fitContent();

  $("chartTitle").textContent = `BTCUSDT ${payload.interval.toUpperCase()} 레짐`;
  $("chartMeta").textContent = `${payload.candles.length} candles | ${payload.segments.length} regime segments | ${fullDate(Date.parse(payload.generatedAt) / 1000)}`;
  $("latestPill").textContent = payload.latest.stable_regime_label || payload.latest.regime_label;
  $("latestPill").style.borderColor = payload.latest.stable_regime_color || payload.latest.regime_color;
  $("latestPill").style.color = payload.latest.stable_regime_color || payload.latest.regime_color;

  renderLegend();
  renderTimeline();
  renderSnapshot("latestSnapshot", payload.latest);
  renderSnapshot("cursorSnapshot", payload.latest);
  renderStats();
  renderMarketSnapshot(payload.latest);
  renderValidationReport(payload.report);
  requestAnimationFrame(drawRegimeOverlay);
  if (window.lucide) window.lucide.createIcons();
}

function renderLegend() {
  const regimes = state.payload.regimes;
  $("legend").innerHTML = Object.entries(regimes)
    .map(([key, item]) => `
      <span class="legend-item" data-regime="${escapeHtml(key)}">
        <span class="swatch" style="background:${item.color}"></span>
        ${escapeHtml(item.label)}
      </span>
    `)
    .join("");
}

function renderTimeline() {
  const segments = state.payload.segments;
  const timeline = $("timeline");
  if (!segments.length) {
    timeline.innerHTML = "";
    return;
  }
  const start = segments[0].from;
  const end = segments[segments.length - 1].to;
  const total = Math.max(1, end - start);
  timeline.innerHTML = "";
  for (const segment of segments) {
    const element = document.createElement("div");
    element.className = "timeline-segment";
    element.style.flexBasis = `${((segment.to - segment.from) / total) * 100}%`;
    element.style.background = segment.color;
    element.title = `${segment.label} · ${dateLabel(segment.from)} - ${dateLabel(segment.to)}`;
    timeline.appendChild(element);
  }
}

function renderStats() {
  $("regimeStats").innerHTML = state.payload.stats
    .map((item) => `
      <div class="stat-row">
        <div class="stat-label">
          <span class="swatch" style="background:${item.color}"></span>
          <span>${escapeHtml(item.label)}</span>
        </div>
        <strong>${ratio(item.pct, 1)}</strong>
        <div class="bar"><span style="width:${Math.max(2, item.pct * 100)}%;background:${item.color}"></span></div>
      </div>
    `)
    .join("");
}

function renderSnapshot(id, point) {
  if (!point) {
    $(id).innerHTML = "";
    return;
  }
  $(id).innerHTML = `
    <div class="regime-badge" style="border-color:${point.stable_regime_color || point.regime_color};color:${point.stable_regime_color || point.regime_color}">
      Stable: ${escapeHtml(point.stable_regime_label || point.regime_label)}
    </div>
    ${point.raw_regime_label ? `
      <div class="trade-regime">Raw: ${escapeHtml(point.raw_regime_label)}</div>
    ` : ""}
    ${point.trade_regime_label ? `
      <div class="trade-regime">적용 레짐: ${escapeHtml(point.trade_regime_label)}</div>
    ` : ""}
    ${point.stable_action_bias ? `
      <div class="trade-regime">Action bias: ${escapeHtml(point.stable_action_bias)}</div>
    ` : ""}
    <dl>
      <div><dt>날짜</dt><dd>${dateLabel(point.time)}</dd></div>
      <div><dt>BTC</dt><dd>$${money(point.close)}</dd></div>
      <div><dt>수익률</dt><dd class="${Number(point.return || 0) >= 0 ? "good" : "bad"}">${pct(point.return)}</dd></div>
      <div><dt>EMA50</dt><dd>$${money(point.ema50)}</dd></div>
      <div><dt>EMA200</dt><dd>$${money(point.ema200)}</dd></div>
      <div><dt>ATR%</dt><dd>${ratio(point.atr_pct)}</dd></div>
    </dl>
  `;
}

function renderMarketSnapshot(point) {
  $("marketSnapshot").innerHTML = `
    <div class="metric"><span>ETH/BTC</span><strong>${money(point.eth_btc)}</strong></div>
    <div class="metric"><span>알트 상승 비율</span><strong>${ratio(point.alt_up_ratio, 1)}</strong></div>
    <div class="metric"><span>알트 EMA200 위</span><strong>${ratio(point.alt_above_ema200_ratio, 1)}</strong></div>
    <div class="metric"><span>알트 샘플</span><strong>${point.alt_count ?? "-"}</strong></div>
  `;
}

function renderValidationReport(report) {
  if (!report) return;
  $("durationTable").innerHTML = `
    <thead>
      <tr><th>레짐</th><th>발생</th><th>총일</th><th>평균</th><th>최소</th><th>최대</th></tr>
    </thead>
    <tbody>
      ${report.durationSummary.map((row) => `
        <tr>
          <td>${regimeName(row)}</td>
          <td>${row.occurrences}</td>
          <td>${row.totalDays}</td>
          <td>${number(row.averageDays, 1)}</td>
          <td>${row.minDays}</td>
          <td>${row.maxDays}</td>
        </tr>
      `).join("")}
    </tbody>
  `;

  $("performanceTable").innerHTML = `
    <thead>
      <tr><th>레짐</th><th>일수</th><th>BTC 평균</th><th>BTC 누적</th><th>ETH 평균</th><th>알트 평균</th><th>변동성</th><th>MDD</th></tr>
    </thead>
    <tbody>
      ${report.performanceSummary.map((row) => `
        <tr>
          <td>${regimeName(row)}</td>
          <td>${row.days}</td>
          <td>${pct(row.btcAverageDailyReturn)}</td>
          <td>${pct(row.btcCumulativeReturn)}</td>
          <td>${pct(row.ethAverageDailyReturn)}</td>
          <td>${pct(row.altAverageDailyReturn)}</td>
          <td>${ratio(row.volatility)}</td>
          <td>${ratio(row.maxDrawdown)}</td>
        </tr>
      `).join("")}
    </tbody>
  `;

  renderBenchmarkReport(report.benchmarkReport);
  renderLabelMigrationReport(report.labelMigrationReport);
  renderActionBiasPerformance(report.actionBiasPerformance);
  renderPolicyBacktestReport(report.policyBacktestReport);
  renderPolicyBacktestAuditReport(report.policyBacktestAuditReport);
  renderSimpleBaselineChallengeReport(report.simpleBaselineChallengeReport);
  renderRiskNormalizedComparisonReport(report.riskNormalizedComparisonReport);
  renderHybridOverlayChallengeReport(report.hybridOverlayChallengeReport);
  renderOverlayAblationReport(report.overlayAblationReport);
  renderEthStrengthSensitivityReport(report.ethStrengthSensitivityReport);
  renderAltUniverseRobustnessReport(report.altUniverseRobustnessReport);
  renderLabelRevalidationReport(report.labelRevalidationReport);

  $("eventTable").innerHTML = `
    <thead>
      <tr><th>구간</th><th>Raw</th><th>Stable</th><th>Trade</th><th>Raw 위험</th><th>Stable 위험</th><th>Trade 위험</th><th>BTC</th><th>ETH</th><th>알트</th><th>Stable 구성</th></tr>
    </thead>
    <tbody>
      ${report.eventChecks.map((row) => `
        <tr>
          <td><strong>${escapeHtml(row.event)}</strong><span>${escapeHtml(row.start)} - ${escapeHtml(row.end)}</span></td>
          <td>${regimeLabel(row.rawDominantRegime)}</td>
          <td>${regimeLabel(row.stableDominantRegime)}</td>
          <td>${regimeLabel(row.tradeDominantRegime)}</td>
          <td>${delayDays(row.rawRiskDelayDays)}</td>
          <td>${delayDays(row.stableRiskDelayDays)}</td>
          <td>${delayDays(row.tradeRiskDelayDays)}</td>
          <td>${pct(row.btcCumulativeReturn)}</td>
          <td>${pct(row.ethCumulativeReturn)}</td>
          <td>${pct(row.altCumulativeReturn)}</td>
          <td>${mixLabel(row.stableMix)}</td>
        </tr>
      `).join("")}
    </tbody>
  `;

  $("stabilityTable").innerHTML = `
    <thead>
      <tr><th>기준</th><th>변경 횟수</th><th>평균 지속</th><th>최소</th><th>최대</th><th>상승 평균</th><th>BTC 평균</th><th>알트 평균</th><th>하락 평균</th></tr>
    </thead>
    <tbody>
      ${report.stabilityComparison.map((row) => `
        <tr>
          <td>${escapeHtml(row.scope)}</td>
          <td>${row.changeCount}</td>
          <td>${number(row.averageDays, 1)}</td>
          <td>${row.minDays}</td>
          <td>${row.maxDays}</td>
          <td>${number(row.bullAverageDays, 1)}</td>
          <td>${number(row.btcAverageDays, 1)}</td>
          <td>${number(row.altAverageDays, 1)}</td>
          <td>${number(row.bearAverageDays, 1)}</td>
        </tr>
      `).join("")}
    </tbody>
  `;

  $("returnCompareTable").innerHTML = `
    <thead>
      <tr><th>레짐</th><th>Raw 일수</th><th>Raw BTC 평균</th><th>Raw BTC 누적</th><th>Stable 일수</th><th>Stable BTC 평균</th><th>Stable BTC 누적</th></tr>
    </thead>
    <tbody>
      ${report.returnComparison.map((row) => `
        <tr>
          <td>${regimeName(row)}</td>
          <td>${row.rawDays}</td>
          <td>${pct(row.rawBtcAverageDailyReturn)}</td>
          <td>${pct(row.rawBtcCumulativeReturn)}</td>
          <td>${row.stableDays}</td>
          <td>${pct(row.stableBtcAverageDailyReturn)}</td>
          <td>${pct(row.stableBtcCumulativeReturn)}</td>
        </tr>
      `).join("")}
    </tbody>
  `;

  renderV2V3Comparison(report.v2v3Comparison);
  renderObserveReport(report.observe);

  $("lookaheadChecks").innerHTML = report.lookahead.checks
    .map((check) => `
      <div class="check ${escapeHtml(check.status)}">
        <strong>${escapeHtml(check.name)}</strong>
        <span>${escapeHtml(check.status)}</span>
        <p>${escapeHtml(check.detail)}</p>
      </div>
    `)
    .join("");
}

function renderHybridOverlayChallengeReport(report) {
  if (!report) return;
  $("hybridPassFailTable").innerHTML = `
    <thead>
      <tr><th>Hybrid</th><th>Base</th><th>Calmar</th><th>MDD 20%</th><th>CAGR 유지</th><th>Base CAGR</th><th>Hybrid CAGR</th><th>Base MDD</th><th>Hybrid MDD</th></tr>
    </thead>
    <tbody>
      ${(report.passFail || []).map((row) => `
        <tr>
          <td>${escapeHtml(row.hybrid)}</td>
          <td>${escapeHtml(row.base)}</td>
          <td><span class="check-pill ${escapeHtml(row.calmarPass)}">${benchmarkStatusLabel(row.calmarPass)}</span><span>${number(row.baseCalmar, 2)} → ${number(row.hybridCalmar, 2)}</span></td>
          <td><span class="check-pill ${escapeHtml(row.riskPass)}">${benchmarkStatusLabel(row.riskPass)}</span></td>
          <td><span class="check-pill ${escapeHtml(row.cagrStatus)}">${benchmarkStatusLabel(row.cagrStatus)}</span></td>
          <td>${pct(row.baseCagr)}</td>
          <td>${pct(row.hybridCagr)}</td>
          <td>${ratio(row.baseMdd)}</td>
          <td>${ratio(row.hybridMdd)}</td>
        </tr>
      `).join("")}
    </tbody>
  `;
  $("hybridOverlayTable").innerHTML = `
    <thead>
      <tr><th>역할</th><th>전략</th><th>Base</th><th>총수익</th><th>CAGR</th><th>MDD</th><th>Sharpe</th><th>Calmar</th><th>Turnover</th><th>비용</th><th>참여율</th></tr>
    </thead>
    <tbody>
      ${(report.comparisonRows || []).map((row) => `
        <tr>
          <td>${escapeHtml(row.role)}</td>
          <td>${escapeHtml(row.label)}</td>
          <td>${escapeHtml(row.baseLabel)}</td>
          <td>${pct(row.totalReturn)}</td>
          <td>${pct(row.cagr)}</td>
          <td>${ratio(row.maxDrawdown)}</td>
          <td>${number(row.sharpe, 2)}</td>
          <td>${number(row.calmar, 2)}</td>
          <td>${row.turnover === undefined ? "-" : `${number(row.turnover, 2)}x`}</td>
          <td>${pct(row.totalTradingCost)}</td>
          <td>${pct(row.marketParticipation, 1)}</td>
        </tr>
      `).join("")}
    </tbody>
  `;
}

function renderOverlayAblationReport(report) {
  if (!report) return;
  $("overlayAblationPassTable").innerHTML = `
    <thead>
      <tr><th>Base</th><th>Full Overlay</th><th>Shock Only</th><th>판정</th><th>메시지</th></tr>
    </thead>
    <tbody>
      ${(report.passFail || []).map((row) => `
        <tr>
          <td>${escapeHtml(row.base)}</td>
          <td>${number(row.fullOverlayCalmar, 2)}</td>
          <td>${number(row.shockOnlyCalmar, 2)}</td>
          <td><span class="check-pill ${escapeHtml(row.status)}">${benchmarkStatusLabel(row.status)}</span></td>
          <td>${escapeHtml(row.message)}</td>
        </tr>
      `).join("")}
    </tbody>
  `;
  $("overlayAblationTable").innerHTML = `
    <thead>
      <tr><th>Base</th><th>Overlay</th><th>총수익</th><th>CAGR</th><th>MDD</th><th>Sharpe</th><th>Calmar</th><th>Turnover</th><th>비용</th><th>참여율</th></tr>
    </thead>
    <tbody>
      ${(report.rows || []).map((row) => `
        <tr>
          <td>${escapeHtml(row.baseLabel)}</td>
          <td>${escapeHtml(row.overlayLabel)}</td>
          <td>${pct(row.totalReturn)}</td>
          <td>${pct(row.cagr)}</td>
          <td>${ratio(row.maxDrawdown)}</td>
          <td>${number(row.sharpe, 2)}</td>
          <td>${number(row.calmar, 2)}</td>
          <td>${number(row.turnover, 2)}x</td>
          <td>${pct(row.totalTradingCost)}</td>
          <td>${pct(row.marketParticipation, 1)}</td>
        </tr>
      `).join("")}
    </tbody>
  `;
}

function renderEthStrengthSensitivityReport(report) {
  if (!report) return;
  const check = report.passFail || {};
  $("ethStrengthSensitivityCheck").innerHTML = `
    <div class="check ${escapeHtml(check.status)}">
      <strong>eth_strength_rule</strong>
      <span>${escapeHtml(check.status)}</span>
      <p>${escapeHtml(check.message)} · current ${number(check.currentCalmar, 2)} · best ${escapeHtml(check.bestAlternative)} ${number(check.bestAlternativeCalmar, 2)}</p>
    </div>
  `;
  $("ethStrengthSensitivityTable").innerHTML = `
    <thead>
      <tr><th>조건</th><th>일수</th><th>발생</th><th>평균 지속</th><th>ALT</th><th>BTC</th><th>초과</th><th>CAGR</th><th>MDD</th><th>Sharpe</th><th>Calmar</th></tr>
    </thead>
    <tbody>
      ${(report.rows || []).map((row) => `
        <tr>
          <td>${escapeHtml(row.label)}</td>
          <td>${row.activeDays}</td>
          <td>${row.occurrences}</td>
          <td>${number(row.averageDays, 1)}d</td>
          <td>${pct(row.altCumulativeReturn)}</td>
          <td>${pct(row.btcCumulativeReturn)}</td>
          <td>${pct(row.btcExcessReturn)}</td>
          <td>${pct(row.cagr)}</td>
          <td>${ratio(row.maxDrawdown)}</td>
          <td>${number(row.sharpe, 2)}</td>
          <td>${number(row.calmar, 2)}</td>
        </tr>
      `).join("")}
    </tbody>
  `;
}

function renderAltUniverseRobustnessReport(report) {
  if (!report) return;
  $("altRobustnessWarnings").innerHTML = (report.warnings || []).map((row) => `
    <div class="check ${escapeHtml(row.status)}">
      <strong>${escapeHtml(row.name)}</strong>
      <span>${escapeHtml(row.status)}</span>
      <p>${escapeHtml(row.detail)}</p>
    </div>
  `).join("");
  $("altRobustnessStartTable").innerHTML = `
    <thead>
      <tr><th>시작연도</th><th>총수익</th><th>CAGR</th><th>MDD</th><th>Sharpe</th><th>Calmar</th></tr>
    </thead>
    <tbody>
      ${(report.startYearRows || []).map((row) => `
        <tr>
          <td>${row.startYear}</td>
          <td>${pct(row.totalReturn)}</td>
          <td>${pct(row.cagr)}</td>
          <td>${ratio(row.maxDrawdown)}</td>
          <td>${number(row.sharpe, 2)}</td>
          <td>${number(row.calmar, 2)}</td>
        </tr>
      `).join("")}
    </tbody>
  `;
  $("altLeaveOneOutTable").innerHTML = `
    <thead>
      <tr><th>제외</th><th>총수익</th><th>CAGR</th><th>MDD</th><th>Sharpe</th><th>Calmar</th></tr>
    </thead>
    <tbody>
      ${(report.leaveOneOut || []).map((row) => `
        <tr>
          <td>${escapeHtml(row.excluded)}</td>
          <td>${pct(row.totalReturn)}</td>
          <td>${pct(row.cagr)}</td>
          <td>${ratio(row.maxDrawdown)}</td>
          <td>${number(row.sharpe, 2)}</td>
          <td>${number(row.calmar, 2)}</td>
        </tr>
      `).join("")}
    </tbody>
  `;
  $("altMinCountTable").innerHTML = `
    <thead>
      <tr><th>조건</th><th>총수익</th><th>CAGR</th><th>MDD</th><th>Sharpe</th><th>Calmar</th><th>참여율</th></tr>
    </thead>
    <tbody>
      ${(report.minCountRows || []).map((row) => `
        <tr>
          <td>${escapeHtml(row.label)}</td>
          <td>${pct(row.totalReturn)}</td>
          <td>${pct(row.cagr)}</td>
          <td>${ratio(row.maxDrawdown)}</td>
          <td>${number(row.sharpe, 2)}</td>
          <td>${number(row.calmar, 2)}</td>
          <td>${pct(row.marketParticipation, 1)}</td>
        </tr>
      `).join("")}
    </tbody>
  `;
}

function renderSimpleBaselineChallengeReport(report) {
  if (!report) return;
  $("simpleBaselineChecks").innerHTML = (report.passFail?.checks || []).map((row) => `
    <div class="check ${escapeHtml(row.status)}">
      <strong>${escapeHtml(row.name)}</strong>
      <span>${escapeHtml(row.status)}</span>
      <p>policy ${formatAuditValue(row.policyValue ?? row.policyReturn)} · baseline ${formatAuditValue(row.baselineValue ?? row.baselineMedianReturn)}</p>
    </div>
  `).join("");
  $("simpleBaselineTable").innerHTML = `
    <thead>
      <tr><th>구분</th><th>전략</th><th>총수익</th><th>CAGR</th><th>MDD</th><th>Sharpe</th><th>Calmar</th><th>Turnover</th><th>비용</th><th>참여율</th></tr>
    </thead>
    <tbody>
      ${(report.comparisonRows || []).map((row) => `
        <tr>
          <td>${escapeHtml(row.group)}</td>
          <td>${escapeHtml(row.label)}</td>
          <td>${pct(row.totalReturn)}</td>
          <td>${pct(row.cagr)}</td>
          <td>${ratio(row.maxDrawdown)}</td>
          <td>${number(row.sharpe, 2)}</td>
          <td>${number(row.calmar, 2)}</td>
          <td>${row.turnover === undefined ? "-" : `${number(row.turnover, 2)}x`}</td>
          <td>${pct(row.totalTradingCost)}</td>
          <td>${pct(row.marketParticipation, 1)}</td>
        </tr>
      `).join("")}
    </tbody>
  `;
  $("simpleRebalanceTable").innerHTML = `
    <thead>
      <tr><th>주기</th><th>구분</th><th>전략</th><th>총수익</th><th>CAGR</th><th>MDD</th><th>Calmar</th><th>Turnover</th><th>비용</th></tr>
    </thead>
    <tbody>
      ${(report.rebalanceComparison || []).map((row) => `
        <tr>
          <td>${escapeHtml(row.rebalance)}</td>
          <td>${escapeHtml(row.group)}</td>
          <td>${escapeHtml(row.label)}</td>
          <td>${pct(row.totalReturn)}</td>
          <td>${pct(row.cagr)}</td>
          <td>${ratio(row.maxDrawdown)}</td>
          <td>${number(row.calmar, 2)}</td>
          <td>${number(row.turnover, 2)}x</td>
          <td>${pct(row.totalTradingCost)}</td>
        </tr>
      `).join("")}
    </tbody>
  `;
  $("simpleCostTable").innerHTML = `
    <thead>
      <tr><th>비용</th><th>구분</th><th>전략</th><th>총수익</th><th>CAGR</th><th>MDD</th><th>Calmar</th><th>Turnover</th></tr>
    </thead>
    <tbody>
      ${(report.costSensitivity || []).map((row) => `
        <tr>
          <td>${escapeHtml(row.cost)}</td>
          <td>${escapeHtml(row.group)}</td>
          <td>${escapeHtml(row.label)}</td>
          <td>${pct(row.totalReturn)}</td>
          <td>${pct(row.cagr)}</td>
          <td>${ratio(row.maxDrawdown)}</td>
          <td>${number(row.calmar, 2)}</td>
          <td>${number(row.turnover, 2)}x</td>
        </tr>
      `).join("")}
    </tbody>
  `;
}

function renderRiskNormalizedComparisonReport(report) {
  if (!report) return;
  $("riskWinnerTable").innerHTML = `
    <thead>
      <tr><th>기준</th><th>승자</th><th>그룹</th><th>값</th></tr>
    </thead>
    <tbody>
      ${(report.winners || []).map((row) => `
        <tr>
          <td>${escapeHtml(row.name)}</td>
          <td>${escapeHtml(row.winner)}</td>
          <td>${escapeHtml(row.group)}</td>
          <td>${formatAuditValue(row.value)}</td>
        </tr>
      `).join("")}
    </tbody>
  `;
  renderRiskScaledTable("sameVolatilityTable", report.sameVolatilityRows || [], true);
  renderRiskScaledTable("sameDrawdownTable", report.sameDrawdownRows || [], false);
  renderRiskScaledTable("policyLeverageTable", report.policyLeverageRows || [], false);
}

function renderRiskScaledTable(tableId, rows, showVol) {
  $(tableId).innerHTML = `
    <thead>
      <tr><th>전략</th><th>그룹</th><th>스케일</th><th>총수익</th><th>CAGR</th><th>MDD</th><th>Sharpe</th><th>Calmar</th>${showVol ? "<th>변동성</th>" : "<th>목표 MDD</th>"}</tr>
    </thead>
    <tbody>
      ${rows.map((row) => `
        <tr>
          <td>${escapeHtml(row.label)}</td>
          <td>${escapeHtml(row.kind)}</td>
          <td>${number(row.scale, 2)}x</td>
          <td>${pct(row.totalReturn)}</td>
          <td>${pct(row.cagr)}</td>
          <td>${ratio(row.maxDrawdown)}</td>
          <td>${number(row.sharpe, 2)}</td>
          <td>${number(row.calmar, 2)}</td>
          <td>${showVol ? ratio(row.volatility) : ratio(row.targetMdd)}</td>
        </tr>
      `).join("")}
    </tbody>
  `;
}

function formatAuditValue(value) {
  if (value === null || value === undefined) return "-";
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return escapeHtml(value);
  return Math.abs(numeric) <= 3 ? number(numeric, 2) : pct(numeric);
}

function renderPolicyBacktestAuditReport(report) {
  if (!report) return;
  renderPolicyAuditPassFail(report.passFail || []);
  renderAuditBenchmarkTable(report.benchmarkDetailedComparison || []);
  renderUniverseAudit(report.universeAudit);
  renderExecutionTiming(report.executionTiming);
  renderOosReport(report.oos);
}

function renderPolicyAuditPassFail(rows) {
  $("policyAuditPassFailTable").innerHTML = `
    <thead>
      <tr><th>정책</th><th>MDD 감소</th><th>MDD</th><th>Calmar</th><th>Cost 0.2%</th><th>Regime Change</th><th>Policy Calmar</th><th>BTC Calmar</th></tr>
    </thead>
    <tbody>
      ${rows.map((row) => `
        <tr>
          <td>${escapeHtml(row.policy)}</td>
          <td>${pct(row.mddReduction, 1)}</td>
          <td><span class="check-pill ${escapeHtml(row.mddPass)}">${benchmarkStatusLabel(row.mddPass)}</span></td>
          <td><span class="check-pill ${escapeHtml(row.efficiencyPass)}">${benchmarkStatusLabel(row.efficiencyPass)}</span></td>
          <td><span class="check-pill ${escapeHtml(row.costPass)}">${benchmarkStatusLabel(row.costPass)}</span><span>${pct(row.cost02Cagr)} CAGR</span></td>
          <td><span class="check-pill ${escapeHtml(row.robustnessPass)}">${benchmarkStatusLabel(row.robustnessPass)}</span><span>${pct(row.regimeChangeCagr)} CAGR</span></td>
          <td>${number(row.policyCalmar, 2)}</td>
          <td>${number(row.btcCalmar, 2)}</td>
        </tr>
      `).join("")}
    </tbody>
  `;
}

function renderAuditBenchmarkTable(rows) {
  $("auditBenchmarkTable").innerHTML = `
    <thead>
      <tr><th>구분</th><th>이름</th><th>총수익</th><th>CAGR</th><th>MDD</th><th>Sharpe</th><th>Calmar</th><th>변동성</th><th>승률</th><th>MDD 기간</th></tr>
    </thead>
    <tbody>
      ${rows.map((row) => `
        <tr>
          <td>${escapeHtml(row.group)}</td>
          <td>${escapeHtml(row.label)}</td>
          <td>${pct(row.totalReturn)}</td>
          <td>${pct(row.cagr)}</td>
          <td>${ratio(row.maxDrawdown)}</td>
          <td>${number(row.sharpe, 2)}</td>
          <td>${number(row.calmar, 2)}</td>
          <td>${ratio(row.volatility)}</td>
          <td>${pct(row.winRate, 1)}</td>
          <td><strong>${escapeHtml(row.maxDrawdownPeriod?.start)}</strong><span>${escapeHtml(row.maxDrawdownPeriod?.end)} · ${row.maxDrawdownPeriod?.days ?? 0}d</span></td>
        </tr>
      `).join("")}
    </tbody>
  `;
}

function renderUniverseAudit(report) {
  if (!report) return;
  const composition = report.composition || {};
  $("universeSummary").innerHTML = `
    <div class="metric"><span>평균 ALT 편입</span><strong>${number(composition.averageCount, 1)}</strong></div>
    <div class="metric"><span>최소 / 최대</span><strong>${composition.minCount ?? 0} / ${composition.maxCount ?? 0}</strong></div>
    <div class="metric"><span>3개 미만 날짜</span><strong>${pct(composition.below3Pct, 1)}</strong></div>
    <div class="metric"><span>3개 미만 최대 연속</span><strong>${composition.maxBelow3RunDays ?? 0}d</strong></div>
  `;
  $("universeWarnings").innerHTML = (report.warnings || []).map((row) => `
    <div class="check ${escapeHtml(row.status)}">
      <strong>${escapeHtml(row.name)}</strong>
      <span>${escapeHtml(row.status)}</span>
      <p>${escapeHtml(row.detail)}</p>
    </div>
  `).join("");
  $("symbolStartTable").innerHTML = `
    <thead>
      <tr><th>심볼</th><th>시작일</th><th>종료일</th><th>일수</th></tr>
    </thead>
    <tbody>
      ${(report.symbolStartRows || []).map((row) => `
        <tr>
          <td>${escapeHtml(row.symbol)}</td>
          <td>${escapeHtml(row.start)}</td>
          <td>${escapeHtml(row.end)}</td>
          <td>${row.days}</td>
        </tr>
      `).join("")}
    </tbody>
  `;
  $("altContributionTable").innerHTML = `
    <thead>
      <tr><th>심볼</th><th>최초 편입</th><th>편입일수</th><th>자체 누적</th><th>누적 기여</th><th>양수 기여 비중</th></tr>
    </thead>
    <tbody>
      ${(report.altContributionRows || []).map((row) => `
        <tr>
          <td>${escapeHtml(row.symbol)}</td>
          <td>${escapeHtml(row.firstIncluded)}</td>
          <td>${row.includedDays}</td>
          <td>${pct(row.ownCumulativeReturn)}</td>
          <td>${pct(row.cumulativeContributionReturn)}</td>
          <td>${pct(row.positiveContributionShare, 1)}</td>
        </tr>
      `).join("")}
    </tbody>
  `;
  renderUniverseSensitivity(report.sensitivity);
}

function renderUniverseSensitivity(report) {
  const rows = report?.rows || [];
  $("universeSensitivityTable").innerHTML = `
    <thead>
      <tr><th>Universe</th><th>정책</th><th>총수익</th><th>CAGR</th><th>MDD</th><th>Calmar</th><th>Sharpe</th><th>BTC 초과</th><th>비용</th></tr>
    </thead>
    <tbody>
      ${rows.map((row) => `
        <tr>
          <td><strong>${escapeHtml(row.scenarioLabel)}</strong><span>${escapeHtml((row.symbols || []).join(", "))}</span></td>
          <td>${escapeHtml(row.policy)}</td>
          <td>${pct(row.totalReturn)}</td>
          <td>${pct(row.cagr)}</td>
          <td>${ratio(row.maxDrawdown)}</td>
          <td>${number(row.calmar, 2)}</td>
          <td>${number(row.sharpe, 2)}</td>
          <td>${pct(row.excessReturnVsBtc)}</td>
          <td>${pct(row.totalTradingCost)}</td>
        </tr>
      `).join("")}
    </tbody>
  `;
}

function renderExecutionTiming(report) {
  if (!report) return;
  $("executionTimingChecks").innerHTML = (report.checks || []).map((row) => `
    <div class="check ${escapeHtml(row.status)}">
      <strong>${escapeHtml(row.label)}</strong>
      <span>${escapeHtml(row.status)}</span>
      <p>${escapeHtml(row.description)} · shift ${row.tradeRegimeShiftOk ? "ok" : "fail"} · action ${row.actionBiasShiftOk ? "ok" : "fail"} · open/close ${row.openCloseDataOk ? "ok" : "fail"}</p>
    </div>
  `).join("");
  $("executionTimingTable").innerHTML = `
    <thead>
      <tr><th>모드</th><th>정책</th><th>총수익</th><th>CAGR</th><th>MDD</th><th>Turnover</th><th>비용</th><th>룩어헤드</th></tr>
    </thead>
    <tbody>
      ${(report.rows || []).map((row) => `
        <tr>
          <td>${escapeHtml(row.label)}</td>
          <td>${escapeHtml(row.policy)}</td>
          <td>${pct(row.totalReturn)}</td>
          <td>${pct(row.cagr)}</td>
          <td>${ratio(row.maxDrawdown)}</td>
          <td>${number(row.turnover, 2)}x</td>
          <td>${pct(row.totalTradingCost)}</td>
          <td><span class="check-pill ${escapeHtml(row.lookaheadStatus)}">${benchmarkStatusLabel(row.lookaheadStatus)}</span></td>
        </tr>
      `).join("")}
    </tbody>
  `;
}

function renderOosReport(report) {
  if (!report) return;
  const rows = [
    ...(report.trainDev?.benchmarks || []),
    ...(report.trainDev?.policies || []),
    ...(report.oos?.benchmarks || []).map((row) => ({ ...row, scopeOverride: "oos" })),
    ...(report.oos?.policies || []).map((row) => ({ ...row, scopeOverride: "oos" })),
  ];
  $("oosSummaryTable").innerHTML = `
    <thead>
      <tr><th>구간</th><th>구분</th><th>이름</th><th>총수익</th><th>CAGR</th><th>MDD</th><th>Sharpe</th><th>Calmar</th><th>Turnover</th><th>비용</th></tr>
    </thead>
    <tbody>
      ${rows.map((row) => `
        <tr>
          <td>${escapeHtml(row.scopeOverride || "train/dev")}</td>
          <td>${escapeHtml(row.group)}</td>
          <td>${escapeHtml(row.label)}</td>
          <td>${pct(row.totalReturn)}</td>
          <td>${pct(row.cagr)}</td>
          <td>${ratio(row.maxDrawdown)}</td>
          <td>${number(row.sharpe, 2)}</td>
          <td>${number(row.calmar, 2)}</td>
          <td>${row.turnover === undefined ? "-" : `${number(row.turnover, 2)}x`}</td>
          <td>${pct(row.totalTradingCost)}</td>
        </tr>
      `).join("")}
    </tbody>
  `;
  $("oosDailyTable").innerHTML = `
    <thead>
      <tr><th>날짜</th><th>정책</th><th>Action Bias</th><th>BTC</th><th>ETH</th><th>ALT</th><th>현금</th><th>수익률</th><th>Turnover</th><th>비용</th></tr>
    </thead>
    <tbody>
      ${(report.oos?.daily || []).slice(-96).map((row) => `
        <tr>
          <td>${escapeHtml(row.date)}</td>
          <td>${escapeHtml(row.policy)}</td>
          <td>${escapeHtml(row.actionBias)}</td>
          <td>${pct(row.btcWeight, 0)}</td>
          <td>${pct(row.ethWeight, 0)}</td>
          <td>${pct(row.altWeight, 0)}</td>
          <td>${pct(row.cashWeight, 0)}</td>
          <td>${pct(row.return)}</td>
          <td>${number(row.turnover, 2)}x</td>
          <td>${pct(row.tradingCost)}</td>
        </tr>
      `).join("")}
    </tbody>
  `;
  $("rollingOosTable").innerHTML = `
    <thead>
      <tr><th>월</th><th>정책</th><th>Policy 수익률</th><th>BTC 수익률</th><th>MDD</th><th>Turnover</th><th>비용</th></tr>
    </thead>
    <tbody>
      ${(report.rollingMonthly || []).map((row) => `
        <tr>
          <td>${escapeHtml(row.month)}</td>
          <td>${escapeHtml(row.policy)}</td>
          <td>${pct(row.totalReturn)}</td>
          <td>${pct(row.btcReturn)}</td>
          <td>${ratio(row.maxDrawdown)}</td>
          <td>${number(row.turnover, 2)}x</td>
          <td>${pct(row.totalTradingCost)}</td>
        </tr>
      `).join("")}
    </tbody>
  `;
}

function renderPolicyBacktestReport(report) {
  if (!report) return;
  renderPolicySummaryTable(report.defaultRun?.rows || []);
  renderPolicyBenchmarkTable(report.benchmarks || []);
  renderPolicyCostTable(report.costSensitivity || []);
  renderPolicyRebalanceTable(report.rebalanceComparison || []);
  renderPolicyEquityChart(report.defaultRun?.equityCurves || []);
  renderPolicyYearlyTable(report.defaultRun?.rows || []);
  renderPolicyMonthlyTable(report.defaultRun?.rows || []);
}

function renderPolicySummaryTable(rows) {
  $("policySummaryTable").innerHTML = `
    <thead>
      <tr><th>정책</th><th>총수익</th><th>CAGR</th><th>MDD</th><th>Sharpe</th><th>Calmar</th><th>승률</th><th>Turnover</th><th>거래비용</th><th>참여율</th><th>BTC 초과</th><th>MDD 축소</th></tr>
    </thead>
    <tbody>
      ${rows.map((row) => `
        <tr>
          <td><strong>${escapeHtml(row.label)}</strong><span>${escapeHtml(row.rebalance)}</span></td>
          <td>${pct(row.totalReturn)}</td>
          <td>${pct(row.cagr)}</td>
          <td>${ratio(row.maxDrawdown)}</td>
          <td>${number(row.sharpe, 2)}</td>
          <td>${number(row.calmar, 2)}</td>
          <td>${pct(row.winRate, 1)}</td>
          <td>${number(row.turnover, 2)}x</td>
          <td>${pct(row.totalTradingCostPct)}</td>
          <td>${pct(row.marketParticipation, 1)}</td>
          <td>${pct(row.excessReturnVsBtc)}</td>
          <td><span class="check-pill ${escapeHtml(row.mddReducedVsBtcStatus)}">${benchmarkStatusLabel(row.mddReducedVsBtcStatus)}</span></td>
        </tr>
      `).join("")}
    </tbody>
  `;
}

function renderPolicyBenchmarkTable(rows) {
  $("policyBenchmarkTable").innerHTML = `
    <thead>
      <tr><th>벤치마크</th><th>총수익</th><th>CAGR</th><th>MDD</th><th>Sharpe</th><th>Calmar</th><th>승률</th><th>참여율</th><th>최대 낙폭 기간</th></tr>
    </thead>
    <tbody>
      ${rows.map((row) => `
        <tr>
          <td>${escapeHtml(row.label)}</td>
          <td>${pct(row.totalReturn)}</td>
          <td>${pct(row.cagr)}</td>
          <td>${ratio(row.maxDrawdown)}</td>
          <td>${number(row.sharpe, 2)}</td>
          <td>${number(row.calmar, 2)}</td>
          <td>${pct(row.winRate, 1)}</td>
          <td>${pct(row.marketParticipation, 1)}</td>
          <td><strong>${escapeHtml(row.maxDrawdownPeriod?.start)}</strong><span>${escapeHtml(row.maxDrawdownPeriod?.end)} · ${row.maxDrawdownPeriod?.days ?? 0}d</span></td>
        </tr>
      `).join("")}
    </tbody>
  `;
}

function renderPolicyCostTable(groups) {
  const rows = groups.flatMap((group) => group.rows.map((row) => ({ cost: group.label, ...row })));
  $("policyCostTable").innerHTML = `
    <thead>
      <tr><th>비용</th><th>정책</th><th>총수익</th><th>CAGR</th><th>MDD</th><th>BTC 초과</th><th>거래비용</th><th>Turnover</th></tr>
    </thead>
    <tbody>
      ${rows.map((row) => `
        <tr>
          <td>${escapeHtml(row.cost)}</td>
          <td>${escapeHtml(row.label)}</td>
          <td>${pct(row.totalReturn)}</td>
          <td>${pct(row.cagr)}</td>
          <td>${ratio(row.maxDrawdown)}</td>
          <td>${pct(row.excessReturnVsBtc)}</td>
          <td>${pct(row.totalTradingCostPct)}</td>
          <td>${number(row.turnover, 2)}x</td>
        </tr>
      `).join("")}
    </tbody>
  `;
}

function renderPolicyRebalanceTable(groups) {
  const rows = groups.flatMap((group) => group.rows.map((row) => ({ rebalance: group.rebalance, ...row })));
  $("policyRebalanceTable").innerHTML = `
    <thead>
      <tr><th>주기</th><th>정책</th><th>총수익</th><th>CAGR</th><th>MDD</th><th>BTC 초과</th><th>거래비용</th><th>Turnover</th><th>MDD 축소</th></tr>
    </thead>
    <tbody>
      ${rows.map((row) => `
        <tr>
          <td>${escapeHtml(row.rebalance)}</td>
          <td>${escapeHtml(row.label)}</td>
          <td>${pct(row.totalReturn)}</td>
          <td>${pct(row.cagr)}</td>
          <td>${ratio(row.maxDrawdown)}</td>
          <td>${pct(row.excessReturnVsBtc)}</td>
          <td>${pct(row.totalTradingCostPct)}</td>
          <td>${number(row.turnover, 2)}x</td>
          <td><span class="check-pill ${escapeHtml(row.mddReducedVsBtcStatus)}">${benchmarkStatusLabel(row.mddReducedVsBtcStatus)}</span></td>
        </tr>
      `).join("")}
    </tbody>
  `;
}

function renderPolicyYearlyTable(rows) {
  const years = sortedPeriodLabels(rows, "yearlyReturns", "year");
  $("policyYearlyTable").innerHTML = `
    <thead>
      <tr><th>연도</th>${rows.map((row) => `<th>${escapeHtml(row.label)}</th>`).join("")}</tr>
    </thead>
    <tbody>
      ${years.map((year) => `
        <tr>
          <td>${escapeHtml(year)}</td>
          ${rows.map((row) => `<td>${pct(periodReturn(row.yearlyReturns, "year", year))}</td>`).join("")}
        </tr>
      `).join("")}
    </tbody>
  `;
}

function renderPolicyMonthlyTable(rows) {
  const months = sortedPeriodLabels(rows, "monthlyReturns", "month").slice(-24);
  $("policyMonthlyTable").innerHTML = `
    <thead>
      <tr><th>월</th>${rows.map((row) => `<th>${escapeHtml(row.label)}</th>`).join("")}</tr>
    </thead>
    <tbody>
      ${months.map((month) => `
        <tr>
          <td>${escapeHtml(month)}</td>
          ${rows.map((row) => `<td>${pct(periodReturn(row.monthlyReturns, "month", month))}</td>`).join("")}
        </tr>
      `).join("")}
    </tbody>
  `;
}

function sortedPeriodLabels(rows, listKey, labelKey) {
  return [...new Set(rows.flatMap((row) => (row[listKey] || []).map((item) => item[labelKey])))]
    .filter(Boolean)
    .sort();
}

function periodReturn(items, labelKey, label) {
  const item = (items || []).find((row) => row[labelKey] === label);
  return item ? item.return : null;
}

function renderPolicyEquityChart(curves) {
  const chart = $("policyEquityChart");
  const validCurves = curves
    .map((curve) => ({ ...curve, points: (curve.points || []).filter((point) => point.time && point.value) }))
    .filter((curve) => curve.points.length > 1);
  if (!validCurves.length) {
    chart.innerHTML = "";
    return;
  }

  const width = 920;
  const height = 320;
  const pad = { left: 54, right: 18, top: 20, bottom: 38 };
  const allPoints = validCurves.flatMap((curve) => curve.points);
  const minTime = Math.min(...allPoints.map((point) => point.time));
  const maxTime = Math.max(...allPoints.map((point) => point.time));
  const minValue = Math.min(...allPoints.map((point) => point.value));
  const maxValue = Math.max(...allPoints.map((point) => point.value));
  const yMin = Math.max(0, minValue * 0.94);
  const yMax = maxValue * 1.04;
  const colors = ["#16c784", "#56ccf2", "#f2c94c", "#ea3943", "#9b5cf6"];
  const x = (time) => pad.left + ((time - minTime) / Math.max(1, maxTime - minTime)) * (width - pad.left - pad.right);
  const y = (value) => pad.top + (1 - ((value - yMin) / Math.max(0.000001, yMax - yMin))) * (height - pad.top - pad.bottom);
  const paths = validCurves.map((curve, index) => {
    const d = curve.points
      .map((point, pointIndex) => `${pointIndex === 0 ? "M" : "L"}${x(point.time).toFixed(1)},${y(point.value).toFixed(1)}`)
      .join(" ");
    return `<path class="curve" d="${d}" stroke="${colors[index % colors.length]}"></path>`;
  }).join("");
  const legend = validCurves.map((curve, index) => {
    const xPos = pad.left + index * 172;
    const yPos = height - 12;
    return `
      <g>
        <line x1="${xPos}" y1="${yPos - 4}" x2="${xPos + 18}" y2="${yPos - 4}" stroke="${colors[index % colors.length]}" stroke-width="3"></line>
        <text class="legend-text" x="${xPos + 24}" y="${yPos}">${escapeHtml(curve.label)}</text>
      </g>
    `;
  }).join("");

  chart.innerHTML = `
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Policy equity curve">
      <line class="axis" x1="${pad.left}" y1="${pad.top}" x2="${pad.left}" y2="${height - pad.bottom}"></line>
      <line class="axis" x1="${pad.left}" y1="${height - pad.bottom}" x2="${width - pad.right}" y2="${height - pad.bottom}"></line>
      <text x="8" y="${y(yMax).toFixed(1)}">${number(yMax, 2)}x</text>
      <text x="8" y="${y(yMin).toFixed(1)}">${number(yMin, 2)}x</text>
      <text x="${pad.left}" y="${height - 22}">${dateLabel(minTime)}</text>
      <text x="${width - 96}" y="${height - 22}">${dateLabel(maxTime)}</text>
      ${paths}
      ${legend}
    </svg>
  `;
}

function renderLabelRevalidationReport(report) {
  if (!report) return;
  renderLabelFailSegmentTable(report);
  renderDefensiveWarningTable(report);
  renderEthBtcStrengthTable(report);
}

function renderLabelMigrationReport(report) {
  if (!report) return;
  $("labelMigrationTable").innerHTML = `
    <thead>
      <tr><th>기존 키</th><th>기존 라벨</th><th>새 키</th><th>새 라벨</th><th>Action Bias</th></tr>
    </thead>
    <tbody>
      ${report.rows.map((row) => `
        <tr>
          <td>${escapeHtml(row.legacy)}</td>
          <td>${escapeHtml(row.legacyLabel)}</td>
          <td>${regimeLabel(row.regime)}</td>
          <td>${escapeHtml(row.label)}</td>
          <td>${escapeHtml(row.actionBias)}</td>
        </tr>
      `).join("")}
    </tbody>
  `;
}

function renderActionBiasPerformance(report) {
  if (!report) return;
  renderActionBiasTable("stableActionBiasTable", report.stable);
  renderActionBiasTable("tradeActionBiasTable", report.trade);
}

function renderActionBiasTable(tableId, scope) {
  if (!scope) return;
  $(tableId).innerHTML = `
    <thead>
      <tr><th>Action Bias</th><th>레짐</th><th>일수</th><th>BTC</th><th>ETH</th><th>상위 알트</th><th>현금</th><th>최적</th></tr>
    </thead>
    <tbody>
      ${scope.rows.map((row) => `
        <tr>
          <td>${escapeHtml(row.actionBias)}</td>
          <td>${row.regimes.map((regime) => regimeLabel(regime)).join(" ")}</td>
          <td>${row.days}</td>
          <td>${pct(row.btcCumulativeReturn)}</td>
          <td>${pct(row.ethCumulativeReturn)}</td>
          <td>${pct(row.altCumulativeReturn)}</td>
          <td>${pct(row.cashCumulativeReturn)}</td>
          <td>${assetLabel(row.bestAsset)} ${pct(row.bestAssetReturn)}</td>
        </tr>
      `).join("")}
    </tbody>
  `;
}

function renderLabelFailSegmentTable(report) {
  const rows = ["stable", "trade"].flatMap((scope) => [
    ...report[scope].largeCapLead.nonWinningSegments.map((row) => ({ scope, regime: "large_cap_lead", ...row })),
    ...report[scope].ethStrength.weakerThanBtcSegments.map((row) => ({ scope, regime: "eth_strength", ...row })),
  ]);
  const visibleRows = [...rows].sort((a, b) => b.days - a.days).slice(0, 24);
  $("labelFailSegmentTable").innerHTML = `
    <thead>
      <tr><th>기준</th><th>레짐</th><th>구간</th><th>일수</th><th>BTC</th><th>ETH</th><th>알트</th><th>구간 최적</th><th>원인</th></tr>
    </thead>
    <tbody>
      ${visibleRows.length ? visibleRows.map((row) => `
        <tr>
          <td>${escapeHtml(row.scope)}</td>
          <td>${regimeLabel(row.regime)}</td>
          <td><strong>${escapeHtml(row.start)}</strong><span>${escapeHtml(row.end)}</span></td>
          <td>${row.days}</td>
          <td>${pct(row.btcCumulativeReturn)}</td>
          <td>${pct(row.ethCumulativeReturn)}</td>
          <td>${pct(row.altCumulativeReturn)}</td>
          <td>${assetLabel(row.bestRiskAsset)} ${pct(row.bestRiskAssetReturn)}</td>
          <td><span>${escapeHtml(row.reason)}</span></td>
        </tr>
      `).join("") : `<tr><td colspan="9">fail 구간 없음</td></tr>`}
    </tbody>
  `;
}

function renderDefensiveWarningTable(report) {
  const rows = ["stable", "trade"].flatMap((scope) => [
    ...report[scope].defensive.holdingAdvantageSegments.map((row) => ({ scope, regime: "defensive", issue: "보유 우위", ...row })),
    ...report[scope].defensive.reboundSegments.map((row) => ({ scope, regime: "defensive", issue: "반등 후보", ...row })),
    ...report[scope].shock.holdingAdvantageSegments.map((row) => ({ scope, regime: "shock", issue: "보유 우위", ...row })),
    ...report[scope].shock.reboundSegments.map((row) => ({ scope, regime: "shock", issue: "반등 후보", ...row })),
  ]);
  const visibleRows = [...rows].sort((a, b) => b.days - a.days).slice(0, 24);
  $("defensiveWarningTable").innerHTML = `
    <thead>
      <tr><th>기준</th><th>레짐</th><th>구간</th><th>일수</th><th>BTC</th><th>ETH</th><th>알트</th><th>최적</th><th>확인</th></tr>
    </thead>
    <tbody>
      ${visibleRows.length ? visibleRows.map((row) => `
        <tr>
          <td>${escapeHtml(row.scope)}</td>
          <td>${regimeLabel(row.regime)}</td>
          <td><strong>${escapeHtml(row.start)}</strong><span>${escapeHtml(row.end)}</span></td>
          <td>${row.days}</td>
          <td>${pct(row.btcCumulativeReturn)}</td>
          <td>${pct(row.ethCumulativeReturn)}</td>
          <td>${pct(row.altCumulativeReturn)}</td>
          <td>${assetLabel(row.bestAsset)} ${pct(row.bestAssetReturn)}</td>
          <td><strong>${escapeHtml(row.issue)}</strong><span>${row.reboundCandidate ? "반등장 잔존 가능" : escapeHtml(row.reason)}</span></td>
        </tr>
      `).join("") : `<tr><td colspan="9">warning 구간 없음</td></tr>`}
    </tbody>
  `;
}

function renderEthBtcStrengthTable(report) {
  const rows = ["stable", "trade"].map((scope) => ({
    scope,
    ...report[scope].ethStrength.ethBtcStrengthCheck,
  }));
  $("ethBtcStrengthTable").innerHTML = `
    <thead>
      <tr><th>기준</th><th>일수</th><th>ETH/BTC 상승</th><th>확정 상승</th><th>알트 > BTC</th><th>Hit</th><th>Coverage</th><th>판정</th></tr>
    </thead>
    <tbody>
      ${rows.map((row) => `
        <tr>
          <td>${escapeHtml(row.scope)}</td>
          <td>${row.days}</td>
          <td>${row.ethBtcRisingDays}</td>
          <td>${row.ethBtcConfirmedDays}</td>
          <td>${row.altBeatsBtcDays}</td>
          <td>${pct(row.confirmedHitRate, 1)}</td>
          <td>${pct(row.confirmedCoverage, 1)}</td>
          <td><span class="check-pill ${escapeHtml(row.status)}">${benchmarkStatusLabel(row.status)}</span><span>${escapeHtml(row.message)}</span></td>
        </tr>
      `).join("")}
    </tbody>
  `;
}

function renderBenchmarkReport(report) {
  if (!report) return;
  renderBenchmarkTable("stableBenchmarkTable", report.stable);
  renderBenchmarkTable("tradeBenchmarkTable", report.trade);
}

function renderBenchmarkTable(tableId, scope) {
  if (!scope) return;
  $(tableId).innerHTML = `
    <thead>
      <tr><th>레짐</th><th>일수</th><th>BTC</th><th>ETH</th><th>상위 알트</th><th>현금</th><th>최적</th><th>검증</th></tr>
    </thead>
    <tbody>
      ${scope.rows.map((row) => `
        <tr>
          <td>${regimeName(row)}</td>
          <td>${row.days}</td>
          <td>${pct(row.btcCumulativeReturn)}</td>
          <td>${pct(row.ethCumulativeReturn)}</td>
          <td>${pct(row.altCumulativeReturn)}</td>
          <td>${pct(row.cashCumulativeReturn)}</td>
          <td>${assetLabel(row.bestAsset)} ${pct(row.bestAssetReturn)}</td>
          <td><span class="check-pill ${escapeHtml(row.validationStatus)}">${benchmarkStatusLabel(row.validationStatus)}</span><span>${escapeHtml(row.validationMessage)}</span></td>
        </tr>
      `).join("")}
    </tbody>
  `;
}

function renderV2V3Comparison(comparison) {
  if (!comparison) return;

  $("v2v3SummaryTable").innerHTML = `
    <thead>
      <tr><th>버전</th><th>Stable 변경</th><th>평균 지속</th><th>Observe 총일</th><th>Observe 최대</th><th>평균 위험 지연</th></tr>
    </thead>
    <tbody>
      ${comparison.summary.map((row) => `
        <tr>
          <td>${escapeHtml(row.version)}</td>
          <td>${row.stableChangeCount}</td>
          <td>${number(row.averageDays, 1)}d</td>
          <td>${row.observeTotalDays}</td>
          <td>${row.observeMaxDays}</td>
          <td>${row.averageEventRiskDelayDays === null || row.averageEventRiskDelayDays === undefined ? "-" : `${number(row.averageEventRiskDelayDays, 1)}d`}</td>
        </tr>
      `).join("")}
    </tbody>
  `;

  $("v2v3EventRiskTable").innerHTML = `
    <thead>
      <tr><th>이벤트</th><th>v2 위험 지연</th><th>v3 위험 지연</th></tr>
    </thead>
    <tbody>
      ${comparison.eventRiskDelay.map((row) => `
        <tr>
          <td><strong>${escapeHtml(row.event)}</strong><span>${escapeHtml(row.start)} - ${escapeHtml(row.end)}</span></td>
          <td>${delayDays(row.v2RiskDelayDays)}</td>
          <td>${delayDays(row.v3RiskDelayDays)}</td>
        </tr>
      `).join("")}
    </tbody>
  `;

  $("v2v3ReturnTable").innerHTML = `
    <thead>
      <tr><th>레짐</th><th>v2 일수</th><th>v2 BTC 평균</th><th>v2 BTC 누적</th><th>v3 일수</th><th>v3 BTC 평균</th><th>v3 BTC 누적</th></tr>
    </thead>
    <tbody>
      ${comparison.regimeReturns.map((row) => `
        <tr>
          <td>${regimeName(row)}</td>
          <td>${row.v2Days}</td>
          <td>${pct(row.v2BtcAverageDailyReturn)}</td>
          <td>${pct(row.v2BtcCumulativeReturn)}</td>
          <td>${row.v3Days}</td>
          <td>${pct(row.v3BtcAverageDailyReturn)}</td>
          <td>${pct(row.v3BtcCumulativeReturn)}</td>
        </tr>
      `).join("")}
    </tbody>
  `;

  const check = comparison.observeLimitCheck;
  $("observeLimitCheckTable").innerHTML = `
    <thead>
      <tr><th>구간</th><th>제한</th><th>v2 Observe 총/최대</th><th>v3 Observe 총/최대</th><th>결과</th></tr>
    </thead>
    <tbody>
      <tr>
        <td><strong>${escapeHtml(check.name)}</strong><span>${escapeHtml(check.start)} - ${escapeHtml(check.end)}</span></td>
        <td>${check.limitDays}d</td>
        <td>${check.v2ObserveTotalDays} / ${check.v2ObserveMaxDays}</td>
        <td>${check.v3ObserveTotalDays} / ${check.v3ObserveMaxDays}</td>
        <td>${check.v3Pass ? "pass" : "fail"}</td>
      </tr>
    </tbody>
  `;
}

function renderObserveReport(observe) {
  if (!observe) return;
  $("observeSummary").innerHTML = `
    <div class="metric"><span>발생 횟수</span><strong>${observe.summary.occurrences}</strong></div>
    <div class="metric"><span>총 일수</span><strong>${observe.summary.totalDays}</strong></div>
    <div class="metric"><span>평균 지속일</span><strong>${number(observe.summary.averageDays, 1)}</strong></div>
    <div class="metric"><span>최대 지속일</span><strong>${observe.summary.maxDays}</strong></div>
  `;
  $("observeLongTable").innerHTML = `
    <thead>
      <tr><th>시작</th><th>종료</th><th>일수</th><th>이전 레짐</th><th>다음 레짐</th></tr>
    </thead>
    <tbody>
      ${observe.summary.longSegments.length ? observe.summary.longSegments.map((row) => `
        <tr>
          <td>${escapeHtml(row.start)}</td>
          <td>${escapeHtml(row.end)}</td>
          <td>${row.days}</td>
          <td>${regimeLabel(row.previousRegime)}</td>
          <td>${regimeLabel(row.nextRegime)}</td>
        </tr>
      `).join("") : `<tr><td colspan="5">10일 이상 observe 구간 없음</td></tr>`}
    </tbody>
  `;
  $("observeTransitions").innerHTML = `
    <div class="metric"><span>이전 레짐 복귀</span><strong>${observe.transitions.returnToPrevious}</strong></div>
    <div class="metric"><span>하락장 전환</span><strong>${observe.transitions.toBear}</strong></div>
    <div class="metric"><span>uptrend/lead/strength</span><strong>${observe.transitions.toGrowth}</strong></div>
    <div class="metric"><span>다시 위험장</span><strong>${observe.transitions.toRisk}</strong></div>
  `;
  $("observeTransitionTable").innerHTML = `
    <thead>
      <tr><th>시작</th><th>종료</th><th>일수</th><th>이전 레짐</th><th>다음 레짐</th><th>분류</th></tr>
    </thead>
    <tbody>
      ${observe.transitions.rows.slice(-12).map((row) => `
        <tr>
          <td>${escapeHtml(row.start)}</td>
          <td>${escapeHtml(row.end)}</td>
          <td>${row.days}</td>
          <td>${regimeLabel(row.previousRegime)}</td>
          <td>${regimeLabel(row.nextRegime)}</td>
          <td>${escapeHtml(transitionLabel(row.category))}</td>
        </tr>
      `).join("")}
    </tbody>
  `;
  $("observePerformance").innerHTML = `
    <div class="metric"><span>BTC 평균</span><strong>${pct(observe.performance.btcAverageDailyReturn)}</strong></div>
    <div class="metric"><span>ETH 평균</span><strong>${pct(observe.performance.ethAverageDailyReturn)}</strong></div>
    <div class="metric"><span>알트 평균</span><strong>${pct(observe.performance.altAverageDailyReturn)}</strong></div>
    <div class="metric"><span>MDD</span><strong>${ratio(observe.performance.maxDrawdown)}</strong></div>
  `;
  $("observeEventTable").innerHTML = `
    <thead>
      <tr><th>이벤트</th><th>Observe 일수</th><th>시작</th><th>종료</th></tr>
    </thead>
    <tbody>
      ${observe.eventObserve.map((row) => `
        <tr>
          <td><strong>${escapeHtml(row.event)}</strong><span>${escapeHtml(row.start)} - ${escapeHtml(row.end)}</span></td>
          <td>${row.observeDays}</td>
          <td>${row.observeStart ? escapeHtml(row.observeStart) : "-"}</td>
          <td>${row.observeEnd ? escapeHtml(row.observeEnd) : "-"}</td>
        </tr>
      `).join("")}
    </tbody>
  `;
}

function regimeName(row) {
  return `<span class="table-regime"><span class="swatch" style="background:${row.color}"></span>${escapeHtml(row.label)}</span>`;
}

function regimeLabel(regime) {
  if (!regime || !state.payload.regimes[regime]) return "-";
  const item = state.payload.regimes[regime];
  return `<span class="table-regime"><span class="swatch" style="background:${item.color}"></span>${escapeHtml(item.label)}</span>`;
}

function mixLabel(items) {
  if (!items || !items.length) return "-";
  return items
    .slice(0, 3)
    .map((item) => `${regimeLabel(item.regime)} ${item.days}d`)
    .join(" ");
}

function delayDays(value) {
  return value === null || value === undefined ? "-" : `${value}d`;
}

function transitionLabel(value) {
  const labels = {
    return_to_previous: "이전 복귀",
    to_bear: "하락 전환",
    to_growth: "uptrend/lead/strength",
    to_risk: "재위험",
    to_other: "기타",
  };
  return labels[value] || value || "-";
}

function assetLabel(value) {
  const labels = {
    btc: "BTC",
    eth: "ETH",
    alt: "상위 알트",
    cash: "현금",
  };
  return labels[value] || "-";
}

function benchmarkStatusLabel(value) {
  const labels = {
    pass: "pass",
    fail: "fail",
    warning: "warning",
    no_data: "no data",
  };
  return labels[value] || value || "-";
}

function drawRegimeOverlay() {
  const overlay = $("regimeOverlay");
  if (!state.chart || !state.payload || !overlay.clientWidth) return;
  const range = state.chart.timeScale().getVisibleRange();
  overlay.innerHTML = "";
  if (!range) return;
  const width = overlay.clientWidth;
  const rangeWidth = Math.max(1, range.to - range.from);

  for (const segment of state.payload.segments) {
    const from = Math.max(segment.from, range.from);
    const to = Math.min(segment.to, range.to);
    if (to <= from) continue;
    const left = timeToX(from, range, rangeWidth, width);
    const right = timeToX(to, range, rangeWidth, width);
    const element = document.createElement("div");
    element.style.left = `${Math.max(0, left)}px`;
    element.style.width = `${Math.max(1, right - left)}px`;
    element.style.background = segment.color;
    overlay.appendChild(element);
  }
}

function timeToX(time, range, rangeWidth, width) {
  const direct = state.chart.timeScale().timeToCoordinate(time);
  if (direct !== null && direct !== undefined) return direct;
  return ((time - range.from) / rangeWidth) * width;
}

function normalizeTime(value) {
  if (typeof value === "number") return value;
  if (value && typeof value === "object" && "year" in value) {
    return Math.floor(Date.UTC(value.year, value.month - 1, value.day) / 1000);
  }
  return Number(value);
}

function nearestPoint(time) {
  const exact = state.pointsByTime.get(String(time));
  if (exact) return exact;
  const points = state.payload.points;
  let left = 0;
  let right = points.length - 1;
  while (left <= right) {
    const mid = Math.floor((left + right) / 2);
    if (points[mid].time < time) left = mid + 1;
    else right = mid - 1;
  }
  const before = points[Math.max(0, right)];
  const after = points[Math.min(points.length - 1, left)];
  if (!before) return after;
  if (!after) return before;
  return Math.abs(before.time - time) <= Math.abs(after.time - time) ? before : after;
}

$("controls").addEventListener("submit", (event) => {
  event.preventDefault();
  loadData(true);
});

if (window.lucide) window.lucide.createIcons();
loadData(false);
