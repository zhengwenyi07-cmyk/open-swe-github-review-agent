# Phase 1 结果：真实 MiMo 本地 Diff Review 原型

> 当前状态：`COMPLETED`
>
> 本阶段在固定本地 Diff 上完成了一次真实 MiMo V2.5 Pro Review。结果证明最薄 Reviewer-compatible 链路可工作；它不是官方 Open SWE 完整 Pregel graph。

## 1. 阶段结论

```text
phase_status=COMPLETED
real_mimo_call_completed=true
review_json_created=true
review_markdown_created=true
schema_validated=true
core_bug_detected=true
github_write_performed=false
next_phase_decision=ENTER_PHASE_2_THREE_TASK_SMOKE
```

MiMo 用一次结构化 Tool Call 正确识别了 `calculator.py:2` 的零分母保护回归，Finding 文件和行号准确，未产生虚假或重复 Finding。模型把预期为 `high` 的严重度评为 `critical`，属于校准偏高，不影响核心缺陷召回。

## 2. 实际实施范围

本阶段采用计划允许的方案 B：`OPEN_SWE_REVIEWER_COMPATIBLE_LOCAL_SLICE`。实现复用了官方 Reviewer 的 Prompt 纪律、changed-line 约束、结构化 Finding 边界和单一 Review Tool Call；本地 Git Sandbox 提供固定 Diff 和真实测试结果。

没有运行官方完整 Pregel graph，也没有接入 GitHub PR metadata、云 Sandbox 或 `publish_review`。因此准确表述是“Open SWE Reviewer-compatible 本地原型”，不能表述为“完整 Open SWE Reviewer 已部署”。

## 3. 固定身份

```text
project_contract_commit=83e4ef7afdfff9153f491ef4d9783080276ad39f
open_swe_repository=https://github.com/langchain-ai/open-swe.git
open_swe_commit=daab5de0baf2d8b16a7e2ae3fadbcb632bace8cc
fixture_id=phase1_logic_error_v1
base_commit=030396458d0e6fd6b8bf444c0ef24d1ea495b5b3
candidate_commit=746e90b56d3150d96acbff4a0f02308ab151669c
diff_sha256=e025350863e5054547661826f042d4c6e8ab40008947e35e221c12e9c10061ea
configured_model=mimo-v2.5-pro
response_model=mimo-v2.5-pro
finish_reason=tool_calls
```

## 4. 实际运行命令

API Key 通过隐藏输入进入当前 shell，未写入命令、文件或 Git：

```bash
read -rsp "MiMo API Key: " MIMO_API_KEY
echo
export MIMO_API_KEY
export MIMO_ACCOUNT_TYPE=PAY_AS_YOU_GO
export OPEN_SWE_MIMO_ALLOW_NETWORK=YES_ONCE

python scripts/run_mimo_preflight.py \
  --execute \
  --acknowledgement OPEN_SWE_PHASE1_MIMO_PREFLIGHT

python scripts/run_phase1_mimo_review.py \
  --execute-once \
  --fixture fixtures/phase1_logic_error/fixture.json \
  --acknowledgement OPEN_SWE_PHASE1_FIXED_DIFF_REVIEW
```

终端结果分别为：

```text
PASS mimo-preflight output=.../artifacts/mimo_preflight.json
PASS phase1-review output=.../artifacts/phase1
```

## 5. Preflight 结果

| 项目 | 结果 |
|---|---|
| 状态 | PASS |
| 实际返回模型 | `mimo-v2.5-pro` |
| finish reason | `tool_calls` |
| Tool Call 数 | 1 |
| Input Tokens | 273 |
| Output Tokens | 52 |
| Total Tokens | 325 |
| Transport | OpenAI Chat Completions |

## 6. Review 输出与人工评分

模型返回 `REQUEST_CHANGES`，包含一个 confirmed correctness Finding：Candidate 把 `if denominator == 0` 改成 `if numerator == 0`，导致 `ratio(5, 0)` 抛出 `ZeroDivisionError`。

| # | File:Line | 模型严重度 | 预期严重度 | 评估 |
|---|---|---|---|---|
| 1 | `calculator.py:2` | critical | high | 核心缺陷正确；严重度偏高一级 |

```text
core_bug_recall=1/1
false_findings=0
duplicate_findings=0
uncertainties=0
decision=REQUEST_CHANGES
decision_is_reasonable=true
```

## 7. 测试与运行指标

```text
test_command=python -m unittest test_calculator.py
test_returncode=1
test_passed=false
model_calls=1
input_tokens=1058
output_tokens=426
total_tokens=1484
elapsed_seconds=10.484
automatic_retries=0
cost=NOT_AVAILABLE
```

测试失败是 Fixture 中真实逻辑回归的预期证据，不是基础设施失败。Preflight 与 Review 合计使用 1,809 Tokens。

## 8. 产物与 SHA256

| 文件 | SHA256 |
|---|---|
| `artifacts/mimo_preflight.json` | `d0830409e74f8ec40c810405dad2edfca349fc0f138dcb2a8840b3d88ac07b06` |
| `artifacts/phase1/review.json` | `6dcaa003e23f1bc1fcc25d3bafca0d03080db52fe3f43172bf0d6a6151e90f00` |
| `artifacts/phase1/review.md` | `e866733ea4111bfcd89e333294af166bd717bc8d22f7920fc23ea64f62d8eba3` |
| `artifacts/phase1/run_summary.json` | `1cece57286b9b7d8d019f13273d75c21b3b108b6d4b4061fa05b6845dd6327be` |

## 9. 安全与权限

```text
api_key_in_git=false
api_key_in_artifacts=false
api_key_in_prompt=false
github_api_called=false
github_write_performed=false
code_modified_by_agent=false
old_mini_swe_project_modified=false
local_4b_run=false
training_started=false
docker_started=false
```

## 10. 成功、局限与下一步

成功：真实强模型调用、固定 Diff、真实失败测试、严格 JSON、changed-line 校验和 Markdown 渲染形成了完整本地闭环；核心缺陷召回 `1/1`，没有误报。

局限：样本只有一道；严重度校准偏高；运行的是 Reviewer-compatible local slice，而不是官方完整 graph；尚未验证三类缺陷的泛化，也未接入 GitHub。

人工决策：Phase 1 完成，允许下一步只创建并复审 Phase 2 三题 Smoke 计划。不得自动运行 Phase 2、调用 GitHub 写 API或扩张成通用评测平台。
