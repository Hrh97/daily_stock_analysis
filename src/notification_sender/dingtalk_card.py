# -*- coding: utf-8 -*-
"""Build full-detail, table-free DingTalk actionCards from the markdown report."""

from __future__ import annotations

import re
from typing import Dict, List, Optional

from src.formatters import chunk_content_by_max_bytes

_SUMMARY_RE = re.compile(
    r"^(?P<emoji>🟢|🟡|🟠|🔴|⚪|⚫|🔵|🟣|🟤)\s+\*\*(?P<name>.+?)\((?P<code>[^)]+)\)\*\*\s*[:：]\s*"
    r"(?P<action>[^|｜]+?)\s*[|｜]\s*评分\s*(?P<score>\d+)"
)
_DATE_RE = re.compile(r"^#\s+.*?(\d{4}-\d{2}-\d{2}).*$", re.M)
_CARD_MAX_BYTES = 18500
_LABEL_HEADERS = ("指标", "点位", "项目", "名称", "日期", "检查项", "情况")


def _parse_summary(report: str) -> List[Dict[str, str]]:
    stocks: List[Dict[str, str]] = []
    for line in report.splitlines():
        match = _SUMMARY_RE.match(line.strip())
        if match:
            stocks.append(match.groupdict())
    return stocks


def _split_table_row(line: str) -> List[str]:
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [cell.strip() for cell in stripped.split("|")]


def _is_table_separator(line: str) -> bool:
    stripped = line.strip()
    if not stripped.startswith("|"):
        return False
    cells = _split_table_row(stripped)
    return bool(cells) and all(cell and set(cell) <= set("-: ") for cell in cells)


def _render_table(header: List[str], rows: List[List[str]]) -> List[str]:
    is_label_table = len(header) == 2 and any(
        keyword in header[0] for keyword in _LABEL_HEADERS
    )
    if is_label_table:
        rendered = []
        for row in rows:
            left = row[0] if len(row) > 0 else ""
            right = row[1] if len(row) > 1 else ""
            left = left.replace("**", "")
            if left and right:
                rendered.append(f"**{left}**：{right}")
            elif right:
                rendered.append(right)
        return rendered

    if len(rows) == 1:
        parts = [
            f"**{column}** {value}"
            for column, value in zip(header, rows[0])
            if value
        ]
        return ["｜".join(parts)] if parts else []

    rendered = []
    for row in rows:
        parts = [
            f"**{column}** {value}"
            for column, value in zip(header, row)
            if value
        ]
        if parts:
            rendered.append("- " + "｜".join(parts))
    return rendered


def _convert_tables(text: str) -> str:
    """Turn markdown tables into key/value lines, since DingTalk does not render tables."""
    lines = text.splitlines()
    output: List[str] = []
    index = 0
    in_fence = False
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            output.append(line)
            index += 1
            continue
        if (
            not in_fence
            and stripped.startswith("|")
            and index + 1 < len(lines)
            and _is_table_separator(lines[index + 1])
        ):
            header = _split_table_row(line)
            index += 2
            rows: List[List[str]] = []
            while (
                index < len(lines)
                and lines[index].strip().startswith("|")
                and not _is_table_separator(lines[index])
            ):
                rows.append(_split_table_row(lines[index]))
                index += 1
            rendered = _render_table(header, rows)
            if rendered:
                if output and output[-1].strip():
                    output.append("")
                output.extend(rendered)
                output.append("")
            continue
        output.append(line)
        index += 1
    return re.sub(r"\n{3,}", "\n\n", "\n".join(output)).strip()


def _card_title(report: str, stocks: List[Dict[str, str]]) -> str:
    if len(stocks) == 1:
        stock = stocks[0]
        return (
            f"{stock['emoji']} {stock['name']} {stock['code']} · "
            f"{stock['action']}（评分{stock['score']}）"
        )
    date_match = _DATE_RE.search(report)
    date_text = date_match.group(1) if date_match else ""
    prefix = f"{date_text} " if date_text else ""
    return f"{prefix}决策仪表盘 · {len(stocks)}只持仓"


def build_dingtalk_cards(
    report: str, max_bytes: int = _CARD_MAX_BYTES
) -> Optional[List[Dict[str, str]]]:
    """Return full-detail actionCards, or None when the report has no stock summary."""
    if not report or "分析结果摘要" not in report:
        return None
    stocks = _parse_summary(report)
    if not stocks:
        return None

    body = report
    heading_match = re.match(r"^#\s+.+\n+", body)
    if heading_match:
        body = body[heading_match.end():]
    body = _convert_tables(body)
    chunks = [
        chunk
        for chunk in chunk_content_by_max_bytes(body, max_bytes=max_bytes)
        if chunk.strip()
    ]
    if not chunks:
        return None

    base_title = _card_title(report, stocks)
    cards: List[Dict[str, str]] = []
    for index, chunk in enumerate(chunks):
        title = base_title
        if len(chunks) > 1:
            title = f"{base_title} ({index + 1}/{len(chunks)})"
        cards.append({"title": title[:100], "text": chunk})
    return cards
