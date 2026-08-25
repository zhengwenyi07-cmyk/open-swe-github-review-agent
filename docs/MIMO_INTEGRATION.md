# MiMo V2.5 Pro 接入与拟执行命令

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

## 先运行的真实付费预检（拟执行，当前未运行）

预检不是 Review benchmark，只验证 MiMo 能返回一个语义精确的单 Tool Call。复审并提交静态合同后，人工批准时才执行：

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

## Phase 1 真实 Smoke（拟执行路径，当前不可运行）

真实 Smoke 必须先完成一项很小的集成改动：将上述预配置 `ChatOpenAI` 实例注入固定 Commit 的官方 `get_reviewer_agent`，并把官方 publish 工具替换为本地只写 JSON/Markdown 的终点。该集成当前明确为 `NOT_IMPLEMENTED`，避免用本项目的 Fake workflow 冒充官方 Open SWE graph。

集成完成并通过离线测试后，拟执行接口冻结为：

```bash
OPEN_SWE_MIMO_ALLOW_NETWORK=YES_ONCE \
MIMO_ACCOUNT_TYPE=PAY_AS_YOU_GO \
python scripts/run_phase1_mimo_review.py \
  --execute-once \
  --fixture fixtures/phase1_logic_error/fixture.json \
  --acknowledgement OPEN_SWE_PHASE1_FIXED_DIFF_REVIEW
```

`scripts/run_phase1_mimo_review.py` 当前不存在；它是主对话复审后下一步唯一允许新增的真实集成入口。不能在此之前直接运行上述命令。

真实 Smoke 必须仍然满足：不调用 GitHub 写 API、不发布评论、不改代码、不自动重试正常模型失败、结果只落到本地证据目录。
