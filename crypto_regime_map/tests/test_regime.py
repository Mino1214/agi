import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from indicators import ema  # noqa: E402
from policy_backtest import (  # noqa: E402
    build_alt_universe_robustness_report,
    build_eth_strength_sensitivity_report,
    build_hybrid_overlay_challenge_report,
    build_overlay_ablation_report,
    build_policy_backtest_audit_report,
    build_policy_backtest_report,
    build_risk_normalized_comparison_report,
    build_simple_baseline_challenge_report,
)
from regime import DEFAULT_SYMBOLS, REGIMES, build_payload_from_raw, classify, stabilize_regimes  # noqa: E402
from validation import build_validation_report  # noqa: E402

UPTREND = "uptrend"
LARGE_CAP_LEAD = "large_cap_lead"
ETH_STRENGTH = "eth_strength"
DEFENSIVE = "defensive"
SHOCK = "shock"
NEUTRAL = "neutral"
OBSERVE = "observe"


class IndicatorTests(unittest.TestCase):
    def test_ema_starts_after_period(self):
        values = [1, 2, 3, 4, 5]
        result = ema(values, 3)
        self.assertEqual(result[:2], [None, None])
        self.assertEqual(result[2], 2)
        self.assertAlmostEqual(result[-1], 4.0)


class RegimeTests(unittest.TestCase):
    def test_risk_takes_priority(self):
        row = {
            "close": 100,
            "ema50": 120,
            "ema200": 130,
            "return": -0.08,
            "return_3d": -0.13,
            "atr_pct": 0.06,
            "atr_pct_sma20": 0.03,
            "atr_pct_sma50": 0.03,
            "volume": 200,
            "volume_sma20": 100,
            "alt_up_ratio": 0.2,
        }
        self.assertEqual(classify(row), SHOCK)

    def test_risk_v2_requires_two_conditions(self):
        row = {
            "close": 100,
            "ema50": 120,
            "ema200": 130,
            "return": -0.08,
            "return_3d": -0.05,
            "atr_pct": 0.03,
            "atr_pct_sma20": 0.03,
            "atr_pct_sma50": 0.03,
            "volume": 100,
            "volume_sma20": 100,
            "alt_up_ratio": 0.6,
        }
        self.assertEqual(classify(row), DEFENSIVE)

    def test_bear_when_btc_under_ema200(self):
        row = {
            "close": 90,
            "ema50": 95,
            "ema200": 100,
            "return": -0.01,
            "atr_pct": 0.03,
            "atr_pct_sma50": 0.03,
            "volume": 100,
            "volume_sma20": 100,
        }
        self.assertEqual(classify(row), DEFENSIVE)

    def test_alt_requires_eth_btc_and_alt_strength(self):
        row = {
            "close": 120,
            "ema50": 110,
            "ema200": 100,
            "return": 0.01,
            "atr_pct": 0.03,
            "atr_pct_sma50": 0.03,
            "volume": 100,
            "volume_sma20": 100,
            "eth_btc": 0.06,
            "eth_btc_ema50": 0.055,
            "eth_btc_ema200": 0.05,
            "alt_up_ratio": 0.75,
        }
        self.assertEqual(classify(row), ETH_STRENGTH)


