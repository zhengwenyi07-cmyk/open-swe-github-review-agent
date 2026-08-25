# Phase 1 计划：真实 MiMo 本地 Diff Review 原型

> 状态：`IMPLEMENTED_READY_FOR_PAID_RUN`
>
> 文档性质：实施前计划，可根据实现中的真实发现做最小调整；所有偏差必须写入同目录 `RESULTS.md`。
>
> 第一优先级：尽快获得一个真实可工作的 Diff Review 原型，不建设工业级平台。

## 1. 本阶段研究问题

本阶段只回答一个问题：

> 固定版本的 Open SWE Reviewer 路径能否使用 MiMo V2.5 Pro，读取一个固定本地 Git Diff，运行固定测试，并生成 Schema 合法、可读且不写入 GitHub 的 Review JSON 与 Markdown？

本阶段不是模型准确率大评测，也不是 GitHub App 阶段。只要真实模型调用和最小 Review 链路跑通，就达到核心目标。

## 2. 已有基础

新项目：

```text
/home/zhengwenyi/projects/open-swe-github-review-agent
```

官方只读源码：

```text
/home/zhengwenyi/projects/open-swe-upstream
```

固定上游：

```text
repository=https://github.com/langchain-ai/open-swe.git
commit=daab5de0baf2d8b16a7e2ae3fadbcb632bace8cc
reviewer_graph=agent.graphs.reviewer:traced_reviewer_agent
reviewer_factory=agent.reviewer:get_reviewer_agent
```

Phase 0 已提供：

- 固定双 Commit 本地 Fixture；
- Unified Diff 和 changed-line parser；
- Review JSON Schema 与语义验证；
- Fake Model/Fake Sandbox workflow；
- Markdown renderer；
- MiMo `ChatOpenAI` 静态适配器；
- 非基准 Tool Call 预检脚本；
- 13 项离线测试。

Phase 0 只验证静态合同，没有执行 MiMo 或官方 Reviewer graph。

## 3. 固定输入

Fixture：`fixtures/phase1_logic_error/fixture.json`

```text
fixture_id=phase1_logic_error_v1
base_commit=030396458d0e6fd6b8bf444c0ef24d1ea495b5b3
candidate_commit=746e90b56d3150d96acbff4a0f02308ab151669c
diff_sha256=e025350863e5054547661826f042d4c6e8ab40008947e35e221c12e9c10061ea
test_command=python -m unittest test_calculator.py
```

已知回归：Candidate 把零分母判断从 `denominator == 0` 错改为 `numerator == 0`。预期核心问题锚定 `calculator.py:2`，类别为 correctness，严重度为 high。

该预期只用于最终人工评分，不应直接出现在真实模型 Prompt 中。

## 4. 固定模型配置

```text
provider=MiMo
model=mimo-v2.5-pro
base_url=https://api.xiaomimimo.com/v1
transport=OpenAI-compatible Chat Completions
temperature=0.0
max_tokens=4096
max_retries=0
use_responses_api=false
```

密钥只允许从 `MIMO_API_KEY` 读取。账户类型固定为 `PAY_AS_YOU_GO`。不得将 Key 写入配置、日志、Prompt、结果文件或 Git。

## 5. 实施范围

### 5.1 P0：必须完成

1. 确认当前仓库工作区干净，HEAD 已推送。
2. 建立 Phase 1 的最薄真实模型 Review 入口。
3. 使用真实 MiMo 调用分析固定 Diff。
4. 运行固定单元测试并记录真实返回码。
5. 生成 `review.json`。
6. 通过现有 Schema 和 changed-line 语义验证。
7. 生成 `review.md`。
8. 保存最小运行摘要：模型身份、调用次数、Token、耗时、测试状态和最终状态。
9. 更新 `CONCEPTS.md` 和 `RESULTS.md`。
10. 运行后停止，交回主审核对话。

### 5.2 P1：尽量完成

真实调用应尽量复用固定 Open SWE Reviewer 的模型、Prompt、Diff/finding 边界，而不是只调用当前 Fake workflow。推荐顺序：

1. 优先尝试把预配置 MiMo `ChatOpenAI` 注入固定 `get_reviewer_agent`。
2. 将官方 GitHub publish 终点替换为本地 JSON/Markdown sink。
3. 使用固定本地仓库代替真实 GitHub PR 和云 Sandbox。

如果官方完整 graph 因 GitHub、LangSmith Sandbox 或部署依赖无法在本阶段快速本地化，允许采用最薄 adapter，直接复用官方 Reviewer Prompt、changed-line/finding 纪律和模型工具调用方式。必须在 `RESULTS.md` 准确写明复用了什么、没有运行什么，不能把本地 adapter 冒充官方完整 graph。

### 5.3 P2：只有不延误原型时完成

- 记录输入/输出 Token；
- 记录一次调用的实际费用或可计算费用；
- 保存脱敏模型响应结构摘要；
- 增加少量真实适配器离线拒绝测试。

P2 不得阻塞 P0。

## 6. 推荐新增或修改文件

文件名允许按真实实现做小幅调整，但不要扩张成框架：

