# -*- coding: utf-8 -*-
"""Tests for the local chip-distribution fallback."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

from data_provider.a_stock_data_chip import (
    LOCAL_CHIP_SOURCE,
    build_local_chip_distribution_from_frame,
)
from data_provider.base import DataFetcherManager
from data_provider.realtime_types import ChipDistribution, get_chip_circuit_breaker


def _frame(prices, turnover):
    dates = pd.bdate_range(end="2026-10-26", periods=len(prices))
    return pd.DataFrame(
        {
            "date": dates,
            "high": [price * 1.01 for price in prices],
            "low": [price * 0.99 for price in prices],
            "close": prices,
            "turn": turnover,
            "tradestatus": "1",
        }
    )


STABLE_FRAME = _frame([10.0] * 500, 2.0)
UNSTABLE_FRAME = _frame([10.0] * 350 + [20.0] * 150, 0.1)


class _NoneChipFetcher:
    name = "NoneChipFetcher"
    priority = 0

    def get_chip_distribution(self, stock_code: str):
        return None


class _ResultChipFetcher:
    name = "ResultChipFetcher"
    priority = 0

    def __init__(self, chip):
        self.chip = chip

    def get_chip_distribution(self, stock_code: str):
        return self.chip


class _FakeBaostockFetcher:
    name = "BaostockFetcher"
    priority = 3

    def __init__(self, frame):
        self.frame = frame
        self.calls = 0

    def get_daily_history_with_turnover(self, stock_code, start_date, end_date):
        self.calls += 1
        return self.frame


class TestLocalChipFallback(unittest.TestCase):
    def setUp(self):
        get_chip_circuit_breaker().reset()

    def test_stable_windows_return_reference_chip(self):
        chip = build_local_chip_distribution_from_frame(STABLE_FRAME, "600519")

        self.assertIsNotNone(chip)
        self.assertEqual(chip.source, LOCAL_CHIP_SOURCE)
        self.assertTrue(0.3 <= chip.profit_ratio <= 0.7)
        self.assertAlmostEqual(chip.avg_cost, 10.0, delta=0.3)
        self.assertLessEqual(chip.cost_90_low, chip.cost_70_low)
        self.assertLessEqual(chip.cost_70_high, chip.cost_90_high)

    def test_unstable_windows_return_none(self):
        chip = build_local_chip_distribution_from_frame(UNSTABLE_FRAME, "601288")

        self.assertIsNone(chip)

    def test_manager_uses_local_fallback_after_real_providers_fail(self):
        fake_baostock = _FakeBaostockFetcher(STABLE_FRAME)
        manager = DataFetcherManager(fetchers=[_NoneChipFetcher(), fake_baostock])

        with patch("src.config.get_config", return_value=SimpleNamespace(enable_chip_distribution=True)):
            chip = manager.get_chip_distribution("600519")

        self.assertIsNotNone(chip)
        self.assertEqual(chip.source, LOCAL_CHIP_SOURCE)
        self.assertEqual(fake_baostock.calls, 1)

    def test_manager_treats_zero_placeholder_as_failure(self):
        placeholder = ChipDistribution(
            code="600519",
            profit_ratio=0.0,
            avg_cost=10.0,
            concentration_90=0.0,
            concentration_70=0.0,
        )
        fake_baostock = _FakeBaostockFetcher(STABLE_FRAME)
        manager = DataFetcherManager(
            fetchers=[_ResultChipFetcher(placeholder), fake_baostock]
        )

        with patch("src.config.get_config", return_value=SimpleNamespace(enable_chip_distribution=True)):
            chip = manager.get_chip_distribution("600519")

        self.assertIsNotNone(chip)
        self.assertEqual(chip.source, LOCAL_CHIP_SOURCE)
        self.assertEqual(fake_baostock.calls, 1)

    def test_manager_skips_local_fallback_when_unstable(self):
        fake_baostock = _FakeBaostockFetcher(UNSTABLE_FRAME)
        manager = DataFetcherManager(fetchers=[_NoneChipFetcher(), fake_baostock])

        with patch("src.config.get_config", return_value=SimpleNamespace(enable_chip_distribution=True)):
            chip = manager.get_chip_distribution("601288")

        self.assertIsNone(chip)
        self.assertEqual(fake_baostock.calls, 1)

    def test_manager_skips_local_fallback_for_hk_and_etf(self):
        fake_baostock = _FakeBaostockFetcher(STABLE_FRAME)
        manager = DataFetcherManager(fetchers=[_NoneChipFetcher(), fake_baostock])

        with patch("src.config.get_config", return_value=SimpleNamespace(enable_chip_distribution=True)):
            self.assertIsNone(manager.get_chip_distribution("00700"))
            self.assertIsNone(manager.get_chip_distribution("510300"))

        self.assertEqual(fake_baostock.calls, 0)


if __name__ == "__main__":
    unittest.main()
