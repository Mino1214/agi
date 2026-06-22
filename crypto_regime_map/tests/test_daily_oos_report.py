import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import alpha_engine_v1_2_daily_oos_report as report  # noqa: E402
import alpha_engine_v1_2_paper_engine as paper  # noqa: E402


class DailyOosReportTests(unittest.TestCase):
    def test_zero_order_report_and_reduce_risk_normal_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp)
            paper.ensure_state_files(state_dir)
            now_ts = report.OOS_START_TS + 3600
            signal_after_start = report.OOS_START_TS + 60

            paper.write_csv_rows(
                state_dir / paper.STATE_FILES["signals"][0],
                [
                    {
                        "signal_id": "pre_oos",
                        "signal_time": report.OOS_START_TS - 60,
                        "symbol": "ETHUSDT",
                        "selected": "False",
                        "rejection_reason": "alpha_score_below_min",
                        "top_20_passed": "False",
                    },
                    {
                        "signal_id": "reduce_risk",
                        "signal_time": signal_after_start,
                        "symbol": "SOLUSDT",
                        "selected": "False",
                        "rejection_reason": "defensive_no_entry",
                        "top_20_passed": "True",
                        "trade_action_bias": "reduce_risk",
                    },
                    {
                        "signal_id": "alpha_low",
                        "signal_time": signal_after_start + 60,
                        "symbol": "XRPUSDT",
                        "selected": "False",
                        "rejection_reason": "alpha_score_below_min",
                        "top_20_passed": "False",
                    },
                ],
                paper.SIGNAL_FIELDS,
            )
            paper.write_csv_rows(
                state_dir / paper.STATE_FILES["equity"][0],
                [
                    {
                        "timestamp": signal_after_start + 120,
                        "date": "2026-06-21 14:16",
                        "equity": "1.0",
                        "cash": "1.0",
                        "open_unrealized": "0",
                        "cumulative_pnl": "0",
                        "drawdown_pct": "0",
                        "open_positions": "0",
                        "current_regime": "defensive",
                        "current_action_bias": "reduce_risk",
                        "strategy_status": "warning",
                        "max_drawdown_pct": "0",
                    }
                ],
                paper.EQUITY_FIELDS,
            )
            write_rows(
                state_dir / "paper_health.csv",
                [
                    "timestamp",
                    "date",
                    "status",
                    "can_enter",
                    "pause_reason",
                    "last_run_at",
                    "last_data_update_at",
                    "recent_7d_trade_count",
                    "recent_30d_trade_count",
                    "recent_30d_mdd_pct",
                ],
                [
                    {
                        "timestamp": signal_after_start + 180,
                        "date": "2026-06-21 14:17 UTC",
                        "status": "warning",
                        "can_enter": "False",
                        "pause_reason": "regime_reduce_risk",
                        "last_run_at": "2026-06-21 14:17 UTC",
                        "last_data_update_at": "2026-06-21 14:16 UTC",
                        "recent_7d_trade_count": "0",
                        "recent_30d_trade_count": "0",
                        "recent_30d_mdd_pct": "0",
                    }
                ],
            )
            (state_dir / paper.HEALTH_STATE_NAME).write_text(
                json.dumps(
                    {
                        "status": "warning",
                        "warning_reasons": [
                            {
                                "status": "warning",
                                "section": "data",
                                "code": "missing_candles",
                                "message": "historical gap",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            result = report.generate_daily_oos_report(
                state_dir=state_dir,
                report_path=state_dir / "daily.md",
                summary_path=state_dir / "daily.csv",
                now_ts=now_ts,
            )

            self.assertEqual(result.today["signal_count"], "2")
            self.assertEqual(result.today["order_created_count"], "0")
            self.assertEqual(result.today["block_reduce_risk"], "2")
            self.assertEqual(result.today["block_alpha_score_below_min"], "1")
            self.assertEqual(result.today["normal_reduce_risk_block"], "yes")
            self.assertIn("정상 차단", result.report_text)
            self.assertIn("성과 판단 불가", result.report_text)
            self.assertTrue((state_dir / "daily.csv").exists())


def write_rows(path: Path, fieldnames, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    unittest.main()
