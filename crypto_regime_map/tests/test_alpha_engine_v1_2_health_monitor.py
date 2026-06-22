import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Optional


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import alpha_engine_v1_2_health_monitor as health  # noqa: E402
import alpha_engine_v1_2_paper_engine as paper  # noqa: E402


NOW_TS = 1_800_000_000


class AlphaEngineHealthMonitorTests(unittest.TestCase):
    def test_normal_files_are_normal(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = HealthFixture(Path(tmp))
            env.write_normal()

            result = env.check()

            self.assertEqual(result["status"], "normal")
            self.assertTrue(result["new_entry_allowed"])
            self.assertEqual(result["component_status"]["data"], "normal")
            state = health.load_health_state(env.state_dir)
            self.assertTrue(state["strategy_locked"])
            self.assertEqual(state["strategy_lock_name"], health.STRATEGY_LOCK_NAME)
            self.assertTrue(state["paper_start_time"])
            self.assertIn("human_summary", state)

    def test_missing_csv_is_critical(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = HealthFixture(Path(tmp))
            env.write_normal()
            (env.state_dir / "paper_orders.csv").unlink()

            result = env.check()

            self.assertEqual(result["status"], "critical")
            self.assertTrue(any(item["code"] == "csv_read_error" for item in result["findings"]))

    def test_duplicate_positions_auto_pause(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = HealthFixture(Path(tmp))
            env.write_normal()
            env.write_positions([position_row("pos_1", "BTCUSDT"), position_row("pos_2", "BTCUSDT")])

            result = env.check()

            self.assertEqual(result["status"], "paused")
            self.assertFalse(result["new_entry_allowed"])
            self.assertTrue(any(item["code"] == "duplicate_open_positions" for item in result["findings"]))

    def test_reduce_risk_order_auto_pause(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = HealthFixture(Path(tmp))
            env.write_normal()
            env.write_orders([order_row("ord_1", "BTCUSDT", status="pending", action_bias="reduce_risk")])

            result = env.check()

            self.assertEqual(result["status"], "paused")
            self.assertTrue(any(item["code"] == "order_created_in_blocked_regime" for item in result["findings"]))

    def test_stale_data_auto_pause(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = HealthFixture(Path(tmp))
            env.write_normal(raw_latest_close=NOW_TS - 7 * 3600)

            result = env.check()

            self.assertEqual(result["status"], "paused")
            self.assertTrue(any(item["code"] in {"data_update_paused_delay", "latest_1h_candle_stale"} for item in result["findings"]))

    def test_liquidation_risk_auto_pause(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = HealthFixture(Path(tmp))
            env.write_normal()
            env.write_positions([position_row("pos_1", "BTCUSDT", liquidation_price=96, buffer_pct=-1, liquidation_risk=True)])

            result = env.check()

            self.assertEqual(result["status"], "paused")
            self.assertTrue(any(item["code"] == "liquidation_risk" for item in result["findings"]))

    def test_recent_20_pf_below_one_warns(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = HealthFixture(Path(tmp))
            env.write_normal()
            env.write_trades(pf_trade_rows(wins=5, losses=15))

            result = env.check()

            self.assertEqual(result["component_status"]["performance"], "warning")
            self.assertTrue(any(item["code"] == "recent_20_pf_below_one" for item in result["findings"]))

    def test_mdd_exceeded_auto_pause(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = HealthFixture(Path(tmp))
            env.write_normal()
            env.write_equity(
                [
                    equity_row(NOW_TS - 2 * 86400, 1.0),
                    equity_row(NOW_TS - 86400, 0.89),
                    equity_row(NOW_TS, 0.89),
                ]
            )

            result = env.check()

            self.assertEqual(result["status"], "paused")
            self.assertTrue(any(item["code"] == "recent_30d_mdd_exceeded" for item in result["findings"]))

    def test_trade_frequency_auto_pause_persists_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = HealthFixture(Path(tmp))
            env.write_normal()
            env.write_trades(entry_trade_rows(46))

            result = env.check()
            state = json.loads((env.state_dir / health.HEALTH_STATE_JSON).read_text(encoding="utf-8"))

            self.assertEqual(result["status"], "paused")
            self.assertEqual(state["status"], "paused")
            self.assertTrue(any(item["code"] == "recent_30d_trade_count_paused" for item in result["findings"]))

    def test_manual_resume_requires_reason_and_records_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = HealthFixture(Path(tmp))
            env.write_normal()

            health.manual_pause(env.state_dir, "manual pause", now_ts=NOW_TS)
            with self.assertRaises(ValueError):
                health.manual_resume(env.state_dir, "", now_ts=NOW_TS + 1)
            state = health.manual_resume(env.state_dir, "checked", now_ts=NOW_TS + 2)
            events = health.read_health_events(env.state_dir)

            self.assertEqual(state["status"], "normal")
            self.assertTrue(state["new_entry_allowed"])
            self.assertTrue(any(row["code"] == "manual_resume" for row in events))

    def test_paper_engine_skips_new_orders_when_health_paused(self):
        signal = {
            "signal_id": "sig_1",
            "symbol": "BTCUSDT",
            "alpha_score": 9.0,
            "signal_time": NOW_TS,
            "signal_date": "2027-01-15 08:00",
            "fill_time": NOW_TS,
            "trade_regime": "uptrend",
            "trade_action_bias": "long_allowed",
        }

        orders, cash, events = paper.create_orders_for_signals(
            SimpleNamespace(),
            {},
            [],
            [signal],
            1.0,
            NOW_TS,
            entry_pause_reason="health_paused",
        )

        self.assertEqual(orders, [])
        self.assertEqual(cash, 1.0)
        self.assertEqual(events, [])

    def test_pending_orders_are_rejected_when_health_paused(self):
        data = SimpleNamespace(rows_1h={"BTCUSDT": [{"time": NOW_TS}]})
        orders = [order_row("ord_1", "BTCUSDT", status="pending")]

        updated, _cash, _events = paper.fill_pending_orders(
            data,
            {},
            orders,
            1.0,
            NOW_TS,
            entry_pause_reason="health_paused",
        )

        self.assertEqual(updated[0]["status"], "rejected")
        self.assertEqual(updated[0]["reason"], "health_paused")

    def test_health_flow_data_gap_fails_gate_and_locks_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = HealthFixture(Path(tmp))
            env.write_normal()
            env.remove_raw_candle("SOLUSDT", "1h", NOW_TS - 2 * 3600)

            payload = health.build_health_flow_payload(
                env.state_dir,
                env.raw_dir,
                env.report_path,
                now_ts=NOW_TS,
                write_outputs=True,
            )
            state = health.load_health_state(env.state_dir)

            self.assertEqual(payload["gates"]["data"]["status"], "fail")
            self.assertFalse(payload["new_entry_allowed"])
            self.assertEqual(payload["final_block_reason"], "health_data_gap")
            self.assertFalse(state["new_entry_allowed"])

    def test_health_flow_repair_makes_data_gate_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = HealthFixture(Path(tmp))
            env.write_normal()
            missing_ts = NOW_TS - 2 * 3600
            env.remove_raw_candle("SOLUSDT", "1h", missing_ts)

            repair = health.repair_market_data_gaps(
                env.state_dir,
                env.raw_dir,
                now_ts=NOW_TS,
                fetcher=lambda symbol, interval, start, end: [candle_row(missing_ts)],
            )
            payload = health.build_health_flow_payload(
                env.state_dir,
                env.raw_dir,
                env.report_path,
                now_ts=NOW_TS,
                write_outputs=True,
            )

            self.assertEqual(repair["validation_result"], "pass")
            self.assertEqual(payload["gates"]["data"]["status"], "pass")
            self.assertTrue(payload["new_entry_allowed"])

    def test_health_flow_regime_blocks_when_data_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = HealthFixture(Path(tmp))
            env.write_normal()
            env.write_equity([equity_row(NOW_TS, 1.0, regime="defensive", action_bias="reduce_risk")])

            payload = health.build_health_flow_payload(
                env.state_dir,
                env.raw_dir,
                env.report_path,
                now_ts=NOW_TS,
                write_outputs=True,
            )

            self.assertEqual(payload["gates"]["data"]["status"], "pass")
            self.assertEqual(payload["gates"]["regime"]["status"], "blocked")
            self.assertFalse(payload["new_entry_allowed"])
            self.assertEqual(payload["final_block_reason"], "regime_reduce_risk")

    def test_health_flow_all_gates_pass_allows_new_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = HealthFixture(Path(tmp))
            env.write_normal()

            payload = health.build_health_flow_payload(
                env.state_dir,
                env.raw_dir,
                env.report_path,
                now_ts=NOW_TS,
                write_outputs=True,
            )

            self.assertEqual(payload["gates"]["data"]["status"], "pass")
            self.assertEqual(payload["gates"]["regime"]["status"], "pass")
            self.assertEqual(payload["gates"]["risk"]["status"], "pass")
            self.assertTrue(payload["new_entry_allowed"])

    def test_health_flow_signal_order_block_reason_is_separated(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = HealthFixture(Path(tmp))
            env.write_normal()
            env.remove_raw_candle("SOLUSDT", "1h", NOW_TS - 2 * 3600)

            payload = health.build_health_flow_payload(
                env.state_dir,
                env.raw_dir,
                env.report_path,
                now_ts=NOW_TS,
                write_outputs=True,
            )
            btc = next(row for row in payload["signals"] if row["symbol"] == "BTCUSDT")

            self.assertEqual(btc["signal_status"], "candidate_pass")
            self.assertEqual(btc["order_status"], "blocked")
            self.assertEqual(btc["block_reason"], "health_data_gap")

    def test_future_4h_candle_close_is_not_signal_delay(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = HealthFixture(Path(tmp))
            env.write_normal(raw_latest_close=NOW_TS + 4 * 3600)
            env.write_signals(signal_rows(NOW_TS))

            result = env.check()

            self.assertFalse(any(item["code"] == "missing_signal_after_4h_close" for item in result["findings"]))


class HealthFixture:
    def __init__(self, root: Path):
        self.root = root
        self.state_dir = root / "state"
        self.raw_dir = root / "raw"
        self.report_path = root / "reports" / "health.md"

    def write_normal(self, raw_latest_close: int = NOW_TS) -> None:
        self.write_raw(raw_latest_close)
        self.write_positions([])
        self.write_orders([])
        self.write_trades([])
        self.write_equity([equity_row(NOW_TS - 3600, 1.0), equity_row(NOW_TS, 1.0)])
        self.write_signals(signal_rows(raw_latest_close))

    def check(self) -> dict:
        return health.run_check(
            state_dir=self.state_dir,
            raw_dir=self.raw_dir,
            report_path=self.report_path,
            now_ts=NOW_TS,
            write_outputs=True,
        )

    def write_raw(self, latest_close: int) -> None:
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        for symbol in health.UNIVERSE:
            for interval, seconds in health.INTERVAL_SECONDS.items():
                latest_open = latest_close - seconds
                rows = []
                for index in range(8):
                    timestamp = latest_open - (7 - index) * seconds
                    rows.append(candle_row(timestamp))
                (self.raw_dir / f"{symbol}_{interval}.json").write_text(json.dumps(rows), encoding="utf-8")

    def remove_raw_candle(self, symbol: str, interval: str, timestamp: int) -> None:
        path = self.raw_dir / f"{symbol}_{interval}.json"
        rows = json.loads(path.read_text(encoding="utf-8"))
        rows = [row for row in rows if int(row["time"]) != timestamp]
        path.write_text(json.dumps(rows), encoding="utf-8")

    def write_positions(self, rows: list[dict]) -> None:
        paper.write_csv_rows(self.state_dir / "paper_positions.csv", rows, paper.POSITION_FIELDS)

    def write_orders(self, rows: list[dict]) -> None:
        paper.write_csv_rows(self.state_dir / "paper_orders.csv", rows, paper.ORDER_FIELDS)

    def write_trades(self, rows: list[dict]) -> None:
        paper.write_csv_rows(self.state_dir / "paper_trades.csv", rows, paper.TRADE_FIELDS)

    def write_equity(self, rows: list[dict]) -> None:
        paper.write_csv_rows(self.state_dir / "paper_equity.csv", rows, paper.EQUITY_FIELDS)

    def write_signals(self, rows: list[dict]) -> None:
        paper.write_csv_rows(self.state_dir / "paper_signals.csv", rows, paper.SIGNAL_FIELDS)


def signal_rows(signal_time: int) -> list[dict]:
    rows = []
    for index, symbol in enumerate(health.TRADING_UNIVERSE, start=1):
        selected = symbol == "BTCUSDT"
        top_20 = symbol in {"BTCUSDT", "ETHUSDT"}
        rows.append(
            {
                "signal_id": f"sig_{symbol.lower()}_{signal_time}",
                "signal_time": signal_time,
                "signal_date": "2027-01-15 08:00",
                "fill_time": signal_time,
                "fill_date": "2027-01-15 08:00",
                "symbol": symbol,
                "alpha_score": 10 - index,
                "rank": index,
                "universe_size": len(health.TRADING_UNIVERSE),
                "selected": selected,
                "rejection_reason": "" if selected else "alpha_score_not_top_20pct",
                "scan_status": "scanned",
                "top_20_passed": top_20,
                "entry_block_reason": "",
                "top_score_pct": 0.2,
                "top_rank_cutoff": 2,
                "trade_regime": "uptrend",
                "trade_action_bias": "long_allowed",
                "regime_reason": "",
                "close": 100,
                "ema20": 99,
                "ema50": 98,
                "atr14": 2,
            }
        )
    return rows


def position_row(
    position_id: str,
    symbol: str,
    liquidation_price: float = 50.0,
    buffer_pct: float = 10.0,
    liquidation_risk: bool = False,
) -> dict:
    return {
        "position_id": position_id,
        "status": "open",
        "symbol": symbol,
        "side": "long",
        "opened_at": NOW_TS - 3600,
        "opened_at_date": "2027-01-15 07:00",
        "signal_time": NOW_TS - 7200,
        "signal_date": "2027-01-15 06:00",
        "order_id": f"ord_{position_id}",
        "entry_price": 100,
        "stop_price": 95,
        "risk_distance": 5,
        "risk_amount": 0.01,
        "units": 0.01,
        "initial_units": 0.01,
        "entry_equity": 1.0,
        "alpha_score": 9,
        "trade_regime": "uptrend",
        "trade_action_bias": "long_allowed",
        "liquidation_leverage_used": 1,
        "liquidation_price_est": liquidation_price,
        "symbol_leverage_cap": 4,
        "raw_leverage": 1,
        "applied_leverage": 1,
        "realized_pnl": 0,
        "funding_pnl": 0,
        "partial_taken": False,
        "last_funding_time": NOW_TS - 3600,
        "last_update_time": NOW_TS,
        "last_update_date": "2027-01-15 08:00",
        "last_price": 101,
        "unrealized_pnl": 0.01,
        "notional": 1.01,
        "liquidation_buffer_pct": buffer_pct,
        "liquidation_risk": liquidation_risk,
    }


def order_row(order_id: str, symbol: str, status: str = "filled", action_bias: str = "long_allowed") -> dict:
    return {
        "order_id": order_id,
        "created_time": NOW_TS - 60,
        "created_date": "2027-01-15 07:59",
        "signal_id": f"sig_{order_id}",
        "signal_time": NOW_TS - 3600,
        "signal_date": "2027-01-15 07:00",
        "fill_time": NOW_TS,
        "fill_date": "2027-01-15 08:00",
        "symbol": symbol,
        "side": "long",
        "type": "paper_market_next_1h_open",
        "status": status,
        "reason": "",
        "alpha_score": 9,
        "trade_regime": "uptrend",
        "trade_action_bias": action_bias,
        "entry_price": 100,
        "units": 0.01,
        "notional": 1,
        "fee": 0.001,
        "raw_leverage": 1,
        "applied_leverage": 1,
        "position_id": f"pos_{order_id}",
        "updated_time": NOW_TS,
        "updated_date": "2027-01-15 08:00",
    }


def candle_row(timestamp: int) -> dict:
    return {
        "time": timestamp,
        "open": 100.0,
        "high": 105.0,
        "low": 95.0,
        "close": 101.0,
        "volume": 1000.0,
    }


def equity_row(timestamp: int, equity: float, regime: str = "uptrend", action_bias: str = "long_allowed") -> dict:
    return {
        "timestamp": timestamp,
        "date": "2027-01-15 08:00",
        "equity": equity,
        "cash": equity,
        "open_unrealized": 0,
        "cumulative_pnl": equity - 1,
        "drawdown_pct": 0,
        "open_positions": 0,
        "open_notional": 0,
        "current_regime": regime,
        "current_action_bias": action_bias,
        "strategy_status": "normal",
        "max_drawdown_pct": 0,
        "liquidation_risk_count": 0,
    }


def pf_trade_rows(wins: int, losses: int) -> list[dict]:
    rows = []
    index = 0
    for _ in range(wins):
        rows.extend(entry_exit_pair(index, 0.01))
        index += 1
    for _ in range(losses):
        rows.extend(entry_exit_pair(index, -0.01))
        index += 1
    return rows


def entry_trade_rows(count: int) -> list[dict]:
    rows = []
    for index in range(count):
        rows.append(entry_row(index, NOW_TS - index * 3600))
    return rows


def entry_exit_pair(index: int, pnl: float) -> list[dict]:
    entry_ts = NOW_TS - (index + 2) * 3600
    exit_ts = entry_ts + 1800
    position_id = f"pos_trade_{index}"
    entry = entry_row(index, entry_ts, position_id=position_id)
    exit_row = {
        **entry,
        "event_id": f"exit_{index}",
        "event_type": "exit",
        "timestamp": exit_ts,
        "date": "2027-01-15 08:00",
        "side": "sell",
        "pnl": pnl,
        "cash_delta": pnl,
        "equity_after": 1 + pnl,
        "reason": "test_exit",
        "exit_price": 101 if pnl > 0 else 99,
        "position_total_pnl": pnl,
        "hold_hours": 0.5,
    }
    return [entry, exit_row]


def entry_row(index: int, timestamp: int, position_id: Optional[str] = None) -> dict:
    position_id = position_id or f"pos_entry_{index}"
    return {
        "event_id": f"entry_{index}",
        "event_type": "entry",
        "position_id": position_id,
        "order_id": f"ord_trade_{index}",
        "timestamp": timestamp,
        "date": "2027-01-15 08:00",
        "symbol": "BTCUSDT",
        "side": "buy",
        "price": 100,
        "units": 0.01,
        "notional": 1,
        "fee": 0.001,
        "raw_leverage": 1,
        "applied_leverage": 1,
        "funding_rate": "",
        "funding_pnl": "",
        "pnl": -0.001,
        "cash_delta": -0.001,
        "equity_after": 1,
        "reason": "entry",
        "alpha_score": 9,
        "trade_regime": "uptrend",
        "trade_action_bias": "long_allowed",
        "entry_price": 100,
        "stop_price": 95,
        "exit_price": "",
        "position_total_pnl": "",
        "hold_hours": 0,
    }


if __name__ == "__main__":
    unittest.main()
