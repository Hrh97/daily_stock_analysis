# -*- coding: utf-8 -*-
"""Local chip-distribution fallback adapted from a-stock-data (Apache-2.0).

Source: https://github.com/simonlin1212/a-stock-data/blob/main/SKILL.md (§4.6)
The CYQ algorithm is adapted from that project. See docs/third-party-notices.md.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Optional

import numpy as np
import pandas as pd

from .realtime_types import ChipDistribution

logger = logging.getLogger(__name__)

LOCAL_CHIP_SOURCE = "本地推演筹码（参考）"
LOCAL_CHIP_DECAY = 1.0
LOCAL_CHIP_WINDOWS = (("6m", 180), ("1y", 365), ("2y", 730))
LOCAL_CHIP_BASE_WINDOW = "1y"
LOCAL_CHIP_MAX_PROFIT_SPREAD = 0.30
LOCAL_CHIP_FETCH_LOOKBACK_DAYS = 760
LOCAL_CHIP_MIN_ROWS = 20


def _triangular_weights(grid: np.ndarray, low: float, high: float, avg: float) -> np.ndarray:
    """当日筹码在价格网格上的三角分布权重（峰值在均价，面积归一）。"""
    w = np.zeros_like(grid)
    if not np.isfinite([low, high, avg]).all() or high < low:
        return w
    if high - low < 1e-9:
        w[np.argmin(np.abs(grid - low))] = 1.0
        return w
    avg = min(max(avg, low), high)
    left = (grid >= low) & (grid <= avg)
    right = (grid > avg) & (grid <= high)
    if avg - low > 1e-9:
        w[left] = (grid[left] - low) / (avg - low)
    else:
        w[left] = 1.0
    if high - avg > 1e-9:
        w[right] = (high - grid[right]) / (high - avg)
    else:
        w[right] = 1.0
    total = w.sum()
    if total > 0:
        return w / total
    w[np.argmin(np.abs(grid - avg))] = 1.0
    return w


def chip_distribution(df: pd.DataFrame, grid_size: int = 300, decay: float = 1.0) -> dict:
    """筹码分布 — df 需含 high/low/close/turn（turn 为百分数，0.31 表示 0.31%）。

    decay: 换手衰减系数。1.0=按真实换手率换手；同花顺口径常用 1.5~2.0。
    """
    need = {"date", "high", "low", "close", "turn"}
    missing = need - set(df.columns)
    if missing:
        raise ValueError(f"chip_distribution 缺少列: {sorted(missing)}")
    d = df.dropna(subset=["high", "low", "close", "turn"]).copy()
    d = d[d["high"] > 0]
    if d.empty:
        raise ValueError("chip_distribution: 有效行数为 0")
    d = d.sort_values("date").reset_index(drop=True)

    lo, hi = float(d["low"].min()), float(d["high"].max())
    pad = (hi - lo) * 0.02 or max(lo * 0.02, 0.01)
    grid = np.linspace(lo - pad, hi + pad, grid_size)

    # 首日必须播种为全部流通盘，否则短窗口会把少量换手错误归一化成 100%。
    chips = None
    for row in d.itertuples(index=False):
        t = float(row.turn) / 100.0 * decay
        t = min(max(t, 0.0), 1.0)
        avg = (float(row.high) + float(row.low) + float(row.close)) / 3.0
        w = _triangular_weights(grid, float(row.low), float(row.high), avg)
        if w.sum() <= 0:
            continue
        if chips is None:
            chips = w.copy()
            continue
        chips = chips * (1.0 - t) + w * t
    if chips is None:
        raise RuntimeError("chip_distribution: 所有交易日的价格区间都无效")

    total = chips.sum()
    if total <= 0:
        raise RuntimeError("chip_distribution: 筹码总量为 0")
    chips = chips / total

    price = float(d["close"].iloc[-1])
    cum = np.cumsum(chips)

    def price_at(q: float) -> float:
        return float(np.interp(q, cum, grid))

    p05, p15, p85, p95 = (price_at(q) for q in (0.05, 0.15, 0.85, 0.95))
    peak_i = int(np.argmax(chips))
    return {
        "price": price,
        "profit_ratio": float(chips[grid <= price].sum()),
        "avg_cost": float((grid * chips).sum()),
        "cost_90": (p05, p95),
        "cost_70": (p15, p85),
        "concentration_90": float((p95 - p05) / (p95 + p05)) if p95 + p05 else None,
        "concentration_70": float((p85 - p15) / (p85 + p15)) if p85 + p15 else None,
        "peak_price": float(grid[peak_i]),
        "histogram": [(float(pp), float(cc)) for pp, cc in zip(grid, chips) if cc > 1e-6],
    }


def build_local_chip_distribution_from_frame(
    df: pd.DataFrame,
    stock_code: str,
) -> Optional[ChipDistribution]:
    """Build a 1-year local CYQ result only when 6m/1y/2y windows agree."""
    if df is None or df.empty:
        return None
    required = {"date", "high", "low", "close", "turn"}
    if not required.issubset(df.columns):
        logger.debug("本地推演缺少列 %s: %s", stock_code, sorted(required - set(df.columns)))
        return None

    d = df.copy()
    if "tradestatus" in d.columns:
        d = d[d["tradestatus"].astype(str) == "1"]
    for col in ("high", "low", "close", "turn"):
        d[col] = pd.to_numeric(d[col], errors="coerce")
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    d = d.dropna(subset=["date", "high", "low", "close", "turn"])
    d = d[d["high"] > 0].sort_values("date")
    if len(d) < LOCAL_CHIP_MIN_ROWS:
        return None

    latest = d["date"].max()
    results: dict[str, dict[str, Any]] = {}
    for label, days in LOCAL_CHIP_WINDOWS:
        window = d[d["date"] >= latest - pd.Timedelta(days=days)]
        if len(window) < LOCAL_CHIP_MIN_ROWS:
            continue
        try:
            results[label] = chip_distribution(window, decay=LOCAL_CHIP_DECAY)
        except Exception as exc:
            logger.debug("本地推演窗口 %s 失败 %s: %s", label, stock_code, exc)

    base = results.get(LOCAL_CHIP_BASE_WINDOW)
    if base is None or len(results) < 2:
        return None

    profits = [float(item["profit_ratio"]) for item in results.values()]
    spread = max(profits) - min(profits)
    if spread > LOCAL_CHIP_MAX_PROFIT_SPREAD:
        logger.info(
            "[筹码分布] %s 本地推演跨窗口不稳定（获利盘极差 %.1f%%），跳过",
            stock_code,
            spread * 100,
        )
        return None

    avg_cost = float(base["avg_cost"])
    concentration_90 = float(base["concentration_90"] or 0.0)
    concentration_70 = float(base["concentration_70"] or 0.0)
    profit_ratio = float(base["profit_ratio"])
    if (
        not np.isfinite(profit_ratio)
        or not np.isfinite(avg_cost)
        or avg_cost <= 0
        or concentration_90 < 0
        or concentration_70 < 0
    ):
        return None

    return ChipDistribution(
        code=stock_code,
        date=latest.strftime("%Y-%m-%d"),
        source=LOCAL_CHIP_SOURCE,
        profit_ratio=profit_ratio,
        avg_cost=avg_cost,
        cost_90_low=float(base["cost_90"][0]),
        cost_90_high=float(base["cost_90"][1]),
        concentration_90=concentration_90,
        cost_70_low=float(base["cost_70"][0]),
        cost_70_high=float(base["cost_70"][1]),
        concentration_70=concentration_70,
    )


def build_local_chip_distribution(
    stock_code: str,
    baostock_fetcher: Any,
) -> Optional[ChipDistribution]:
    """Fetch baostock qfq daily bars and build the local CYQ fallback."""
    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=LOCAL_CHIP_FETCH_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    df = baostock_fetcher.get_daily_history_with_turnover(stock_code, start, end)
    return build_local_chip_distribution_from_frame(df, stock_code)
