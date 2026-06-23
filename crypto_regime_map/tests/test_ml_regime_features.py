import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ml_regime_features import build_feature_frame  # noqa: E402


class MlRegimeFeatureTests(unittest.TestCase):
    def test_btc_features_do_not_change_when_future_rows_are_added(self):
        raw = {"BTCUSDT": make_candles(260, start_price=100.0)}
        full = build_feature_frame(raw).frame
        prefix = build_feature_frame({"BTCUSDT": raw["BTCUSDT"][:230]}).frame

        common_time = prefix.iloc[-1]["time"]
        full_row = full[full["time"] == common_time].iloc[0]
        prefix_row = prefix.iloc[-1]

        self.assertAlmostEqual(full_row["return_14d"], prefix_row["return_14d"])
        self.assertAlmostEqual(full_row["distance_to_ema200"], prefix_row["distance_to_ema200"])
        self.assertAlmostEqual(full_row["drawdown_from_90d_high"], prefix_row["drawdown_from_90d_high"])

    def test_relative_strength_features_are_added_when_assets_exist(self):
        raw = {
            "BTCUSDT": make_candles(80, start_price=100.0),
            "ETHUSDT": make_candles(80, start_price=20.0, daily_step=0.02),
            "SOLUSDT": make_candles(80, start_price=10.0, daily_step=0.03),
        }
        result = build_feature_frame(raw)

        self.assertIn("eth_btc_return_spread_7d", result.used_features)
        self.assertIn("sol_btc_trend", result.used_features)
        self.assertNotIn("eth_btc_trend", result.missing_features)

    def test_missing_optional_features_are_reported(self):
        result = build_feature_frame({"BTCUSDT": make_candles(40, start_price=100.0)})

        self.assertIn("eth_btc_return_spread_7d", result.missing_features)
        self.assertIn("sol_btc_trend", result.missing_features)
        self.assertIn("btc_funding_rate", result.missing_features)
        self.assertIn("btc_open_interest_change_7d", result.missing_features)


def make_candles(days, start_price, daily_step=0.01):
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


if __name__ == "__main__":
    unittest.main()
