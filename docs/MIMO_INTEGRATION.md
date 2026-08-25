# MiMo V2.5 Pro 接入与 Phase 1 实际运行

## 适配结论

固定上游的 `docs/CUSTOMIZATION.md` 允许把预配置的 chat model 实例直接传给 Agent factory，以获得完整模型参数控制。Open SWE 自带 `make_model("openai:...")` 默认启用 OpenAI Responses API；MiMo 使用 OpenAI-compatible Chat Completions，因此本项目不走该默认路由，而是构造：

- `langchain_openai.ChatOpenAI`
- model：`mimo-v2.5-pro`
- base URL：`https://api.xiaomimimo.com/v1`
- `use_responses_api=False`
- temperature：`0.0`
- max tokens：`4096`
- retries：`0`

API Key 只从 `MIMO_API_KEY` 读取，不进入源码、配置、fixture、Prompt 或 Git。当前适配器位于 `src/open_swe_review_agent/mimo.py`。

## 真实付费预检（已完成）

预检不是 Review benchmark，只验证 MiMo 能返回一个语义精确的单 Tool Call。Phase 1 已执行并通过：实际模型为 `mimo-v2.5-pro`，finish reason 为 `tool_calls`，Tool Call 数为 1，总计 325 Tokens。

```bash
cd /home/zhengwenyi/projects/open-swe-github-review-agent
source .venv/bin/activate

read -rsp "MiMo API Key: " MIMO_API_KEY
echo
export MIMO_API_KEY
export MIMO_ACCOUNT_TYPE=PAY_AS_YOU_GO
export OPEN_SWE_MIMO_ALLOW_NETWORK=YES_ONCE

python scripts/run_mimo_preflight.py \
  --execute \
  --acknowledgement OPEN_SWE_PHASE1_MIMO_PREFLIGHT

unset MIMO_API_KEY OPEN_SWE_MIMO_ALLOW_NETWORK
```

离线状态检查不会联网：

```bash
python scripts/run_mimo_preflight.py --check
```

## Phase 1 真实 Review（已完成）

实际实现采用 Reviewer-compatible local slice：复用官方 Review Prompt 纪律、changed-line 约束和结构化 Tool Call，但没有运行完整官方 Pregel graph。真实执行命令为：

```bash
OPEN_SWE_MIMO_ALLOW_NETWORK=YES_ONCE \
MIMO_ACCOUNT_TYPE=PAY_AS_YOU_GO \
python scripts/run_phase1_mimo_review.py \
  --execute-once \
  --fixture fixtures/phase1_logic_error/fixture.json \
  --acknowledgement OPEN_SWE_PHASE1_FIXED_DIFF_REVIEW
```

运行结果为 `PASS`：核心缺陷召回 `1/1`，虚假 Finding `0`，Review 使用 1,484 Tokens、耗时 10.484 秒。没有调用 GitHub 写 API、发布评论、修改代码或自动重试。
