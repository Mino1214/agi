import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import alpha_engine_v1_2_paper_engine as paper  # noqa: E402
import alpha_engine_v1_2_health_monitor as health  # noqa: E402
import paper_control_panel as panel  # noqa: E402


class PaperControlPanelTests(unittest.TestCase):
    def test_status_is_paper_only_and_live_locked(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp)
            paper.ensure_state_files(state_dir)

            status = panel.build_status(state_dir)

            self.assertTrue(status["paper_only"])
            self.assertFalse(status["strategy"]["live_lock"]["live_enabled"])
            self.assertFalse(status["strategy"]["live_lock"]["button_enabled"])

    def test_status_reflects_health_pause_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp)
            paper.ensure_state_files(state_dir)
            health.manual_pause(state_dir, "operator check")

            status = panel.build_status(state_dir)

            self.assertEqual(status["strategy"]["status"], "paused")
            self.assertFalse(status["strategy"]["can_enter"])
            self.assertEqual(status["strategy"]["pause_reason"], "operator check")

    def test_clear_paper_state_keeps_required_headers(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp)
            paper.ensure_state_files(state_dir)
            paper.write_csv_rows(
                state_dir / paper.STATE_FILES["orders"][0],
                [{"order_id": "ord_test", "status": "pending"}],
                paper.ORDER_FIELDS,
            )

            result = panel.clear_paper_state(state_dir)

            self.assertTrue(result["ok"])
            orders_path = state_dir / paper.STATE_FILES["orders"][0]
            self.assertEqual(orders_path.read_text(encoding="utf-8").splitlines()[0], ",".join(paper.ORDER_FIELDS))
            self.assertEqual(len(paper.read_csv_rows(orders_path)), 0)

    def test_enrich_signal_exposes_raw_and_applied_leverage(self):
        row = {
            "close": 100,
            "atr14": 10,
            "selected": True,
        }
        latest_equity = {"equity": 1.0}

        signal = panel.enrich_signal(row, latest_equity)

        self.assertIsNotNone(signal["raw_leverage"])
        self.assertIn(signal["applied_leverage"], {1, 2, 3, 4})
        self.assertEqual(signal["expected_leverage"], signal["applied_leverage"])

    def test_chart_events_map_trade_and_missed_signal_badges(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp)
            paper.ensure_state_files(state_dir)
            paper.write_csv_rows(
                state_dir / paper.STATE_FILES["orders"][0],
                [
                    {
                        "order_id": "ord_1",
                        "signal_id": "sig_1",
                        "signal_time": 3600,
                        "symbol": "BTCUSDT",
                        "side": "long",
                        "status": "rejected",
                        "reason": "max_positions",
                    }
                ],
                paper.ORDER_FIELDS,
            )
            paper.write_csv_rows(
                state_dir / paper.STATE_FILES["trades"][0],
                [
                    {
                        "event_id": "entry_1",
                        "event_type": "entry",
                        "timestamp": 3600,
                        "symbol": "BTCUSDT",
                        "side": "buy",
                        "price": 100,
                        "reason": "entry",
                    },
                    {
                        "event_id": "stop_1",
                        "event_type": "exit",
                        "timestamp": 7200,
                        "symbol": "BTCUSDT",
                        "side": "sell",
                        "price": 94,
                        "reason": "stop",
                    },
                ],
                paper.TRADE_FIELDS,
            )
            paper.write_csv_rows(
                state_dir / paper.STATE_FILES["signals"][0],
                [
                    {
                        "signal_id": "sig_1",
                        "signal_time": 3600,
                        "symbol": "BTCUSDT",
                        "selected": False,
                        "rejection_reason": "defensive_no_entry",
                        "close": 101,
                    }
                ],
                paper.SIGNAL_FIELDS,
            )

            events = panel.build_chart_events(
                state_dir,
                "BTCUSDT",
                "1h",
                [{"time": 0}, {"time": 3600}, {"time": 7200}],
            )

            by_id = {event["id"]: event for event in events}
            self.assertEqual(by_id["entry_1"]["label"], "B")
            self.assertEqual(by_id["entry_1"]["tone"], "long-entry")
            self.assertEqual(by_id["entry_1"]["placement"], "below")
            self.assertEqual(by_id["stop_1"]["label"], "SL")
            self.assertEqual(by_id["stop_1"]["tone"], "stop-loss")
            self.assertEqual(by_id["stop_1"]["time"], 3600)
            self.assertEqual(by_id["sig_1"]["label"], "MS")
            self.assertEqual(by_id["sig_1"]["tone"], "missed")
            self.assertEqual(by_id["ord_1"]["label"], "MS")
            self.assertEqual(by_id["ord_1"]["tone"], "missed")

    def test_chart_price_lines_include_open_position_levels(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp)
            paper.ensure_state_files(state_dir)
            paper.write_csv_rows(
                state_dir / paper.STATE_FILES["positions"][0],
                [
                    {
                        "position_id": "pos_1",
                        "symbol": "BTCUSDT",
                        "side": "long",
                        "entry_price": 100,
                        "stop_price": 95,
                        "risk_distance": 5,
                        "last_price": 103,
                    }
                ],
                paper.POSITION_FIELDS,
            )

            lines = panel.build_chart_price_lines(state_dir, "BTCUSDT", [])

            prices = {line["id"]: line["price"] for line in lines}
            self.assertEqual(prices["entry"], 100)
            self.assertEqual(prices["stop"], 95)
            self.assertEqual(prices["tp"], 105)
            self.assertEqual(prices["current"], 103)


if __name__ == "__main__":
    unittest.main()
