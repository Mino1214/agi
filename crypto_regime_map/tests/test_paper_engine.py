import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import alpha_engine_v1_2_paper_engine as paper  # noqa: E402
import alpha_engine_v1_2_4h_regime as short_regime_4h  # noqa: E402
import alpha_engine_v1_2_defensive_probe as defensive_probe_rules  # noqa: E402


class PaperSignalSelectionTests(unittest.TestCase):
    def test_v1_2_filter_excludes_doge_and_selects_top_20pct(self):
        signals = [
            make_signal("BTC", 9.0, 1),
            make_signal("ETH", 8.0, 2),
            make_signal("SOL", 7.0, 3),
            make_signal("BNB", 6.5, 4),
            make_signal("XRP", 6.0, 5),
            make_signal("DOGE", 10.0, 1),
            make_signal("LINK", 8.5, 2, regime_reason="defensive_reduce_risk"),
        ]

        rows, selected = paper.select_v1_2_signal_batch(signals)

        self.assertEqual([item["symbol"] for item in selected], ["BTCUSDT"])
        doge = next(row for row in rows if row["symbol"] == "DOGEUSDT")
        defensive = next(row for row in rows if row["symbol"] == "LINKUSDT")
        eth = next(row for row in rows if row["symbol"] == "ETHUSDT")
        self.assertEqual(doge["rejection_reason"], "doge_excluded")
        self.assertEqual(defensive["rejection_reason"], "defensive_no_entry")
        self.assertEqual(eth["rejection_reason"], "alpha_score_not_top_20pct")

    def test_scan_signal_batch_records_all_non_doge_symbols(self):
        signal_time = 1767240000
        open_time = signal_time - 4 * 3600
        rows = {}
        for index, symbol in enumerate(paper.TRADING_UNIVERSE):
            rows[symbol] = make_4h_row(open_time, trend_ok=symbol in {"ETHUSDT", "SOLUSDT"}, strength=10 - index)
        data = SimpleNamespace(
            by_time_4h={symbol: {open_time: row} for symbol, row in rows.items()},
            regime_by_date={
                paper.alpha.date_from_ts(signal_time): {
                    "trade_regime": "defensive",
                    "trade_action_bias": "reduce_risk",
                }
            },
        )

        scan_rows, selected = paper.build_scan_signal_batch(data, signal_time)

        self.assertEqual(len(scan_rows), 9)
        self.assertEqual({row["symbol"] for row in scan_rows}, set(paper.TRADING_UNIVERSE))
        self.assertEqual([row["symbol"] for row in scan_rows if row["top_20_passed"]], ["ETHUSDT", "SOLUSDT"])
        self.assertEqual(len(selected), 0)
        self.assertTrue(all(row["rejection_reason"] for row in scan_rows))

    def test_defensive_probe_selects_only_one_when_enabled(self):
        signal_time = 1767240000
        data = make_defensive_scan_data(signal_time)

        scan_rows, selected = paper.build_scan_signal_batch(
            data,
            signal_time,
            defensive_probe=True,
            probe_health_gate={"can_probe": True, "block_reason": ""},
        )

        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["probe_can_enter"], True)
        self.assertEqual(selected[0]["size_multiplier"], defensive_probe_rules.PROBE_SIZE_MULTIPLIER)
        probe_rows = [row for row in scan_rows if row.get("_defensive_probe_log")]
        self.assertGreater(len(probe_rows), 1)
        self.assertEqual(len([row for row in probe_rows if row["probe_can_enter"]]), 1)

    def test_defensive_probe_blocks_critical_health(self):
        signal_time = 1767240000
        data = make_defensive_scan_data(signal_time)

        scan_rows, selected = paper.build_scan_signal_batch(
            data,
            signal_time,
            defensive_probe=True,
            probe_health_gate={"can_probe": False, "block_reason": "health_critical"},
        )

        self.assertEqual(selected, [])
        probe_rows = [row for row in scan_rows if row.get("_defensive_probe_log")]
        self.assertTrue(probe_rows)
        self.assertTrue(all(row["block_reason"] == "health_critical" for row in probe_rows))

    def test_defensive_probe_blocks_risk_off_or_panic(self):
        decision = defensive_probe_rules.evaluate_candidate(
            {"alpha_score": 8.5, "relative_strength_ok": True},
            "risk_off",
            "reduce_risk",
            "defensive_reduce_risk",
            {},
            {"can_probe": True, "block_reason": ""},
        )

        self.assertFalse(decision["probe_can_enter"])
        self.assertEqual(decision["block_reason"], "risk_off_or_panic")

    def test_short_regime_4h_only_when_option_enabled(self):
        signal_time = 1767240000
        data = make_defensive_scan_data(signal_time)
        short_index = make_short_regime_index(signal_time, "recovery")

        _default_rows, default_selected = paper.build_scan_signal_batch(data, signal_time)
        short_rows, short_selected = paper.build_scan_signal_batch(
            data,
            signal_time,
            regime_timeframe="4h",
            short_regime_index=short_index,
            short_health_gate={"can_probe": True, "block_reason": ""},
        )

        self.assertEqual(default_selected, [])
        self.assertTrue(short_selected)
        self.assertTrue(all(row["trade_regime"] == "recovery" for row in short_rows))
        self.assertTrue(all(row["size_multiplier"] == short_regime_4h.DEFAULT_RECOVERY_SIZE for row in short_selected))

    def test_short_regime_4h_blocks_critical_health(self):
        signal_time = 1767240000
        data = make_defensive_scan_data(signal_time)

        scan_rows, selected = paper.build_scan_signal_batch(
            data,
            signal_time,
            regime_timeframe="4h",
            short_regime_index=make_short_regime_index(signal_time, "uptrend"),
            short_health_gate={"can_probe": False, "block_reason": "health_critical"},
        )

        self.assertEqual(selected, [])
        self.assertTrue(scan_rows)
        self.assertTrue(all(row["rejection_reason"] == "health_critical" for row in scan_rows))

    def test_short_regime_4h_blocks_risk_off(self):
        signal_time = 1767240000
        data = make_defensive_scan_data(signal_time)

        _scan_rows, selected = paper.build_scan_signal_batch(
            data,
            signal_time,
            regime_timeframe="4h",
            short_regime_index=make_short_regime_index(signal_time, "risk_off"),
            short_health_gate={"can_probe": True, "block_reason": ""},
        )

        self.assertEqual(selected, [])

    def test_short_regime_classifier_labels_recovery_and_shock(self):
        recovery = short_regime_4h.classify_4h_row(
            {
                "close": 105,
                "ema20": 104,
                "ema50": 100,
                "ema200": 110,
                "ret_4h": 0.01,
                "drawdown_24h": -0.02,
                "drawdown_72h": -0.03,
                "atr_pct": 0.02,
                "atr_pct_sma50": 0.02,
            }
        )
        shock = short_regime_4h.classify_4h_row(
            {
                "close": 90,
                "ema20": 95,
                "ema50": 98,
                "ema200": 100,
                "ret_4h": -0.07,
                "drawdown_24h": -0.12,
                "drawdown_72h": -0.18,
                "atr_pct": 0.06,
                "atr_pct_sma50": 0.02,
            }
        )

        self.assertEqual(recovery, "recovery")
        self.assertEqual(shock, "risk_off")

    def test_paper_start_gate_records_missed_signal_without_order_candidate(self):
        signal = {
            "signal_id": "sig_1",
            "signal_time": 1000,
            "fill_time": 1000,
            "symbol": "BTCUSDT",
            "selected": True,
            "rejection_reason": "",
            "entry_block_reason": "",
        }

        rows, selected = paper.apply_paper_start_gate([signal], [signal], paper_start_ts=2000)

        self.assertEqual(rows[0]["scan_status"], "missed_signal")
        self.assertEqual(rows[0]["rejection_reason"], "missed_signal_before_paper_start")
        self.assertEqual(selected, [])

    def test_create_orders_skips_signals_before_paper_start_time(self):
        signal = {
            "signal_id": "sig_1",
            "symbol": "BTCUSDT",
            "alpha_score": 9.0,
            "signal_time": 1000,
            "signal_date": "2026-01-01 00:00",
            "fill_time": 1000,
            "trade_regime": "uptrend",
            "trade_action_bias": "long_allowed",
        }

        orders, cash, events = paper.create_orders_for_signals(
            SimpleNamespace(),
            {},
            [],
            [signal],
            1.0,
            2000,
            paper_start_ts=2000,
        )

        self.assertEqual(orders, [])
        self.assertEqual(cash, 1.0)
        self.assertEqual(events, [])

    def test_create_orders_skips_blocked_regime_signal(self):
        signal = {
            "signal_id": "sig_1",
            "symbol": "BTCUSDT",
            "alpha_score": 9.0,
            "signal_time": 2000,
            "signal_date": "2026-01-01 00:00",
            "fill_time": 2000,
            "trade_regime": "shock",
            "trade_action_bias": "shock",
        }

        orders, cash, events = paper.create_orders_for_signals(
            SimpleNamespace(),
            {},
            [],
            [signal],
            1.0,
            2000,
        )

        self.assertEqual(orders, [])
        self.assertEqual(cash, 1.0)
        self.assertEqual(events, [])


