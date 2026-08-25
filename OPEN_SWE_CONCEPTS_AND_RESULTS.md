# Open SWE GitHub Review Agent：概念、实现与结果

> 用途：长期技术复盘。半年后应能依靠本文重新理解项目为什么存在、各组件如何协作、哪些结果真实发生、哪些结论仍只是计划。

## 1. 项目问题是什么

普通 LLM 可以阅读代码并给出建议，但一个可信的 GitHub Review Agent 还必须解决四个工程问题：

1. **上下文边界：**模型看到的是哪一个 Commit/PR、哪一段 Diff？
2. **证据边界：**评论是否能锚定真实改动行，还是在猜测未改代码？
3. **执行边界：**需要运行哪些测试，结果如何与 Review 绑定？
4. **权限边界：**什么时候只能本地输出，什么时候才允许写入 GitHub？

本项目的研究重点不是做一个聊天式代码解释器，而是把这些边界组合成可运行、可评测的 Review workflow。

## 2. 为什么选择 Open SWE

Open SWE 官方项目已经包含 Coding、Reviewer、Sandbox、GitHub 集成和 LangGraph 运行时。固定 Commit 的 Reviewer 不是简单地把完整 Diff 塞给模型，而是预先准备仓库、计算 changed-line 集合、维护结构化 findings，并通过 Review 专用工具发布。

这与本项目需求高度一致：Review Agent 应该“审查并报告”，而不是偷偷改代码或替用户 Merge。因此项目选择沿用官方 Reviewer 路径和边界，而不是复制旧 mini-swe Agent loop。

## 3. 核心概念

### 3.1 Base、Candidate 与 Diff

- Base Commit：改动前的确定版本。
- Candidate Commit：待审查版本。
- Unified Diff：Base 到 Candidate 的文本变化。
- Changed-line set：Candidate 侧真实新增或修改行的 `(file, line)` 集合。

Finding 必须落在 changed-line set 中。这并不保证 Finding 正确，但可以阻止 Agent 把 Review 锚定到 PR 没有修改的任意代码。

### 3.2 Finding、Suggestion 与 Uncertainty

- `confirmed` finding：有直接代码或测试证据的缺陷。
- `suggestion` finding：不会被描述为确定故障的改进建议。
- `uncertainty`：现有 Diff 无法确认、需要更多上下文的问题。

三者分离是为了控制幻觉：模型可以表达不确定，但不能把“可能有问题”伪装成已证实的高严重度缺陷。

### 3.3 Review 决策

- `APPROVE`：没有 finding。
- `COMMENT`：有建议、低中风险问题或不阻塞结论。
- `REQUEST_CHANGES`：至少存在一个 confirmed high/critical finding。

当前合同故意简单，后续只有真实 Smoke 证明需要时才扩展。

### 3.4 Model 与 Sandbox 的职责

Model 负责分析 Diff、形成 summary/findings/uncertainties/decision。Sandbox 负责读取精确 Diff 和运行固定检查。Workflow 把二者组合，并在最终输出前执行 Schema 和语义验证。

模型不应伪造测试结果；Sandbox 也不应替模型选择“正确答案”。

## 4. 官方 Reviewer 路径

固定上游身份：

```text
Repository: https://github.com/langchain-ai/open-swe.git
Commit:     daab5de0baf2d8b16a7e2ae3fadbcb632bace8cc
Graph:      agent.graphs.reviewer:traced_reviewer_agent
Factory:    agent.reviewer:get_reviewer_agent
```

从源码确认的关键路径：

```text
langgraph.json
  -> agent.graphs.reviewer:traced_reviewer_agent
  -> agent.reviewer:get_reviewer_agent
  -> prepare_review_repo / materialize_review_diff
  -> compute_diff_line_set
  -> reviewer tools: add/update/list findings, publish_review
```

完整官方 graph 还涉及 GitHub PR 元数据、Sandbox provider、Deep Agents middleware 和发布工具。当前 Phase 0 没有运行这些外部链路。

## 5. 当前本地实现

### 5.1 `diff_parser.py`

解析 Unified Diff 的 hunk header，跟踪 Candidate 侧行号，并生成所有新增/修改行的锚点集合。删除行只推进 Base 行号，不会被当作 Candidate 可评论行。

### 5.2 `contracts.py`

先使用 Draft 2020-12 JSON Schema 校验字段和类型，再做 Schema 难以表达的语义检查：

- Finding 是否落在 Diff；
- 是否重复；
- decision 与 finding 严重度/assessment 是否一致。

### 5.3 `workflow.py`

最小执行顺序：