class LookaheadTests(unittest.TestCase):
    def test_prefix_payload_matches_full_payload_for_same_date(self):
        raw = make_synthetic_market(days=260)
        full = build_payload_from_raw(raw, symbols=DEFAULT_SYMBOLS)

        for size in (210, 230, 260):
            prefix_raw = {symbol: candles[:size] for symbol, candles in raw.items()}
            prefix = build_payload_from_raw(prefix_raw, symbols=DEFAULT_SYMBOLS)
            self.assertEqual(prefix["points"][-1]["time"], full["points"][size - 1]["time"])
            self.assertEqual(prefix["points"][-1]["raw_regime"], full["points"][size - 1]["raw_regime"])
            self.assertEqual(prefix["points"][-1]["stable_regime"], full["points"][size - 1]["stable_regime"])
            self.assertEqual(prefix["points"][-1]["regime"], full["points"][size - 1]["regime"])
            self.assertEqual(prefix["points"][-1]["trade_regime"], full["points"][size - 1]["trade_regime"])

    def test_trade_regime_is_previous_confirmed_regime(self):
        payload = build_payload_from_raw(make_synthetic_market(days=230), symbols=DEFAULT_SYMBOLS)
        self.assertIsNone(payload["points"][0]["trade_regime"])
        for index in range(1, len(payload["points"])):
            self.assertEqual(payload["points"][index]["trade_regime"], payload["points"][index - 1]["stable_regime"])


class StabilizationTests(unittest.TestCase):
    def test_new_regime_must_persist_five_days(self):
        points = make_points([NEUTRAL] * 5 + [ETH_STRENGTH] * 4)
        stabilize_regimes(points)
        self.assertEqual(points[-1]["stable_regime"], NEUTRAL)

        points = make_points([NEUTRAL] * 5 + [ETH_STRENGTH] * 5)
        stabilize_regimes(points)
        self.assertEqual(points[-1]["stable_regime"], ETH_STRENGTH)

    def test_risk_switches_immediately_then_enters_observe(self):
        points = make_points([NEUTRAL, NEUTRAL, SHOCK, NEUTRAL])
        stabilize_regimes(points)
        self.assertEqual(points[2]["stable_regime"], SHOCK)
        self.assertEqual(points[3]["stable_regime"], OBSERVE)

    def test_observe_recovers_after_three_days_above_ema50(self):
        points = make_points([NEUTRAL, SHOCK, NEUTRAL, NEUTRAL, NEUTRAL], close=120, ema50=100)
        stabilize_regimes(points)
        self.assertEqual(points[2]["stable_regime"], OBSERVE)
        self.assertEqual(points[3]["stable_regime"], OBSERVE)
        self.assertEqual(points[4]["stable_regime"], NEUTRAL)

    def test_observe_breaks_down_to_bear_after_three_days(self):
        points = make_points([UPTREND, SHOCK, NEUTRAL, NEUTRAL, NEUTRAL], close=90, ema50=100)
        for point in points:
            point["ema50_slope"] = -0.01
        stabilize_regimes(points)
        self.assertEqual(points[4]["stable_regime"], DEFENSIVE)

    def test_observe_forces_reclassification_after_seven_days(self):
        cases = [
            (DEFENSIVE, 90, None, None),
            (ETH_STRENGTH, 103, 0.06, 0.05),
            (LARGE_CAP_LEAD, 103, 0.04, 0.05),
            (UPTREND, 101, None, None),
            (NEUTRAL, 100, None, None),
        ]
        for expected, close, eth_btc, eth_ema50 in cases:
            with self.subTest(expected=expected):
                points = make_points([UPTREND, SHOCK] + [NEUTRAL] * 8, close=close, ema200=100, ema50=110)
                for point in points:
                    point["eth_btc"] = eth_btc
                    point["eth_btc_ema50"] = eth_ema50
                stabilize_regimes(points)

                self.assertEqual(max_regime_run(points, OBSERVE), 7)
                self.assertEqual(points[-1]["stable_regime"], expected)

    def test_observe_limit_can_be_disabled_for_v2(self):
        points = make_points([UPTREND, SHOCK] + [NEUTRAL] * 8, close=100, ema200=100, ema50=110)
        stabilize_regimes(points, observe_limit_days=None)

        self.assertEqual(max_regime_run(points, OBSERVE), 8)
        self.assertEqual(points[-1]["stable_regime"], OBSERVE)

    def test_bull_hysteresis_blocks_weak_entry_and_slow_exit(self):
        weak_entry = make_points([NEUTRAL, UPTREND], close=101, ema200=100, ema50=102)
        stabilize_regimes(weak_entry)
        self.assertEqual(weak_entry[-1]["stable_regime"], NEUTRAL)

        slow_exit = [
            {"time": 1577836800, "close": 120, "ema200": 100, "ema50": 110, "raw_regime": UPTREND},
            {"time": 1577923200, "close": 100, "ema200": 100, "ema50": 110, "raw_regime": NEUTRAL},
        ]
        stabilize_regimes(slow_exit)
        self.assertEqual(slow_exit[-1]["stable_regime"], UPTREND)


