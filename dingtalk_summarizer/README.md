# 钉钉群消息汇总助手

基于 [DingTalk Workspace CLI (`dws`)](https://github.com/DingTalk-Real-AI/dingtalk-workspace-cli/blob/main/README_zh.md) 拉取钉钉群消息，再用 **Claude（Opus 4.8）** 对消息进行**汇总**与**关键信息提取**。

## 功能

- 通过 `dws` 拉取指定群（会话）的历史消息，自动翻页拉全；
- 调用 Claude 生成：
  - 整体中文**总结**；
  - 结构化**关键信息**：主要话题、结论/决定、待办事项（含负责人/截止时间）、待解决问题、重要时间点、相关链接；
- 输出 Markdown 报告，可选导出结构化 JSON；
- 可选把汇总结果**回传到群里**；
- 聊天记录过长时自动「分块粗摘要 → 汇总」，避免超长上下文。

## 架构

```
钉钉群  ──(dws chat message list)──▶  dingtalk_client.py  ──▶  规整后的消息列表
                                                                    │
                                                                    ▼
                                            summarizer.py  ──(Claude messages.parse)──▶  结构化 KeyInfo
                                                                    │
                                                                    ▼
                                            main.py  ──▶  Markdown / JSON / 回传到群
```

| 文件 | 作用 |
|------|------|
| `dingtalk_client.py` | 封装 `dws` 命令，拉取/发送消息，并把多种返回结构规整成统一的 `Message` |
| `summarizer.py` | 用 Claude 做汇总 + 结构化关键信息提取（Pydantic 约束输出），并渲染 Markdown |
| `main.py` | 命令行入口 |
| `config.py` | 模型、阈值等配置（支持环境变量覆盖） |

## 安装

### 1. 安装并登录 dws

```bash
# macOS / Linux
curl -fsSL https://raw.githubusercontent.com/DingTalk-Real-AI/dingtalk-workspace-cli/main/scripts/install.sh | sh

# 登录（无浏览器环境用 --device）
dws auth login            # 或: dws auth login --device
dws auth status           # 确认已登录
```

> 凭证由 dws 自行加密存储（不落盘明文、Token 不出域），本项目不接触任何钉钉密钥。

### 2. 安装 Python 依赖

```bash
cd dingtalk_summarizer
pip install -r requirements.txt
```

### 3. 配置 Claude API Key

```bash
cp .env.example .env        # 然后填入你的 key，或直接 export：
export ANTHROPIC_API_KEY=sk-ant-xxxx
```

## 用法

先拿到目标群的会话 ID（`dws` 中的 `--conversation-id`）。可以用 dws 浏览自己所在的群/会话来获取。

在项目上一级目录运行（让 `dingtalk_summarizer` 作为包被导入）：

```bash
# 拉取全部消息并打印 Markdown 汇总
python -m dingtalk_summarizer --conversation-id <CONV_ID>

# 只看最近 200 条，写入文件
python -m dingtalk_summarizer -c <CONV_ID> -n 200 -o report.md

# 同时导出结构化 JSON
python -m dingtalk_summarizer -c <CONV_ID> --json result.json

# 汇总后把结果发回群里
python -m dingtalk_summarizer -c <CONV_ID> --send-back

# 指定模型
python -m dingtalk_summarizer -c <CONV_ID> -m claude-opus-4-8
```

### 参数

| 参数 | 说明 |
|------|------|
| `-c, --conversation-id` | （必填）钉钉群会话 ID |
| `-n, --limit` | 最多拉取的消息条数；不填则自动翻页拉全部 |
| `-m, --model` | Claude 模型，默认 `claude-opus-4-8` |
| `-o, --output` | 把 Markdown 写入文件 |
| `--json` | 把结构化结果写入 JSON 文件 |
| `--send-back` | 把汇总作为消息发回群里 |

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `ANTHROPIC_API_KEY` | — | Claude API Key（必需） |
| `DINGTALK_SUMMARY_MODEL` | `claude-opus-4-8` | 默认模型 |
| `DWS_BIN` | `dws` | dws 可执行文件路径 |
| `DINGTALK_CHUNK_THRESHOLD` | `24000` | 触发分块汇总的字符阈值 |
| `DINGTALK_CHUNK_SIZE` | `16000` | 单个分块最大字符数 |
| `DINGTALK_MAX_TOKENS` | `16000` | 单次响应最大 token |

## 输出示例

```markdown
# 钉钉群消息汇总

- 会话 ID：`cidXXXXXXXX`
- 消息条数：128

## 总结
本周主要围绕 v2.0 发版排期与线上告警展开 ……

## 主要话题
- 发版排期
- 线上 5xx 告警定位

## 待办事项
- [ ] 修复支付回调超时（负责人：张三；截止：周五）
- [ ] 补充压测报告（负责人：李四）

## 重要时间点
- 6/20 灰度，6/23 全量
...
```

## 说明

- 模型默认使用 Claude Opus 4.8（`claude-opus-4-8`），采用自适应思考（adaptive thinking）；
- 关键信息提取使用结构化输出（JSON Schema 约束），保证字段稳定可解析；
- 助手被要求**不臆造**聊天里没有的信息，无法确定的字段留空。
