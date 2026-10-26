import unittest

from src.notification_sender.dingtalk_card import build_dingtalk_cards


SINGLE_STOCK_REPORT = """# 🎯 2026-10-22 决策仪表盘

> 共分析 **1** 只股票 | 🟢买入:0 🟡观望:0 🔴卖出:1

## 📊 分析结果摘要

🟠 **比亚迪(002594)**: 减仓 | 评分 26 | 看空

---

## 🟠 比亚迪 (002594)

> **一句话决策**: 空头排列资金流出，持仓者反弹减仓，空仓者观望

### 📈 当日行情

| 收盘 | 昨收 | 开盘 | 最高 | 最低 | 涨跌幅 | 涨跌额 | 振幅 | 成交量 | 成交额 |
|------|------|------|------|------|-------|-------|------|--------|--------|
| 80.02 | 80.70 | 80.71 | 81.45 | 79.71 | -0.84% | -0.68 | 2.16% | 2646.31 万股 | 21.23 亿元 |

### 📊 数据透视

| 价格指标 | 当前价 |
|---------|------|
| 当前价 | 80.02 |
| MA5 | 81.91 |
| MA20 | 83.33 |

### 🎯 作战计划

| 操作点位 | 当前价 |
|---------|------|
| 🎯 理想买入点 | 暂无理想买点 |
| 🛑 止损位 | 79.70元 |

| 持仓情况 | 操作建议 |
|---------|------|
| 🆕 **空仓者** | 观望，严禁抄底 |
| 💼 **持仓者** | 反弹减仓 |

**💰 仓位建议**: 建议仓位：持仓者降至3成以下
"""


class TestDingtalkCard(unittest.TestCase):
    def test_converts_tables_and_keeps_full_content(self):
        cards = build_dingtalk_cards(SINGLE_STOCK_REPORT)

        self.assertIsNotNone(cards)
        self.assertEqual(len(cards), 1)
        card = cards[0]
        self.assertIn("比亚迪", card["title"])
        self.assertIn("减仓", card["title"])
        text = card["text"]
        self.assertIn("## 📊 分析结果摘要", text)
        self.assertIn("### 🎯 作战计划", text)
        self.assertIn("**收盘** 80.02", text)
        self.assertIn("**🛑 止损位**：79.70元", text)
        self.assertIn("**🆕 空仓者**：观望，严禁抄底", text)
        self.assertNotIn("****", text)
        self.assertIn("建议仓位：持仓者降至3成以下", text)
        self.assertNotIn("|------", text)
        self.assertNotIn("\n|", text)

    def test_watch_summary_with_white_circle_builds_card(self):
        report = SINGLE_STOCK_REPORT.replace(
            "🟠 **比亚迪(002594)**: 减仓 | 评分 26 | 看空",
            "⚪ **比亚迪(002594)**: 观望 | 评分 50 | 震荡",
        ).replace("## 🟠 比亚迪", "## ⚪ 比亚迪")

        cards = build_dingtalk_cards(report)

        self.assertIsNotNone(cards)
        self.assertIn("观望", cards[0]["title"])

    def test_multi_stock_title_uses_date_and_count(self):
        report = SINGLE_STOCK_REPORT.replace(
            "🟠 **比亚迪(002594)**: 减仓 | 评分 26 | 看空",
            "🟠 **比亚迪(002594)**: 减仓 | 评分 26 | 看空\n"
            "🟢 **招商银行(600036)**: 买入 | 评分 80 | 看多",
        )

        cards = build_dingtalk_cards(report)

        self.assertIsNotNone(cards)
        self.assertIn("2026-10-22", cards[0]["title"])
        self.assertIn("2只持仓", cards[0]["title"])

    def test_long_report_splits_into_numbered_cards(self):
        filler = "\n".join(
            f"- 检查项{i}：这是一段用来撑大报告体积的详细说明文字，确保超过单张卡片限制"
            for i in range(400)
        )
        report = SINGLE_STOCK_REPORT + "\n### ✅ 检查清单\n\n" + filler + "\n"

        cards = build_dingtalk_cards(report)

        self.assertIsNotNone(cards)
        self.assertGreaterEqual(len(cards), 2)
        for index, card in enumerate(cards):
            self.assertLessEqual(len(card["text"].encode("utf-8")), 18500)
            self.assertIn(f"({index + 1}/{len(cards)})", card["title"])
            self.assertTrue(card["text"].strip())

    def test_market_review_returns_none(self):
        self.assertIsNone(build_dingtalk_cards("# 🎯 Market Review\n\nBody"))

    def test_report_without_stock_summary_returns_none(self):
        self.assertIsNone(build_dingtalk_cards("# 🎯 2026-10-22 决策仪表盘\n\n无摘要"))


if __name__ == "__main__":
    unittest.main()
