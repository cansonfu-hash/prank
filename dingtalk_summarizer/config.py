"""集中管理项目配置（模型、阈值、dws 可执行文件路径等）。"""
from __future__ import annotations

import os

# 默认使用 Claude 当前最强的 Opus 模型。可通过环境变量覆盖。
DEFAULT_MODEL = os.environ.get("DINGTALK_SUMMARY_MODEL", "claude-opus-4-8")

# dws 可执行文件名（如果不在 PATH 中可设为绝对路径）。
DWS_BIN = os.environ.get("DWS_BIN", "dws")

# 当拼接后的聊天记录字符数超过该阈值时，先分块做"粗摘要"再汇总，
# 避免一次性把超长上下文塞进单次请求。
CHUNK_CHAR_THRESHOLD = int(os.environ.get("DINGTALK_CHUNK_THRESHOLD", "24000"))

# 单个分块的最大字符数。
CHUNK_CHAR_SIZE = int(os.environ.get("DINGTALK_CHUNK_SIZE", "16000"))

# 单次 LLM 响应的最大 token 数。
MAX_TOKENS = int(os.environ.get("DINGTALK_MAX_TOKENS", "16000"))
