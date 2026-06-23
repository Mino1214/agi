import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from ml_regime_v3_hybrid_backtest import (  # noqa: E402
    HybridPolicy,
    MlPrediction,
    ml_policy_decision,
    prediction_for_fill_time,
)


class MlRegimeV3HybridTests(unittest.TestCase):
    def test_filter_policy_blocks_below_threshold(self):
        decision = ml_policy_decision(
            HybridPolicy("ML_OPP_FILTER_65", opportunity_threshold=0.65),
            MlPrediction(date="2024-01-01", p_opportunity=0.64, p_shock=0.90),
        )

        self.assertFalse(decision["allow_entry"])
        self.assertEqual(decision["block_reason"], "ml_opportunity_below_threshold")

    def test_shock_soft_reduces_size_without_blocking(self):
        decision = ml_policy_decision(
            HybridPolicy("ML_OPP_WITH_SHOCK_SOFT", size_adjust=True, shock_soft=True),
            MlPrediction(date="2024-01-01", p_opportunity=0.72, p_shock=0.86),
        )

        self.assertTrue(decision["allow_entry"])
        self.assertAlmostEqual(decision["size_multiplier"], 0.25)

    def test_size_adjust_keeps_low_opportunity_as_small_entry(self):
        decision = ml_policy_decision(
            HybridPolicy("ML_OPP_SIZE_ADJUST", size_adjust=True),
            MlPrediction(date="2024-01-01", p_opportunity=0.55, p_shock=0.10),
        )

        self.assertTrue(decision["allow_entry"])
        self.assertAlmostEqual(decision["size_multiplier"], 0.25)

    def test_prediction_lookup_uses_previous_utc_date(self):
        predictions = {
            "2024-01-01": MlPrediction(date="2024-01-01", p_opportunity=0.7, p_shock=0.2),
            "2024-01-02": MlPrediction(date="2024-01-02", p_opportunity=0.1, p_shock=0.9),
        }

        prediction = prediction_for_fill_time(predictions, 1704153600)

        self.assertEqual(prediction.date, "2024-01-01")


if __name__ == "__main__":
    unittest.main()