class ObserveReportTests(unittest.TestCase):
    def test_observe_report_counts_long_segments_and_transitions(self):
        points = make_report_points([UPTREND, SHOCK] + [OBSERVE] * 11 + [DEFENSIVE])
        report = build_validation_report({"points": points, "regimes": REGIMES})
        observe = report["observe"]

        self.assertEqual(observe["summary"]["occurrences"], 1)
        self.assertEqual(observe["summary"]["totalDays"], 11)
        self.assertEqual(observe["summary"]["maxDays"], 11)
        self.assertEqual(len(observe["summary"]["longSegments"]), 1)
        self.assertEqual(observe["transitions"]["toBear"], 1)
        self.assertEqual(observe["transitions"]["returnToPrevious"], 0)

    def test_event_observe_days_after_first_risk(self):
        points = make_report_points(
            [UPTREND] * 11 + [SHOCK] + [OBSERVE] * 3 + [DEFENSIVE],
            start=1619827200,
        )
        report = build_validation_report({"points": points, "regimes": REGIMES})
        row = next(item for item in report["observe"]["eventObserve"] if item["event"] == "2021-05 폭락")

        self.assertEqual(row["observeDays"], 3)
        self.assertEqual(row["observeStart"], "2021-05-13")

    def test_v2_v3_comparison_checks_observe_limit_window(self):
        points = make_dual_report_points(
            [OBSERVE] * 10,
            [OBSERVE] * 7 + [UPTREND] * 3,
            start=1614297600,
        )
        report = build_validation_report({"points": points, "regimes": REGIMES})
        comparison = report["v2v3Comparison"]
        check = comparison["observeLimitCheck"]

        self.assertEqual(comparison["summary"][0]["observeMaxDays"], 10)
        self.assertEqual(comparison["summary"][1]["observeMaxDays"], 7)
        self.assertTrue(check["v3Pass"])
        self.assertEqual(check["v3ObserveMaxDays"], 7)