1. Sandbox 读取 Base/Candidate Diff。
2. Model 生成 Review candidate。
3. Sandbox 运行固定测试。
4. Workflow 写入真实 Candidate Commit 和测试结果。
5. 合同验证最终 Review。

### 5.4 `fakes.py`

Fake Model 返回确定性 Review；Fake Sandbox 返回固定 Diff 和测试返回码。它们用于验证控制流和拒绝路径，不用于评估模型质量。

### 5.5 `render.py`

把已验证 JSON 转换成人可读 Markdown。渲染器不重新解释模型内容，也不改变决策。

### 5.6 `mimo.py`

Open SWE 默认 OpenAI 路由会使用 Responses API。MiMo 是 OpenAI-compatible Chat Completions，因此通过预配置 `ChatOpenAI` 注入，并明确设置 `use_responses_api=False`。

固定参数：

```text
model=mimo-v2.5-pro
base_url=https://api.xiaomimimo.com/v1
temperature=0.0
max_tokens=4096
max_retries=0
```

该模块已完成离线构造测试，并在 Phase 1 中完成真实 Preflight 与 Review 请求。API 返回模型身份和 finish reason 均经过失败关闭校验。

## 6. 固定本地 Fixture

Fixture 是一个微型 Python 仓库。Base 版本在分母为零时返回既定 sentinel；Candidate 错误地把判断改成分子为零，导致零分母路径抛出异常。

```text
Base:      030396458d0e6fd6b8bf444c0ef24d1ea495b5b3
Candidate: 746e90b56d3150d96acbff4a0f02308ab151669c
Diff SHA:  e025350863e5054547661826f042d4c6e8ab40008947e35e221c12e9c10061ea
```

预期主要 Finding：`calculator.py:2`，category=`correctness`，severity=`high`。固定测试 `python -m unittest test_calculator.py` 在 Candidate 上失败。

## 7. 已完成结果

### Phase 0：静态合同

真实完成内容：

- 官方仓库与 Commit 已核验并保持只读；
- 新仓库和 Python 3.12 `.venv` 已创建；
- Fixture 可确定性重建；
- Diff Hash 与 Base/Candidate Commit 匹配；
- Review Schema 合法；
- Fake workflow 能生成 JSON 和 Markdown；
- Changed-line、重复 Finding、决策语义和未知字段拒绝测试通过；
- MiMo Adapter 构造参数和秘密类型测试通过；
- `pip check` 通过。

测试结果：

```text
Ran 13 tests
OK
```

这说明本地合同和依赖注入设计可运行。Phase 0 本身不说明 MiMo 已发现缺陷，也不说明官方 Open SWE Reviewer 已在本地工作。

### Phase 1：真实 MiMo 固定 Diff Review

真实运行采用 `OPEN_SWE_REVIEWER_COMPATIBLE_LOCAL_SLICE`，而不是官方完整 Pregel graph。MiMo V2.5 Pro 对固定 Fixture 进行一次模型调用，返回一个结构化 Review Tool Call：

- 正确识别 `calculator.py:2` 的零分母保护回归；
- 核心缺陷召回 `1/1`；
- 文件和 changed-line 锚定准确；
- 虚假 Finding `0`，重复 Finding `0`；
- 决策为 `REQUEST_CHANGES`；
- 真实测试返回码为 `1`，与回归预期一致；
- Review 使用 1,484 Tokens，耗时 10.484 秒；
- 严重度给成 `critical`，高于预期 `high`，说明仍需观察校准；
- 没有调用 GitHub API，也没有修改代码。

该结果证明本地最薄 Review 闭环可工作，但单题成功不能推导出泛化能力。下一步用三类小型 Diff 做 Smoke，而不是直接开放 GitHub 权限。

### Phase 2：三题 Diff Review Smoke

Phase 2 在逻辑错误、空列表边界错误和 viewer 删除权限扩大三类冻结 Diff 上各调用 MiMo 一次。边界题与权限题均生成合同合法、文件和 changed-line 锚定正确的 Review，人工核心缺陷召回为 `2/3`、Finding precision 为 `2/2`，虚假和重复 Finding 均为 `0`。逻辑题的响应在 `REVIEW_VALIDATION` 阶段违反合同，运行器按失败关闭策略只保存脱敏失败证据，因此保守按漏报计且不补跑。

两个有效 Review 的严重度分别从 `medium` 高估为 `high`、从 `high` 高估为 `critical`。连同 Phase 1 的 `high`→`critical`，当前三个可观察正确 Finding 都高估一级；这支持“严重度存在上偏倾向”的小样本结论，但不能夸大为统计规律。

本阶段共调用模型 3 次，使用 3,155 input、1,473 output、4,628 total tokens。没有调用 GitHub API 或进行 GitHub 写入。八份原始产物及 Hash 已冻结，下一步只进入 Phase 3 GitHub 只读计划。

