# -*- coding: utf-8 -*-
import time
import hmac
import hashlib
import base64
import urllib.parse
import requests
import logging
from typing import Optional

from src.config import Config
from src.formatters import chunk_content_by_max_bytes, strip_hidden_markdown_metadata  # <-- 引入项目内置的切片器
from src.notification_sender.dingtalk_card import build_dingtalk_cards

logger = logging.getLogger(__name__)

class DingtalkSender:
    def __init__(self, config: Config):
        self.config = config
        self.webhook_url = config.dingtalk_webhook_url
        self.secret = config.dingtalk_secret

    def _card_settings(self):
        card_enabled = bool(getattr(self.config, "dingtalk_card_enabled", True))
        report_url = (getattr(self.config, "dingtalk_report_url", None) or "").strip()
        return card_enabled, report_url

    def _build_signed_url(self) -> str:
        if not self.secret:
            return self.webhook_url
        timestamp = str(round(time.time() * 1000))
        secret_enc = self.secret.encode('utf-8')
        string_to_sign = f'{timestamp}\n{self.secret}'
        string_to_sign_enc = string_to_sign.encode('utf-8')
        hmac_code = hmac.new(secret_enc, string_to_sign_enc, digestmod=hashlib.sha256).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
        separator = "&" if "?" in self.webhook_url else "?"
        return f"{self.webhook_url}{separator}timestamp={timestamp}&sign={sign}"

    def _send_action_card(
        self,
        url: str,
        title: str,
        text: str,
        report_url: str,
        timeout_seconds: int,
    ) -> bool:
        card = {
            "title": title,
            "text": text,
            "btnOrientation": "0",
            "singleTitle": "打开分析工作台",
            "singleURL": report_url,
        }
        payload = {"msgtype": "actionCard", "actionCard": card}
        try:
            response = requests.post(
                url,
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=timeout_seconds,
            )
            response.raise_for_status()
            result = response.json()
            if result.get("errcode") == 0:
                logger.info("钉钉卡片发送成功")
                return True
            logger.error(f"钉钉卡片发送失败 (DingTalk API error): {result}")
            return False
        except Exception as e:
            logger.error(f"发送钉钉卡片异常 (Failed to send DingTalk actionCard): {e}")
            return False

    def _send_markdown_text(
        self,
        url: str,
        text: str,
        display_title: str,
        timeout_seconds: int,
    ) -> bool:
        payload = {
            "msgtype": "markdown",
            "markdown": {
                "title": display_title,
                "text": text,
            },
        }
        try:
            response = requests.post(
                url,
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=timeout_seconds,
            )
            response.raise_for_status()
            result = response.json()
            if result.get("errcode") == 0:
                logger.info("钉钉 Markdown 消息发送成功")
                return True
            logger.error(f"钉钉 Markdown 消息发送失败 (DingTalk API error): {result}")
            return False
        except Exception as e:
            logger.error(f"发送钉钉 Markdown 消息异常 (Failed to send DingTalk markdown): {e}")
            return False

    def _send_markdown_report(
        self,
        url: str,
        content: str,
        title: str,
        timeout_seconds: int,
    ) -> bool:
        # 限制标题长度，防止极端长标题吃掉过多 JSON 字节预算
        safe_title = (title[:100] + "...") if title and len(title) > 100 else title
        # 预留 1000 bytes 的安全预算，用于 JSON 结构、标题和分页后缀的额外开销
        chunks = chunk_content_by_max_bytes(content, max_bytes=19000)
        all_success = True

        for index, chunk in enumerate(chunks):
            text = f"### {safe_title}\n\n{chunk}" if index == 0 and safe_title else chunk

            display_title = safe_title or "通知 (Notification)"
            if len(chunks) > 1:
                display_title = f"{display_title} ({index + 1}/{len(chunks)})"

            if not self._send_markdown_text(url, text, display_title, timeout_seconds):
                all_success = False

            if len(chunks) > 1 and index < len(chunks) - 1:
                time.sleep(0.5)

        return all_success

    def send_to_dingtalk(self, content: str, title: str = "", timeout_seconds: int = 10) -> bool:
        """发送 Markdown/卡片消息到钉钉群 (Send DingTalk message)"""
        if not self.webhook_url:
            return False
        sanitized_content = strip_hidden_markdown_metadata(content).strip()

        # 1. 签名逻辑 (Security Signature)
        url = self._build_signed_url()

        # 2. 优先发送完整 actionCard（去表格 + 自动分条 + 完整报告按钮）
        card_enabled, report_url = self._card_settings()
        if card_enabled and report_url:
            cards = build_dingtalk_cards(sanitized_content)
            if cards:
                all_success = True
                use_card = True
                for index, card in enumerate(cards):
                    if use_card:
                        if self._send_action_card(
                            url,
                            card["title"],
                            card["text"],
                            report_url,
                            timeout_seconds,
                        ):
                            if index < len(cards) - 1:
                                time.sleep(0.5)
                            continue
                        logger.warning("钉钉 actionCard 发送失败，后续分段回退为 Markdown")
                        use_card = False
                    if not self._send_markdown_text(
                        url,
                        card["text"],
                        card["title"],
                        timeout_seconds,
                    ):
                        all_success = False
                    if index < len(cards) - 1:
                        time.sleep(0.5)
                return all_success

        # 3. 非股票报告或未启用卡片时，按原 Markdown 分段发送
        return self._send_markdown_report(url, sanitized_content, title, timeout_seconds)