class BenchmarkReportTests(unittest.TestCase):
    def test_benchmark_report_validates_regime_names_for_stable_and_trade(self):
        points = make_benchmark_points(
            [
                (ETH_STRENGTH, None, 0.0, 0.0, 0.0),
                (LARGE_CAP_LEAD, ETH_STRENGTH, 0.04, 0.03, 0.01),
                (SHOCK, LARGE_CAP_LEAD, 0.03, 0.01, 0.01),
                (DEFENSIVE, SHOCK, 0.01, 0.02, 0.0),
                (NEUTRAL, DEFENSIVE, 0.01, -0.01, -0.01),
            ]
        )
        report = build_validation_report({"points": points, "regimes": REGIMES})
        stable = {row["regime"]: row for row in report["benchmarkReport"]["stable"]["rows"]}
        trade = {row["regime"]: row for row in report["benchmarkReport"]["trade"]["rows"]}

        self.assertEqual(report["benchmarkReport"]["stable"]["basis"], "previous_stable_regime")
        self.assertEqual(report["benchmarkReport"]["trade"]["basis"], "same_bar_trade_regime")
        self.assertEqual(stable[ETH_STRENGTH]["validationStatus"], "warning")
        self.assertEqual(stable[ETH_STRENGTH]["bestAsset"], "btc")
        self.assertEqual(stable[LARGE_CAP_LEAD]["validationStatus"], "pass")
        self.assertEqual(stable[SHOCK]["validationStatus"], "warning")
        self.assertEqual(stable[DEFENSIVE]["validationStatus"], "warning")
        self.assertEqual(trade[ETH_STRENGTH]["validationStatus"], "warning")
        self.assertEqual(trade[SHOCK]["bestAsset"], "eth")

    def test_bear_benchmark_marks_cash_and_short_need_when_all_holds_lose(self):
        points = make_benchmark_points(
            [
                (DEFENSIVE, None, 0.0, 0.0, 0.0),
                (DEFENSIVE, DEFENSIVE, -0.05, -0.04, -0.06),
            ]
        )
        report = build_validation_report({"points": points, "regimes": REGIMES})
        bear = next(row for row in report["benchmarkReport"]["stable"]["rows"] if row["regime"] == DEFENSIVE)

        self.assertEqual(bear["bestAsset"], "cash")
        self.assertTrue(bear["cashWasBest"])
        self.assertTrue(bear["shortNeeded"])
        self.assertEqual(bear["validationStatus"], "pass")

    def test_action_bias_performance_groups_regime_returns(self):
        points = make_benchmark_points(
            [
                (UPTREND, None, 0.0, 0.0, 0.0),
                (UPTREND, UPTREND, 0.02, 0.03, 0.01),
                (DEFENSIVE, UPTREND, -0.01, -0.02, -0.03),
            ]
        )
        report = build_validation_report({"points": points, "regimes": REGIMES})
        stable = {row["actionBias"]: row for row in report["actionBiasPerformance"]["stable"]["rows"]}

        self.assertIn("long_allowed", stable)
        self.assertEqual(stable["long_allowed"]["regimes"], [UPTREND])
        self.assertEqual(stable["long_allowed"]["days"], 2)
        self.assertEqual(stable["long_allowed"]["bestAsset"], "btc")


class LabelRevalidationReportTests(unittest.TestCase):
    def test_label_revalidation_report_outputs_failure_causes_and_candidates(self):
        points = make_label_points(
            [
                (ETH_STRENGTH, None, 0.0, 0.0, 0.0, 100, 90, 0.06, 0.05, 0.04),
                (LARGE_CAP_LEAD, ETH_STRENGTH, 0.02, 0.01, 0.00, 102, 90, 0.06, 0.05, 0.04),
                (DEFENSIVE, LARGE_CAP_LEAD, 0.01, 0.03, 0.04, 103, 90, 0.04, 0.05, 0.04),
                (SHOCK, DEFENSIVE, 0.02, 0.00, -0.01, 120, 100, 0.04, 0.05, 0.04),
                (NEUTRAL, SHOCK, 0.00, 0.03, 0.00, 121, 100, 0.04, 0.05, 0.04),
            ]
        )
        report = build_validation_report({"points": points, "regimes": REGIMES})
        stable = report["labelRevalidationReport"]["stable"]
        trade = report["labelRevalidationReport"]["trade"]
        candidates = {row["regime"]: row for row in stable["candidates"]}

        self.assertEqual(stable["largeCapLead"]["bestAsset"], "alt")
        self.assertEqual(stable["largeCapLead"]["nonWinningDays"], 1)
        self.assertEqual(stable["largeCapLead"]["nonWinningSegments"][0]["bestRiskAsset"], "alt")
        self.assertEqual(stable["ethStrength"]["weakerThanBtcDays"], 1)
        self.assertEqual(stable["ethStrength"]["ethBtcStrengthCheck"]["status"], "fail")
        self.assertEqual(stable["defensive"]["holdingAdvantageDays"], 1)
        self.assertEqual(stable["defensive"]["reboundDays"], 1)
        self.assertEqual(stable["shock"]["holdingAdvantageDays"], 1)
        self.assertEqual(candidates[LARGE_CAP_LEAD]["candidate"], "large_cap_lead")
        self.assertEqual(candidates[ETH_STRENGTH]["candidate"], "eth_strength")
        self.assertEqual(candidates[DEFENSIVE]["candidate"], "defensive")
        self.assertEqual(candidates[SHOCK]["candidate"], "shock")
        self.assertEqual(candidates[LARGE_CAP_LEAD]["recommendation"], "recommended")
        self.assertEqual(trade["largeCapLead"]["nonWinningDays"], 1)
        self.assertEqual(trade["ethStrength"]["ethBtcStrengthCheck"]["status"], "fail")

    def test_label_migration_report_outputs_v4_mapping_and_action_bias(self):
        report = build_validation_report({"points": [], "regimes": REGIMES, "regimeLabelMigration": [
            {"legacy": "btc", "legacyLabel": "BTC 중심장", "regime": LARGE_CAP_LEAD, "label": LARGE_CAP_LEAD},
            {"legacy": "risk", "legacyLabel": "위험장", "regime": SHOCK, "label": SHOCK},
        ]})
        rows = {row["legacy"]: row for row in report["labelMigrationReport"]["rows"]}

        self.assertEqual(report["labelMigrationReport"]["version"], "v4")
        self.assertEqual(rows["btc"]["regime"], LARGE_CAP_LEAD)
        self.assertEqual(rows["btc"]["actionBias"], "btc_eth_preferred")
        self.assertEqual(rows["risk"]["regime"], SHOCK)
        self.assertEqual(rows["risk"]["actionBias"], "no_new_entry")


