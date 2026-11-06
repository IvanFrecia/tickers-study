"""Unit tests for model-loss behavior."""

from __future__ import annotations

import unittest

import tensorflow as tf

from src.models import TARGET_CLOSE_PENALTY, weighted_mse


class WeightedMSETests(unittest.TestCase):
    def test_weighted_mse_adds_terminal_target_penalty(self) -> None:
        y_true = tf.constant([[0.10, 0.10]], dtype=tf.float32)
        y_pred = tf.constant([[0.00, 0.20]], dtype=tf.float32)

        loss = float(weighted_mse(y_true, y_pred).numpy())

        expected_step_loss = ((0.10**2) * 1.0 + (0.10**2) * 1.5) / 2.0
        expected_terminal_loss = ((1.10 * 1.10) - (1.00 * 1.20)) ** 2
        expected = expected_step_loss + TARGET_CLOSE_PENALTY * expected_terminal_loss

        self.assertAlmostEqual(loss, expected, places=6)


if __name__ == "__main__":
    unittest.main()
