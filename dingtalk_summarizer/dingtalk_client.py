"""通过 DingTalk Workspace CLI (`dws`) 获取/发送钉钉群消息。

参考：https://github.com/DingTalk-Real-AI/dingtalk-workspace-cli

本模块只负责调用 `dws` 命令并把它返回的 JSON 规整成统一结构，
不直接持有任何钉钉凭证——认证完全交给 `dws auth login`。
"""
from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any

from . import config

# 钉钉是国内时间，判断"今天"默认用东八区。
DEFAULT_TZ = "Asia/Shanghai"

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - 3.8 及以下
    ZoneInfo = None  # type: ignore[assignment]


def _tz(name: str = DEFAULT_TZ):
    if ZoneInfo is not None:
        try:
            return ZoneInfo(name)
        except Exception:  # noqa: BLE001 - 没有 tzdata 时兜底
            pass
    return timezone(timedelta(hours=8))  # 兜底 +08:00


class DwsError(RuntimeError):
    """`dws` 命令执行失败时抛出。"""


@dataclass
class Message:
    """规整后的单条群消息。"""

    sender: str
    text: str
    timestamp: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    def as_line(self) -> str:
        prefix = f"[{self.timestamp}] " if self.timestamp else ""
        return f"{prefix}{self.sender}: {self.text}"


def _ensure_dws_available() -> None:
    if shutil.which(config.DWS_BIN) is None and "/" not in config.DWS_BIN:
        raise DwsError(
            f"找不到 `{config.DWS_BIN}` 可执行文件。请先安装 DingTalk Workspace CLI：\n"
            "  curl -fsSL https://raw.githubusercontent.com/DingTalk-Real-AI/"
            "dingtalk-workspace-cli/main/scripts/install.sh | sh\n"
            "并执行 `dws auth login` 完成登录。"
        )


def _run_dws(args: list[str]) -> Any:
    """执行 `dws ... --format json` 并解析其标准输出为 Python 对象。"""
    _ensure_dws_available()
    cmd = [config.DWS_BIN, *args, "--format", "json"]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:  # pragma: no cover - 由 _ensure_dws_available 兜底
        raise DwsError(f"无法执行 dws：{exc}") from exc

    if proc.returncode != 0:
        raise DwsError(
            f"dws 命令执行失败（exit={proc.returncode}）：\n"
            f"  命令: {' '.join(cmd)}\n"
            f"  stderr: {proc.stderr.strip() or '(空)'}"
        )

    out = proc.stdout.strip()
    if not out:
        return {}
    try:
        return json.loads(out)
    except json.JSONDecodeError as exc:
        raise DwsError(f"dws 返回的内容不是合法 JSON：{out[:500]}") from exc


def _iter_message_objects(payload: Any) -> list[dict[str, Any]]:
    """从 dws 的多种可能返回结构中找到消息列表。"""
    if isinstance(payload, list):
        return [m for m in payload if isinstance(m, dict)]
    if isinstance(payload, dict):
        for key in ("messages", "data", "list", "items", "records", "result"):
            value = payload.get(key)
            if isinstance(value, list):
                return [m for m in value if isinstance(m, dict)]
            if isinstance(value, dict):
                # 例如 {"data": {"messages": [...]}}
                nested = _iter_message_objects(value)
                if nested:
                    return nested
    return []


def _first(d: dict[str, Any], *keys: str) -> str:
    for k in keys:
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
        if isinstance(v, (int, float)):
            return str(v)
    return ""


def _extract_text(msg: dict[str, Any]) -> str:
    """尽量从一条消息里抠出可读文本。

    钉钉消息体可能是 {"text": {"content": "..."}}、{"content": "..."}、
    或带 msgtype 的复合结构，这里逐层兜底。
    """
    # 直接的文本字段
    direct = _first(msg, "text", "content", "body", "msg")
    if direct:
        return direct

    # 嵌套：text.content / content.text 等
    for key in ("text", "content", "body", "data"):
        nested = msg.get(key)
        if isinstance(nested, dict):
            inner = _first(nested, "content", "text", "value", "title")
            if inner:
                return inner

    # 富文本 / markdown
    md = msg.get("markdown")
    if isinstance(md, dict):
        inner = _first(md, "text", "content", "title")
        if inner:
            return inner

    # 实在没有就返回类型提示，避免静默丢消息
    msgtype = _first(msg, "msgtype", "type", "messageType")
    return f"<{msgtype or '非文本消息'}>"


def _normalize(msg: dict[str, Any]) -> Message:
    sender = _first(
        msg,
        "senderNick",
        "senderName",
        "sender_nick",
        "senderId",
        "sender",
        "fromNick",
        "from",
        "userName",
        "userid",
    ) or "未知成员"
    timestamp = _first(
        msg,
        "createAt",
        "createTime",
        "created_at",
        "time",
        "timestamp",
        "msgCreateTime",
        "sendTime",
    )
    return Message(sender=sender, text=_extract_text(msg), timestamp=timestamp, raw=msg)


def list_messages(
    conversation_id: str,
    limit: int | None = None,
    page_all: bool = True,
) -> list[Message]:
    """拉取指定会话（群）的消息列表。

    Args:
        conversation_id: 群会话 ID（dws 中的 --conversation-id）。
        limit: 最多拉取的条数；为 None 时配合 page_all 自动翻页拉全部。
        page_all: 是否自动翻页拉取所有历史消息。
    """
    args = ["chat", "message", "list", "--conversation-id", conversation_id]
    if limit is not None:
        args += ["--page-limit", str(limit)]
    elif page_all:
        args.append("--page-all")

    payload = _run_dws(args)
    objs = _iter_message_objects(payload)
    messages = [_normalize(m) for m in objs]
    if limit is not None:
        messages = messages[:limit]
    return messages


def parse_timestamp(raw: str, tzname: str = DEFAULT_TZ) -> datetime | None:
    """把消息时间戳解析为带时区的 datetime；无法解析返回 None。

    兼容：毫秒/秒级 epoch，以及常见的字符串日期格式。
    """
    if not raw:
        return None
    tz = _tz(tzname)
    s = str(raw).strip()

    # 数字 epoch（秒或毫秒）
    cleaned = s.replace(".", "", 1)
    if cleaned.isdigit():
        val = float(s)
        if val > 1e12:  # 毫秒
            val /= 1000.0
        try:
            return datetime.fromtimestamp(val, tz)
        except (OverflowError, OSError, ValueError):
            return None

    # 常见字符串格式
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=tz)
        except ValueError:
            continue

    try:
        dt = datetime.fromisoformat(s)
        return dt.replace(tzinfo=tz) if dt.tzinfo is None else dt
    except ValueError:
        return None


def filter_by_date(
    messages: list[Message],
    target: date | None = None,
    tzname: str = DEFAULT_TZ,
) -> tuple[list[Message], int]:
    """筛选出指定日期（默认今天，东八区）的消息。

    Returns:
        (筛选后的消息, 时间戳无法解析而被排除的条数)
    """
    tz = _tz(tzname)
    if target is None:
        target = datetime.now(tz).date()
    kept: list[Message] = []
    unparsed = 0
    for m in messages:
        dt = parse_timestamp(m.timestamp, tzname)
        if dt is None:
            unparsed += 1
            continue
        if dt.astimezone(tz).date() == target:
            kept.append(m)
    return kept, unparsed


def send_message(conversation_id: str, text: str) -> None:
    """把文本消息发送回群里（用于回传汇总结果）。"""
    args = [
        "chat",
        "message",
        "send",
        "--conversation-id",
        conversation_id,
        "--text",
        text,
        "--yes",
    ]
    _run_dws(args)