class PolicyBacktestTests(unittest.TestCase):
    def test_policy_uses_trade_action_bias_and_next_bar_returns(self):
        points = make_policy_points(
            [
                (DEFENSIVE, UPTREND, "long_allowed", 0.00, 0.00, 0.00, 8),
                (UPTREND, DEFENSIVE, "wait", 0.10, 0.00, 0.00, 8),
                (UPTREND, DEFENSIVE, "wait", 0.10, 0.00, 0.00, 8),
            ]
        )
        report = build_policy_backtest_report({"points": points, "regimes": REGIMES}, fee_rate=0.0, slippage_rate=0.0)
        policy_a = next(row for row in report["defaultRun"]["rows"] if row["id"] == "policy_a_conservative")

        self.assertAlmostEqual(policy_a["totalReturn"], 0.05)
        self.assertEqual(report["config"]["signal"], "trade_action_bias[i] / trade_regime[i]")
        self.assertFalse(report["config"]["stableRegimeDirectUse"])

    def test_policy_backtest_outputs_cost_turnover_and_comparisons(self):
        points = make_policy_points(
            [
                (UPTREND, UPTREND, "long_allowed", 0.00, 0.00, 0.00, 8),
                (UPTREND, UPTREND, "long_allowed", 0.02, 0.01, 0.03, 8),
                (DEFENSIVE, DEFENSIVE, "reduce_risk", -0.04, -0.05, -0.06, 8),
                (UPTREND, UPTREND, "long_allowed", 0.03, 0.02, 0.04, 8),
            ]
        )
        report = build_policy_backtest_report({"points": points, "regimes": REGIMES})
        policy_a = next(row for row in report["defaultRun"]["rows"] if row["id"] == "policy_a_conservative")
        benchmark_ids = {row["id"] for row in report["benchmarks"]}

        self.assertIn("btc_buy_hold", benchmark_ids)
        self.assertIn("btc_eth_50_50", benchmark_ids)
        self.assertEqual([row["label"] for row in report["costSensitivity"]], ["0.0%", "0.1%", "0.2%"])
        self.assertEqual([row["rebalance"] for row in report["rebalanceComparison"]], ["daily", "weekly", "regime_change"])
        self.assertGreater(policy_a["turnover"], 0)
        self.assertGreater(policy_a["totalTradingCost"], 0)
        self.assertIn(policy_a["mddReducedVsBtcStatus"], {"pass", "fail"})
        self.assertTrue(policy_a["monthlyReturns"])
        self.assertTrue(policy_a["yearlyReturns"])

    def test_alt_weight_stays_cash_before_alt_data_exists(self):
        points = make_policy_points(
            [
                (ETH_STRENGTH, ETH_STRENGTH, "alt_watch", 0.00, 0.00, 0.00, 0),
                (ETH_STRENGTH, ETH_STRENGTH, "alt_watch", 0.00, 0.00, 0.50, 0),
            ]
        )
        report = build_policy_backtest_report({"points": points, "regimes": REGIMES}, fee_rate=0.0, slippage_rate=0.0)
        policy_b = next(row for row in report["defaultRun"]["rows"] if row["id"] == "policy_b_balanced")

        self.assertAlmostEqual(policy_b["totalReturn"], 0.0)

    def test_policy_backtest_audit_outputs_universe_timing_and_oos(self):
        rows = []
        regimes = [UPTREND, DEFENSIVE, ETH_STRENGTH, LARGE_CAP_LEAD]
        for index in range(40):
            stable = regimes[index % len(regimes)]
            trade = regimes[(index - 1) % len(regimes)] if index > 0 else None
            action = REGIMES[trade]["action_bias"] if trade else None
            rows.append((stable, trade, action, 0.01, 0.008, 0.012, 4))
        points = make_policy_points(rows, start=1777420800)
        payload = {
            "points": points,
            "regimes": REGIMES,
            "symbolData": [
                {"symbol": "BTCUSDT", "start": points[0]["time"], "end": points[-1]["time"], "days": len(points)},
                {"symbol": "ETHUSDT", "start": points[0]["time"], "end": points[-1]["time"], "days": len(points)},
                {"symbol": "SOLUSDT", "start": points[0]["time"], "end": points[-1]["time"], "days": len(points)},
            ],
        }
        audit = build_policy_backtest_audit_report(payload)

        self.assertEqual(len(audit["benchmarkDetailedComparison"]), 8)
        self.assertTrue(audit["universeAudit"]["symbolStartRows"])
        self.assertEqual(len(audit["universeAudit"]["sensitivity"]["rows"]), 15)
        self.assertEqual({row["status"] for row in audit["executionTiming"]["checks"]}, {"pass"})
        self.assertGreater(audit["oos"]["oos"]["days"], 0)
        self.assertTrue(audit["oos"]["oos"]["daily"])
        self.assertEqual(len(audit["passFail"]), 3)

    def test_simple_baseline_and_risk_normalized_reports_are_built(self):
        rows = []
        regimes = [UPTREND, DEFENSIVE, ETH_STRENGTH, LARGE_CAP_LEAD]
        for index in range(130):
            stable = regimes[index % len(regimes)]
            trade = regimes[(index - 1) % len(regimes)] if index > 0 else None
            action = REGIMES[trade]["action_bias"] if trade else None
            btc_return = 0.01 if index % 5 else -0.005
            rows.append((stable, trade, action, btc_return, 0.008, 0.012, 4))
        points = make_policy_points(rows)
        for point in points:
            point["ema200"] = 95
            point["ema50"] = 105
            point["eth_btc"] = 0.06
            point["eth_btc_ema50"] = 0.055
        payload = {"points": points, "regimes": REGIMES}
        policy_report = build_policy_backtest_report(payload)
        simple = build_simple_baseline_challenge_report(payload, policy_report)
        risk = build_risk_normalized_comparison_report(payload, policy_report, simple)

        self.assertEqual(len(simple["simpleStrategyRows"]), 7)
        self.assertEqual(len(simple["comparisonRows"]), 15)
        self.assertTrue(simple["passFail"]["checks"])
        self.assertTrue(risk["sameVolatilityRows"])
        self.assertTrue(risk["sameDrawdownRows"])
        self.assertTrue(risk["policyLeverageRows"])
        self.assertEqual({row["name"] for row in risk["winners"]}, {
            "raw_return",
            "sharpe",
            "calmar",
            "same_volatility_cagr",
            "same_drawdown_cagr",
        })

    def test_hybrid_overlay_and_robustness_reports_are_built(self):
        rows = []
        regimes = [UPTREND, DEFENSIVE, ETH_STRENGTH, LARGE_CAP_LEAD, SHOCK, NEUTRAL]
        for index in range(140):
            stable = regimes[index % len(regimes)]
            trade = regimes[(index - 1) % len(regimes)] if index > 0 else None
            action = REGIMES[trade]["action_bias"] if trade else None
            btc_return = 0.012 if stable not in {SHOCK, DEFENSIVE} else -0.006
            eth_return = 0.010 if stable != SHOCK else -0.008
            alt_return = 0.014 if stable in {ETH_STRENGTH, UPTREND} else -0.004
            rows.append((stable, trade, action, btc_return, eth_return, alt_return, 5))
        points = make_policy_points(rows)
        for index, point in enumerate(points):
            point["ema200"] = 95
            point["ema50"] = 105 if index % 17 else 90
            point["eth_btc"] = 0.05 + index * 0.0001
            point["eth_btc_ema50"] = 0.049 + index * 0.00005
            point["eth_btc_ema200"] = 0.048
        payload = {"points": points, "regimes": REGIMES}
        simple = build_simple_baseline_challenge_report(payload)
        hybrid = build_hybrid_overlay_challenge_report(payload, simple)
        ablation = build_overlay_ablation_report(payload)
        eth_strength = build_eth_strength_sensitivity_report(payload)
        robustness = build_alt_universe_robustness_report(payload)

        self.assertEqual(len(hybrid["baseRows"]), 5)
        self.assertEqual(len(hybrid["hybridRows"]), 5)
        self.assertEqual(len(hybrid["passFail"]), 5)
        self.assertEqual(len(ablation["rows"]), 25)
        self.assertEqual(len(eth_strength["rows"]), 6)
        self.assertIn(eth_strength["passFail"]["status"], {"pass", "warning"})
        self.assertEqual(len(robustness["leaveOneOut"]), 8)
        self.assertEqual(len(robustness["minCountRows"]), 3)
        self.assertTrue(robustness["warnings"])


