import sys
import unittest
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ml_regime_labels import add_forward_labels, classify_forward_label, label_distribution  # noqa: E402


class MlRegimeLabelTests(unittest.TestCase):
    def test_threshold_precedence(self):
        self.assertEqual(classify_forward_label(0.20, -0.12), "shock")
        self.assertEqual(classify_forward_label(0.09, -0.05), "uptrend")
        self.assertEqual(classify_forward_label(0.04, -0.07), "recovery")
        self.assertEqual(classify_forward_label(-0.06, -0.04), "defensive")
        self.assertEqual(classify_forward_label(0.01, -0.02), "chop")

    def test_add_forward_labels_uses_future_window_only_for_labels(self):
        frame = pd.DataFrame(
            {
                "time": [1577836800 + day * 86400 for day in range(6)],
                "date": [f"2020-01-0{day + 1}" for day in range(6)],
                "close": [100, 101, 103, 110, 112, 114],
                "low": [99, 100, 102, 109, 111, 113],
            }
        )

        labeled = add_forward_labels(frame, horizon_days=3)

        self.assertAlmostEqual(labeled.iloc[0]["future_return_3d"], 0.10)
        self.assertAlmostEqual(labeled.iloc[0]["future_max_drawdown_3d"], 0.0)
        self.assertEqual(labeled.iloc[0]["label"], "uptrend")
        self.assertTrue(pd.isna(labeled.iloc[-1]["label"]))

    def test_label_distribution_keeps_known_label_order(self):
        rows = label_distribution(["uptrend", "shock", "shock", "chop"])
        labels = [row["label"] for row in rows]

        self.assertEqual(labels, ["shock", "defensive", "chop", "recovery", "uptrend"])
        self.assertEqual(rows[0]["count"], 2)


if __name__ == "__main__":
    unittest.main()
