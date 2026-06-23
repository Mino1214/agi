import sys
import unittest
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ml_regime_v2 import (  # noqa: E402
    add_v2_labels,
    build_v2_feature_frame,
    select_opportunity_threshold,
    select_shock_threshold,
)


class MlRegimeV2Tests(unittest.TestCase):
    def test_v2_labels_split_shock_and_opportunity(self):
        closes = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 108.0, 110.0, 112.0]
        closes.extend([113.0 + day for day in range(20)])
        lows = [100.0] + [99.0] * 5 + [90.0] + [103.0] * 3 + [112.0] * 20
        frame = pd.DataFrame(
            {
                "time": [1577836800 + day * 86400 for day in range(30)],
                "date": [f"2020-01-{day + 1:02d}" for day in range(30)],
                "open": [100.0] * 30,
                "high": [101.0] * 30,
                "low": lows,
                "close": closes,
                "volume": [1000.0] * 30,
            }
        )

        labeled = add_v2_labels(frame, shock_drawdown_14d=-0.08)

        self.assertEqual(labeled.iloc[0]["shock_label"], 1)
        self.assertEqual(int(labeled.iloc[10]["opportunity_label"]), 1)
        self.assertTrue(pd.isna(labeled.iloc[-1]["shock_label"]))

    def test_threshold_selection_prefers_recall_for_shock(self):
        y_true = [1, 1, 1, 0, 0, 0]
        probabilities = [0.90, 0.65, 0.20, 0.60, 0.10, 0.05]

        threshold = select_shock_threshold(y_true, probabilities, recall_target=0.50)

        self.assertLessEqual(threshold, 0.65)
        self.assertGreaterEqual(threshold, 0.20)

    def test_opportunity_threshold_requires_precision_delta_when_available(self):
        y_true = [1, 1, 1, 1, 1] + [0] * 20
        probabilities = [0.95, 0.92, 0.90, 0.86, 0.82] + [0.20, 0.18, 0.16, 0.14, 0.12] + [0.05] * 15

        threshold = select_opportunity_threshold(y_true, probabilities, baseline=0.20, precision_delta=0.08)

        self.assertGreaterEqual(threshold, 0.80)

    def test_v2_features_do_not_change_when_future_rows_are_added(self):
        raw_1d = {
            "BTCUSDT": make_daily_candles(260, 100.0),
            "ETHUSDT": make_daily_candles(260, 20.0, daily_step=0.012),
            "SOLUSDT": make_daily_candles(260, 10.0, daily_step=0.014),
        }
        raw_4h = {"BTCUSDT": make_intraday_candles(260 * 6, 100.0, 4 * 3600, step=0.001)}
        raw_1h = {"BTCUSDT": make_intraday_candles(260 * 24, 100.0, 3600, step=0.0002)}
        full = build_v2_feature_frame(raw_1d=raw_1d, raw_4h=raw_4h, raw_1h=raw_1h).frame
        prefix = build_v2_feature_frame(
            raw_1d={symbol: rows[:230] for symbol, rows in raw_1d.items()},
            raw_4h={"BTCUSDT": raw_4h["BTCUSDT"][:230 * 6]},
            raw_1h={"BTCUSDT": raw_1h["BTCUSDT"][:230 * 24]},
        ).frame

        common_time = prefix.iloc[-1]["time"]
        full_row = full[full["time"] == common_time].iloc[0]
        prefix_row = prefix.iloc[-1]

        self.assertAlmostEqual(full_row["volume_zscore_30d"], prefix_row["volume_zscore_30d"])
        self.assertAlmostEqual(full_row["btc_4h_return_24h"], prefix_row["btc_4h_return_24h"])
        self.assertAlmostEqual(full_row["btc_1h_return_6h"], prefix_row["btc_1h_return_6h"])


def make_daily_candles(days, start_price, daily_step=0.01):
    rows = []
    price = start_price
    start = 1577836800
    for index in range(days):
        price *= 1.0 + daily_step
        rows.append(
            {
                "time": start + index * 86400,
                "open": price * 0.99,
                "high": price * 1.02,
                "low": price * 0.98,
                "close": price,
                "volume": 1000 + index,
            }
        )
    return rows


def make_intraday_candles(count, start_price, interval_seconds, step=0.001):
    rows = []
    price = start_price
    start = 1577836800
    for index in range(count):
        price *= 1.0 + step
        rows.append(
            {
                "time": start + index * interval_seconds,
                "open": price * 0.999,
                "high": price * 1.003,
                "low": price * 0.997,
                "close": price,
                "volume": 100 + index,
            }
        )
    return rows


if __name__ == "__main__":
    unittest.main()