```text
src/open_swe_review_agent/open_swe_adapter.py    # 官方 Reviewer 最薄适配
src/open_swe_review_agent/local_git_sandbox.py  # 固定本地仓库读取与固定测试
scripts/run_phase1_mimo_review.py                # 离线 check + 一次性真实运行
tests/test_phase1_mimo_review.py                 # 无网络 Fake/Mock 测试
artifacts/phase1/                                # Git 忽略的真实运行产物
```

不要为了形式完整创建新的 Schema、审计器、状态机、Runner 层、部署层或 r01/r02/r03 目录。现有 `review.schema.json` 足够时直接复用。

## 7. 最小执行路径

```text
materialize fixed fixture
  -> verify Base/Candidate/Diff SHA
  -> obtain exact unified diff
  -> call MiMo through preconfigured ChatOpenAI
  -> receive structured review candidate
  -> run fixed unittest in local fixture repo
  -> attach real test result
  -> validate JSON Schema
  -> validate finding changed-line anchors
  -> write review.json and review.md
  -> stop at human review gate
```

## 8. 付费调用顺序

### 8.1 先执行非基准 Tool Call 预检

静态实现复审并提交后，由用户在终端输入 Key：

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
```

预检只验证单一 Tool Call。预检失败时不运行 Review，先报告错误。

### 8.2 再执行一次固定 Diff Review

分支实现真实入口后，命令接口建议保持为：

```bash
export OPEN_SWE_MIMO_ALLOW_NETWORK=YES_ONCE

python scripts/run_phase1_mimo_review.py \
  --execute-once \
  --fixture fixtures/phase1_logic_error/fixture.json \
  --acknowledgement OPEN_SWE_PHASE1_FIXED_DIFF_REVIEW
```

具体环境变量或参数如因实现必须调整，应先在分支结果中说明。不得自动连续调用多次。

运行后立即清除：

```bash
unset MIMO_API_KEY
unset OPEN_SWE_MIMO_ALLOW_NETWORK
```

## 9. 输出要求

### 9.1 `review.json`

必须满足现有 `schemas/review.schema.json`，至少包括：

- Candidate Commit；
- Summary；
- Findings；
- Uncertainties；
- 真实测试命令与 passed 状态；
- Decision。

Finding 必须落在 Candidate changed line。无法确认的问题必须进入 uncertainties，不能写成 confirmed defect。

### 9.2 `review.md`

必须由已验证 JSON 渲染，而不是另行让模型自由生成。内容至少展示 summary、decision、findings、uncertainties 和 tests。

### 9.3 最小运行摘要

建议保存：

```json
{
  "status": "PASS|MODEL_FAILURE|INFRASTRUCTURE_FAILURE",
  "model": "mimo-v2.5-pro",
  "upstream_commit": "daab5de...",
  "model_calls": 1,
  "input_tokens": 0,
  "output_tokens": 0,
  "elapsed_seconds": 0.0,
  "test_returncode": 0,
  "schema_valid": true,
  "github_write_performed": false
}
```

字段按 API 实际可用信息填写，无法取得时使用 `null` 并在结果中解释，不要编造。

## 10. 验收标准

### 链路通过

- 真实 MiMo 请求完成；
- 输出结构可解析；
- `review.json` 通过 Schema 与语义验证；
- `review.md` 成功生成；
- 固定测试真实执行；
- 没有 GitHub 写入或代码修改；
- 没有凭据泄漏。

### Review 质量判断

分别记录，不与链路通过混为一谈：

- 是否召回核心逻辑错误；
- 文件和行号是否准确；
- 是否存在虚假 Finding；
- confirmed/suggestion/uncertainty 是否分类正确；
- Decision 是否合理。

真实模型没有找出问题属于模型结果，不等于基础设施失败。

## 11. 失败处理

- API 鉴权、网络、依赖或适配错误属于基础设施失败：保存脱敏错误，允许一次最小修复后补跑。
- Schema 不合法先检查适配器是否正确解析 Tool Call；不要通过放宽 Schema 掩盖问题。
- 正常漏报、误报或错误 Decision 属于模型失败：不自动重跑。
- 官方完整 graph 依赖过重时，优先缩成可解释的最薄 adapter，不引入部署阶段。
- 任意失败后不得自动开始 Phase 2。

## 12. 明确禁止

- 不创建 GitHub App。
- 不调用 GitHub 写 API。
- 不发布 Review 评论。
- 不自动修改代码。
- 不运行本地 Qwen3.5-4B。
- 不训练或下载模型。
- 不设计另外两道 Smoke 任务。
- 不启动 Docker 长任务。
- 不修改旧 mini-swe 项目。
- 不增加企业平台、审计框架或新检查点。
- 不提交 API Key 或原始秘密。

## 13. 分支对话最终回报

分支必须返回：

1. 是否完成真实模型 Review。
2. 实际使用的是官方完整 graph、部分官方组件还是最薄兼容 adapter。
3. 修改文件列表。
4. 精确执行命令。
5. Preflight 结果。
6. Review JSON/Markdown 路径和 SHA256。
7. Finding、Uncertainty、Decision 和测试结果。
8. 核心错误是否识别、误报数量。
9. Token、耗时、费用和模型调用数。
10. 凭据与 GitHub 写入检查。
11. 测试和 `git diff --check` 结果。
12. Git 状态、未提交内容和明确未执行项。

返回结果后停止，等待主审核对话决定 Phase 2 是否调整或开始。