def make_synthetic_market(days):
    start = 1577836800
    raw = {}
    for symbol_index, symbol in enumerate(DEFAULT_SYMBOLS):
        price = 100 + symbol_index * 11
        candles = []
        for day in range(days):
            if day < 85:
                drift = 0.003
            elif day < 160:
                drift = -0.0025
            else:
                drift = 0.0015
            wave = ((day % 11) - 5) * 0.0007
            symbol_tilt = (symbol_index - 4) * 0.00015
            daily_return = drift + wave + symbol_tilt
            open_price = price
            close = price * (1 + daily_return)
            high = max(open_price, close) * 1.012
            low = min(open_price, close) * 0.988
            candles.append(
                {
                    "time": start + day * 24 * 60 * 60,
                    "open": open_price,
                    "high": high,
                    "low": low,
                    "close": close,
                    "volume": 1000 + day * 4 + symbol_index * 20,
                }
            )
            price = close
        raw[symbol] = candles
    return raw


def make_points(regimes, close=120, ema200=100, ema50=110):
    return [
        {
            "time": 1577836800 + index * 24 * 60 * 60,
            "close": close,
            "ema200": ema200,
            "ema50": ema50,
            "ema50_slope": 0.01,
            "raw_regime": regime,
        }
        for index, regime in enumerate(regimes)
    ]


