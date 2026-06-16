"""调用 Claude 对钉钉群消息做汇总 + 关键信息提取。

设计：
- 普通规模：一次 `messages.parse` 调用，用 Pydantic 模型约束结构化输出，
  同时拿到"摘要 + 结构化关键信息"。
- 超大规模：先把消息分块做"粗摘要"（map），再对粗摘要做最终结构化汇总（reduce），
  避免一次性塞入超长上下文。
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Iterable

from pydantic import BaseModel, Field

from . import config
from .dingtalk_client import Message

if TYPE_CHECKING:  # 仅类型检查时需要，运行期惰性导入，便于无 SDK 环境下测试纯函数
    import anthropic


# --------------------------- 结构化输出模型 ---------------------------
class ActionItem(BaseModel):
    task: str = Field(description="待办/行动项的具体内容")
    owner: str = Field(default="", description="负责人（如果消息中有提到）")
    due: str = Field(default="", description="截止时间（如果提到）")


class KeyInfo(BaseModel):
    """对一段群聊的汇总与关键信息提取结果。"""

    summary: str = Field(description="对整段对话的简洁中文总结，3-6 句话")
    topics: list[str] = Field(default_factory=list, description="讨论到的主要话题")
    decisions: list[str] = Field(default_factory=list, description="达成的结论 / 决定")
    action_items: list[ActionItem] = Field(
        default_factory=list, description="需要跟进的待办事项 / 行动项"
    )
    open_questions: list[str] = Field(
        default_factory=list, description="尚未解决或悬而未决的问题"
    )
    important_dates: list[str] = Field(
        default_factory=list, description="提到的重要时间点 / 日期 / 排期"
    )
    mentioned_links: list[str] = Field(
        default_factory=list, description="消息中出现的链接 / 文档地址"
    )


SYSTEM_PROMPT = (
    "你是一名高效的中文办公助理，擅长从钉钉群聊记录中提炼重点。"
    "请客观、准确地总结对话，不要编造聊天记录里没有的信息；"
    "无法确定的字段就留空。所有输出使用简体中文。"
)


def _build_transcript(messages: Iterable[Message]) -> str:
    return "\n".join(m.as_line() for m in messages if m.text)


def _chunk_messages(messages: list[Message]) -> list[list[Message]]:
    chunks: list[list[Message]] = []
    current: list[Message] = []
    size = 0
    for m in messages:
        line_len = len(m.as_line()) + 1
        if current and size + line_len > config.CHUNK_CHAR_SIZE:
            chunks.append(current)
            current, size = [], 0
        current.append(m)
        size += line_len
    if current:
        chunks.append(current)
    return chunks


def _summarize_chunk(client: "anthropic.Anthropic", model: str, transcript: str) -> str:
    """对单个分块产出一段纯文本粗摘要（map 阶段）。"""
    with client.messages.stream(
        model=model,
        max_tokens=config.MAX_TOKENS,
        system=SYSTEM_PROMPT,
        thinking={"type": "adaptive"},
        messages=[
            {
                "role": "user",
                "content": (
                    "下面是一段钉钉群聊记录的片段。请用中文提炼这一片段的要点，"
                    "包括：讨论的话题、达成的结论、待办事项、悬而未决的问题、"
                    "重要时间点和链接。用简洁的要点列表输出。\n\n"
                    f"<chat>\n{transcript}\n</chat>"
                ),
            }
        ],
    ) as stream:
        message = stream.get_final_message()
    return "".join(b.text for b in message.content if b.type == "text")


def summarize_messages(
    messages: list[Message],
    model: str | None = None,
    client: "anthropic.Anthropic | None" = None,
) -> KeyInfo:
    """对群消息做汇总与关键信息提取，返回结构化结果。"""
    import anthropic

    model = model or config.DEFAULT_MODEL
    client = client or anthropic.Anthropic()

    if not [m for m in messages if m.text]:
        return KeyInfo(summary="（没有可供总结的文本消息）")

    transcript = _build_transcript(messages)

    # 超大记录：先 map（分块粗摘要）再 reduce（结构化汇总）。
    if len(transcript) > config.CHUNK_CHAR_THRESHOLD:
        partials = [
            _summarize_chunk(client, model, _build_transcript(chunk))
            for chunk in _chunk_messages(messages)
        ]
        source_label = "下面是同一个钉钉群多段聊天记录的分段要点（已按时间顺序排列）"
        source_block = "\n\n".join(
            f"== 片段 {i + 1} ==\n{p}" for i, p in enumerate(partials)
        )
    else:
        source_label = "下面是一段钉钉群的完整聊天记录"
        source_block = transcript

    user_prompt = (
        f"{source_label}：\n\n<chat>\n{source_block}\n</chat>\n\n"
        "请综合以上内容，给出整体总结并提取关键信息。"
    )

    response = client.messages.parse(
        model=model,
        max_tokens=config.MAX_TOKENS,
        system=SYSTEM_PROMPT,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": user_prompt}],
        output_format=KeyInfo,
    )
    parsed = response.parsed_output
    if parsed is None:  # 极端情况下解析失败，兜底返回原始文本
        text = next((b.text for b in response.content if b.type == "text"), "")
        return KeyInfo(summary=text or "（模型未返回结构化结果）")
    return parsed


# --------------------------- 渲染为 Markdown ---------------------------
def _render_sections(info: KeyInfo, base_level: int) -> list[str]:
    """渲染"总结 + 各关键信息"小节，标题层级从 base_level 开始。"""
    h = "#" * base_level
    lines: list[str] = [f"{h} 总结", "", info.summary or "（无）", ""]

    def section(title: str, items: list[str]) -> None:
        lines.append(f"{h} {title}")
        lines.append("")
        lines.extend(f"- {x}" for x in items) if items else lines.append("（无）")
        lines.append("")

    section("主要话题", info.topics)
    section("结论 / 决定", info.decisions)

    lines.append(f"{h} 待办事项")
    lines.append("")
    if info.action_items:
        for a in info.action_items:
            extra = []
            if a.owner:
                extra.append(f"负责人：{a.owner}")
            if a.due:
                extra.append(f"截止：{a.due}")
            suffix = f"（{'；'.join(extra)}）" if extra else ""
            lines.append(f"- [ ] {a.task}{suffix}")
    else:
        lines.append("（无）")
    lines.append("")

    section("待解决的问题", info.open_questions)
    section("重要时间点", info.important_dates)
    section("相关链接", info.mentioned_links)
    return lines


def render_markdown(info: KeyInfo, conversation_id: str, message_count: int) -> str:
    """单个群的完整 Markdown 报告。"""
    lines = [
        "# 钉钉群消息汇总",
        "",
        f"- 会话 ID：`{conversation_id}`",
        f"- 消息条数：{message_count}",
        "",
        *_render_sections(info, base_level=2),
    ]
    return "\n".join(lines).rstrip() + "\n"


def render_combined(results: list[tuple[str, int, KeyInfo]]) -> str:
    """多个群合并为一份报告：一个总标题 + 每群一节。

    Args:
        results: [(conversation_id, message_count, KeyInfo), ...]
    """
    if len(results) == 1:
        cid, count, info = results[0]
        return render_markdown(info, cid, count)

    lines = [f"# 钉钉群消息汇总（共 {len(results)} 个群）", ""]
    for cid, count, info in results:
        lines.append(f"## 群 `{cid}`（{count} 条）")
        lines.append("")
        lines.extend(_render_sections(info, base_level=3))
    return "\n".join(lines).rstrip() + "\n"
