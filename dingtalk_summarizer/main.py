"""命令行入口：拉取钉钉群消息 -> 调用 Claude 汇总 -> 输出/回传。

用法示例：
    python -m dingtalk_summarizer --conversation-id <CONV_ID>
    python -m dingtalk_summarizer --conversation-id <CONV_ID> --limit 200 -o report.md
    python -m dingtalk_summarizer --conversation-id <CONV_ID> --send-back
    python -m dingtalk_summarizer --conversation-id <CONV_ID> --json result.json
"""
from __future__ import annotations

import argparse
import sys

import json

from . import config
from .dingtalk_client import DwsError, list_messages, send_message
from .summarizer import render_combined, render_markdown, summarize_messages


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="dingtalk_summarizer",
        description="拉取钉钉群消息，使用 Claude 进行汇总与关键信息提取。",
    )
    p.add_argument(
        "--conversation-id",
        "-c",
        action="append",
        required=True,
        metavar="CONV_ID",
        help="钉钉群会话 ID；可重复指定或用逗号分隔以一次汇总多个群",
    )
    p.add_argument(
        "--limit",
        "-n",
        type=int,
        default=None,
        help="最多拉取的消息条数；不指定则自动翻页拉取全部",
    )
    p.add_argument(
        "--model",
        "-m",
        default=config.DEFAULT_MODEL,
        help=f"使用的 Claude 模型（默认 {config.DEFAULT_MODEL}）",
    )
    p.add_argument(
        "--output",
        "-o",
        default=None,
        help="把 Markdown 汇总写入指定文件（不指定则打印到标准输出）",
    )
    p.add_argument(
        "--json",
        dest="json_path",
        default=None,
        help="把结构化结果（JSON）写入指定文件",
    )
    p.add_argument(
        "--send-back",
        action="store_true",
        help="把汇总结果作为消息发送回该群",
    )
    return p


def _expand_ids(raw: list[str]) -> list[str]:
    """把 ["a,b", "c"] 这种展开成 ["a", "b", "c"]，去重保序。"""
    ids: list[str] = []
    for item in raw:
        for part in item.split(","):
            part = part.strip()
            if part and part not in ids:
                ids.append(part)
    return ids


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    conversation_ids = _expand_ids(args.conversation_id)

    # (conversation_id, message_count, KeyInfo, per_group_markdown)
    results: list[tuple[str, int, object, str]] = []

    for cid in conversation_ids:
        try:
            print(f"· 正在拉取会话 {cid} 的消息 …", file=sys.stderr)
            messages = list_messages(cid, limit=args.limit)
        except DwsError as exc:
            print(f"[错误] 拉取会话 {cid} 失败：\n{exc}", file=sys.stderr)
            return 2

        if not messages:
            print(f"[提示] 会话 {cid} 没有拉取到任何消息，已跳过。", file=sys.stderr)
            continue

        print(
            f"· 会话 {cid}：已拉取 {len(messages)} 条消息，正在调用 {args.model} 汇总 …",
            file=sys.stderr,
        )
        try:
            info = summarize_messages(messages, model=args.model)
        except Exception as exc:  # noqa: BLE001 - 给用户一个清晰的错误出口
            print(f"[错误] 会话 {cid} 调用模型失败：{exc}", file=sys.stderr)
            return 3

        per_group_md = render_markdown(info, cid, len(messages))
        results.append((cid, len(messages), info, per_group_md))

    if not results:
        print("[提示] 没有任何群产生汇总。", file=sys.stderr)
        return 1

    combined = render_combined([(c, n, info) for c, n, info, _ in results])

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(combined)
        print(f"· Markdown 汇总已写入 {args.output}", file=sys.stderr)
    else:
        print(combined)

    if args.json_path:
        if len(results) == 1:
            payload = results[0][2].model_dump()
        else:
            payload = {cid: info.model_dump() for cid, _, info, _ in results}
        with open(args.json_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"· 结构化结果已写入 {args.json_path}", file=sys.stderr)

    if args.send_back:
        for cid, _, _, per_group_md in results:
            try:
                send_message(cid, per_group_md)
                print(f"· 汇总已回传到群 {cid}。", file=sys.stderr)
            except DwsError as exc:
                print(f"[错误] 回传到群 {cid} 失败：{exc}", file=sys.stderr)
                return 4

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
