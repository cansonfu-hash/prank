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

from . import config
from .dingtalk_client import DwsError, list_messages, send_message
from .summarizer import render_markdown, summarize_messages


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="dingtalk_summarizer",
        description="拉取钉钉群消息，使用 Claude 进行汇总与关键信息提取。",
    )
    p.add_argument(
        "--conversation-id",
        "-c",
        required=True,
        help="钉钉群会话 ID（dws 中的 --conversation-id）",
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


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        print(f"· 正在拉取会话 {args.conversation_id} 的消息 …", file=sys.stderr)
        messages = list_messages(args.conversation_id, limit=args.limit)
    except DwsError as exc:
        print(f"[错误] 拉取消息失败：\n{exc}", file=sys.stderr)
        return 2

    if not messages:
        print("[提示] 没有拉取到任何消息。", file=sys.stderr)
        return 1

    print(f"· 已拉取 {len(messages)} 条消息，正在调用 {args.model} 进行汇总 …",
          file=sys.stderr)
    try:
        info = summarize_messages(messages, model=args.model)
    except Exception as exc:  # noqa: BLE001 - 给用户一个清晰的错误出口
        print(f"[错误] 调用模型失败：{exc}", file=sys.stderr)
        return 3

    markdown = render_markdown(info, args.conversation_id, len(messages))

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(markdown)
        print(f"· Markdown 汇总已写入 {args.output}", file=sys.stderr)
    else:
        print(markdown)

    if args.json_path:
        with open(args.json_path, "w", encoding="utf-8") as f:
            f.write(info.model_dump_json(indent=2, exclude_none=False))
        print(f"· 结构化结果已写入 {args.json_path}", file=sys.stderr)

    if args.send_back:
        try:
            send_message(args.conversation_id, markdown)
            print("· 汇总已回传到群里。", file=sys.stderr)
        except DwsError as exc:
            print(f"[错误] 回传失败：{exc}", file=sys.stderr)
            return 4

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