class PaperLedgerTests(unittest.TestCase):
    def test_ensure_state_files_creates_required_csv_ledgers(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp)
            paper.ensure_state_files(state_dir)

            for filename, fields in paper.STATE_FILES.values():
                path = state_dir / filename
                self.assertTrue(path.exists())
                self.assertEqual(path.read_text(encoding="utf-8").splitlines()[0], ",".join(fields))

    def test_ensure_state_files_migrates_missing_leverage_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp)
            orders_path = state_dir / paper.STATE_FILES["orders"][0]
            orders_path.write_text("order_id,status\nord_1,pending\n", encoding="utf-8")

            paper.ensure_state_files(state_dir)

            header = orders_path.read_text(encoding="utf-8").splitlines()[0].split(",")
            self.assertIn("raw_leverage", header)
            self.assertIn("applied_leverage", header)
            rows = paper.read_csv_rows(orders_path)
            self.assertEqual(rows[0]["order_id"], "ord_1")

    def test_snapshot_equity_uses_existing_rows_for_drawdown(self):
        timestamp = paper.iso_to_ts("2026-01-01T00:00:00+00:00")
        data = SimpleNamespace(
            regime_by_date={
                "2026-01-01": {
                    "trade_regime": "uptrend",
                    "trade_action_bias": "long_allowed",
                }
            }
        )
        existing = [{"timestamp": timestamp - 3600, "equity": "1.0", "drawdown_pct": "0.0"}]

        row = paper.snapshot_equity(data, {}, 0.9, timestamp, timestamp, existing)

        self.assertAlmostEqual(float(row["drawdown_pct"]), -10.0)
        self.assertAlmostEqual(float(row["max_drawdown_pct"]), -10.0)
        self.assertEqual(row["strategy_status"], "warning")