def make_report_points(regimes, start=1577836800):
    points = []
    for index, regime in enumerate(regimes):
        previous = regimes[index - 1] if index > 0 else None
        points.append(
            {
                "time": start + index * 24 * 60 * 60,
                "return": 0.01 if regime not in {SHOCK, OBSERVE} else -0.01,
                "eth_return": 0.008 if regime not in {SHOCK, OBSERVE} else -0.012,
                "alt_average_return": 0.009 if regime not in {SHOCK, OBSERVE} else -0.015,
                "raw_regime": regime,
                "stable_regime": regime,
                "trade_regime": previous,
            }
        )
    return points


def make_dual_report_points(v2_regimes, v3_regimes, start=1577836800):
    points = []
    for index, (v2_regime, v3_regime) in enumerate(zip(v2_regimes, v3_regimes)):
        points.append(
            {
                "time": start + index * 24 * 60 * 60,
                "return": 0.01 if v3_regime not in {SHOCK, OBSERVE} else -0.01,
                "eth_return": 0.008 if v3_regime not in {SHOCK, OBSERVE} else -0.012,
                "alt_average_return": 0.009 if v3_regime not in {SHOCK, OBSERVE} else -0.015,
                "raw_regime": v3_regime,
                "v2_stable_regime": v2_regime,
                "v2_trade_regime": v2_regimes[index - 1] if index > 0 else None,
                "stable_regime": v3_regime,
                "trade_regime": v3_regimes[index - 1] if index > 0 else None,
            }
        )
    return points