### Phase 3：GitHub PR 只读接入（已完成）

Phase 3 只替换输入层：从一个主对话批准的 PR 读取 metadata、Base/Head SHA、changed files 和 raw diff，生成稳定快照和 candidate-side changed-line 集合，再复用现有 MiMo 结构化 Review、Schema、语义门禁和 Markdown renderer。

安全设计采用 metadata 前后双读、files/raw diff 交叉验证、严格输入预算和失败关闭。公开 PR 优先无 Token 读取；需要认证时仅使用细粒度只读 Token。任何 patch 缺失、SHA 漂移、文件或 Diff 超限都会在模型调用前拒绝。本阶段不运行 PR 代码，也不包含任何 GitHub 写 endpoint。

正式运行选择公开、已合并且满足预算的 `pallets/click#3021`。4 次 GitHub GET 获取并验证了 Base `27aaed3...`、Head `27de74a...`、3 个文件、4,659 bytes raw diff 和 38 个 candidate changed lines。MiMo V2.5 Pro 只调用一次，使用 2,937 input、2,987 output、5,924 total tokens，在 63.601 秒内返回 `APPROVE`、0 个 Finding 和 1 个 Uncertainty。Uncertainty 锚定到真实新增行 `src/click/termui.py:122`，询问版本号是否符合发布计划。

该结果证明 GitHub PR 输入可以替代本地 Fixture，同时保持既有 Review 合同和 changed-line 边界。它不能证明更广泛的召回率或 precision，因为该 PR 没有冻结人工 Gold Finding；只读模式也没有执行测试，所以 `APPROVE` 仅表示静态 Diff 审查未确认问题。GitHub 写请求、Review 发布、PR 代码执行和自动重试均为 0。六份原始产物经人工复审后冻结。

## 8. 当前未完成和未知问题

1. 三题 Smoke 显示了跨类别的基本可用性，但样本量仍不足以证明广泛泛化能力。
2. 官方完整 Reviewer Pregel graph 尚未运行。
3. GitHub 只读已在一个公开 PR 上完成；样本量只有 1。Phase 4 最小写入离线合同已完成，但 GitHub App、测试 PR 和真实发布仍未开始。
4. 严重度在三个可观察样本中均高估一级，仍需在后续只读样本中继续观察。

### Phase 4：受控 GitHub Review 最小写入（离线实现完成）

Phase 4 只增加一个变量：把经人工批准 Hash 的本地 Review Payload 发布到项目所有者控制的测试 PR。离线实现采用只安装到该仓库的 GitHub App，准备动作将 installation token 下压到 Pull requests read，发布动作才请求 read/write；代码层唯一允许的仓库内容写接口是 Create Review。

为防止模型输出直接产生外部副作用，计划把准备与发布分开：准备动作只读 PR、调用 MiMo 一次并生成确定性 `publish_payload.json`；主对话逐字审核并提交 Payload Hash 合同后，发布动作才可执行一个 `event=COMMENT` 的 POST，且不得再次调用模型。Head 漂移、重复 Marker 或模糊写入状态均停止，不自动重试。

当前这些都是设计，不是结果。不能声称 GitHub App 已部署、Review 已发布或幂等机制已经验证。

## 9. 后续结果记录模板

每个阶段结束后在本文追加，不覆盖历史：

```text
阶段：
日期与 Git Commit：
研究问题：
输入/任务：
模型与配置：
实际执行命令：
实现变更：
定量结果：
代表性成功：
代表性失败：
安全与权限状态：
结论：
对下一阶段的影响：
明确未执行内容：
```

## 10. 面试时必须诚实区分的内容

可以说：

- “我基于固定 Open SWE Reviewer 源码设计了 changed-line 约束和结构化 Review 合同。”
- “项目使用 AI 辅助实现；我负责目标、边界、实验设计、复审和结果决策，并能解释关键实现与权衡。”
- “Phase 0 的 Fake workflow 验证了合同，不代表真实模型效果。”

不能说：

- “MiMo 已经运行官方完整 Open SWE Reviewer graph。”
- “GitHub App 已经部署。”
- “Agent 因一次真实 PR `APPROVE` 达到了某个召回率或准确率。”
- “本地 4B 已适配 Open SWE。”

## 11. 从旧项目迁移的知识，而不是代码

复用的经验包括：强模型先验证框架、Smoke 漏斗、结构化指标、凭据隔离、模型失败与基础设施失败分离。没有迁移 mini-swe loop、YAML、Parser、完成协议、Trajectory 或历史绝对路径。

因此新项目能延续旧研究结论，但不会把两个 Scaffold 的结果混在一起。