class PaperLeverageTests(unittest.TestCase):
    def test_applied_leverage_uses_integer_steps(self):
        cases = [
            (0.75, 1),
            (1.0, 1),
            (1.01, 2),
            (2.0, 2),
            (2.01, 3),
            (3.0, 3),
            (3.01, 4),
            (4.0, 4),
            (9.0, 4),
        ]

        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(paper.applied_leverage_from_raw(raw), expected)


def make_signal(symbol, alpha_score, rank, regime_reason="uptrend"):
    return {
        "symbol": symbol,
        "signal_time": 1767225600,
        "signal_date": "2026-01-01 00:00",
        "trade_regime": "uptrend",
        "trade_action_bias": "long_allowed",
        "regime_reason": regime_reason,
        "alpha_score": alpha_score,
        "rank": rank,
        "universe_size": 7,
    }


def make_defensive_scan_data(signal_time):
    open_time = signal_time - 4 * 3600
    rows = {}
    for index, symbol in enumerate(paper.TRADING_UNIVERSE):
        rows[symbol] = make_4h_row(open_time, trend_ok=symbol in {"ETHUSDT", "SOLUSDT", "BNBUSDT"}, strength=10 - index)
    return SimpleNamespace(
        by_time_4h={symbol: {open_time: row} for symbol, row in rows.items()},
        regime_by_date={
            paper.alpha.date_from_ts(signal_time): {
                "trade_regime": "defensive",
                "trade_action_bias": "reduce_risk",
            }
        },
    )


def make_short_regime_index(signal_time, regime):
    action = short_regime_4h.action_bias_for_regime(regime)
    return {
        "by_close_time": {
            signal_time: {
                "time": signal_time - 4 * 3600,
                "close_time": signal_time,
                "close": 100,
                "ema20": 99,
                "ema50": 98,
                "ema200": 97,
                "short_regime": regime,
                "strict_short_regime": regime,
                "short_action_bias": action,
            }
        },
        "rows": [],
    }


def make_4h_row(timestamp, trend_ok=True, strength=1):
    close = 100 + strength
    ema20 = close - 1 if trend_ok else close + 1
    ema50 = close - 3 if trend_ok else close + 2
    return {
        "time": timestamp,
        "close_time": timestamp + 4 * 3600,
        "open": close - 1,
        "high": close + 1,
        "low": close - 2,
        "close": close,
        "volume": 200,
        "volume20": 100,
        "ema20": ema20,
        "ema50": ema50,
        "atr14": 2,
        "ret_7d": 0.01 * strength,
        "ret_14d": 0.012 * strength,
        "recent_ema20_pullback": trend_ok,
        "recent_ema50_pullback": False,
    }


if __name__ == "__main__":
    unittest.main()