def make_benchmark_points(rows, start=1577836800):
    points = []
    for index, (stable_regime, trade_regime, btc_return, eth_return, alt_return) in enumerate(rows):
        points.append(
            {
                "time": start + index * 24 * 60 * 60,
                "return": btc_return,
                "eth_return": eth_return,
                "alt_average_return": alt_return,
                "raw_regime": stable_regime,
                "stable_regime": stable_regime,
                "trade_regime": trade_regime,
            }
        )
    return points


def make_label_points(rows, start=1577836800):
    points = []
    for index, (
        stable_regime,
        trade_regime,
        btc_return,
        eth_return,
        alt_return,
        close,
        ema50,
        eth_btc,
        eth_btc_ema50,
        eth_btc_ema200,
    ) in enumerate(rows):
        points.append(
            {
                "time": start + index * 24 * 60 * 60,
                "close": close,
                "ema50": ema50,
                "eth_btc": eth_btc,
                "eth_btc_ema50": eth_btc_ema50,
                "eth_btc_ema200": eth_btc_ema200,
                "return": btc_return,
                "eth_return": eth_return,
                "alt_average_return": alt_return,
                "raw_regime": stable_regime,
                "stable_regime": stable_regime,
                "trade_regime": trade_regime,
            }
        )
    return points


def make_policy_points(rows, start=1577836800):
    points = []
    alt_symbols = ["SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "LINKUSDT", "AVAXUSDT", "ADAUSDT", "TONUSDT"]
    for index, (stable_regime, trade_regime, trade_action_bias, btc_return, eth_return, alt_return, alt_count) in enumerate(rows):
        included_alts = alt_symbols[:alt_count]
        alt_returns = {symbol: alt_return for symbol in included_alts}
        points.append(
            {
                "time": start + index * 24 * 60 * 60,
                "open": 100,
                "close": 100 * (1 + btc_return),
                "return": btc_return,
                "eth_return": eth_return,
                "eth_open_close_return": eth_return,
                "alt_average_return": alt_return,
                "alt_average_open_close_return": alt_return,
                "alt_count": alt_count,
                "alt_symbols": included_alts,
                "alt_returns": alt_returns,
                "alt_open_close_returns": dict(alt_returns),
                "raw_regime": stable_regime,
                "stable_regime": stable_regime,
                "stable_action_bias": REGIMES[stable_regime]["action_bias"],
                "trade_regime": trade_regime,
                "trade_action_bias": trade_action_bias,
            }
        )
    return points


def max_regime_run(points, regime, key="stable_regime"):
    longest = 0
    current = 0
    for point in points:
        if point.get(key) == regime:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


if __name__ == "__main__":
    unittest.main()
