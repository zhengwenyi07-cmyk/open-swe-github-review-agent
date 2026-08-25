# Open SWE GitHub Review Agent：总体框架（初版）

> 文档性质：可调整的研究与实现路线，不是不可变规格。
>
> 当前状态：Phase 0～2 已完成；Phase 2 人工核心缺陷召回 `2/3`、Finding precision `2/2`。
>
> 第一优先级：尽快获得一个可工作的 GitHub Diff Review 原型。
>
> 当前唯一下一步：主对话复审并提交 Phase 3 离线实现，再批准精确目标 PR；尚未批准联网执行。

## 1. 为什么建立这个项目

旧项目 `/home/zhengwenyi/projects/swe-agent` 研究的是本地小模型微调、mini-swe Agent loop、Docker 执行与任务完成能力。它最终区分出了两类瓶颈：本地 4B 模型存在规划和格式能力不足；强 API 模型可以完成任务，但 mini-swe 仍有独立的非交互完成协议问题。

本项目不再继续修 mini-swe，也不复制旧 Agent loop。新的研究对象是代码审查：给 Agent 一个 Commit 或 PR Diff，让它读取改动、运行必要检查、输出结构化 Review，并最终通过最小权限 GitHub App 发布 Review。

一句话目标：

> 基于官方 Open SWE Reviewer 构建一个可复现、可评测、最小权限的 GitHub Diff Review Agent，并用强模型和本地模型对照分析 Review 能力与 Scaffold 的关系。

## 2. 项目成功标准

### 2.1 第一版必须做到

1. 读取固定 Commit/PR Diff。
2. 只在 Diff 改动行上报告问题。
3. 运行少量、明确且可重复的检查。
4. 输出严格 Review JSON。
5. 生成人可读 Markdown Review。
6. 区分 confirmed defect、suggestion 和 uncertainty。
7. 在本地链路可信后，通过最小权限 GitHub App 读取 PR 并发布 Review。
8. 保存足够支持复现、面试解释和结果对比的配置、指标与代表性证据。

### 2.2 不属于第一版

Slack、Linear、Web Dashboard、自动 Merge、默认分支写入、自动修复、多租户、分布式队列、长期记忆、大规模 Multi-Agent、训练数据生产线和企业部署平台均不属于第一版。

## 3. 总体技术路径

```text
Git Commit / Pull Request
          |
          v
    Diff + Changed Lines
          |
          v
 Open SWE Reviewer Agent
   |                  |
   |                  +--> 必要测试/静态检查
   v
结构化 Findings
   |
   +--> Review JSON
   +--> Local Markdown
   +-->（后期）GitHub PR Review / Check Run
```

模型和执行层保持可替换：

```text
Review Model:
  MiMo V2.5 Pro（先验证上限）
  -> Qwen3.5-4B Base（可选对照）
  -> 旧 Adapter（可选跨 Scaffold 对照）

Sandbox:
  Fake Sandbox（合同测试）
  -> 固定本地仓库（原型）
  -> Open SWE 支持的真实 Sandbox（GitHub 阶段）
```

## 4. 上游与实现边界

固定上游：

- Repository：`https://github.com/langchain-ai/open-swe.git`
- Commit：`daab5de0baf2d8b16a7e2ae3fadbcb632bace8cc`
- Reviewer graph：`agent.graphs.reviewer:traced_reviewer_agent`
- Reviewer factory：`agent.reviewer:get_reviewer_agent`

官方 Reviewer 会在模型调用前准备仓库和 Diff，计算 changed-line 集合，并使用 Review 专用 finding/publish 工具。项目应尽量沿着该 Reviewer 路径集成，而不是重新实现另一个通用 Agent 框架。

当前仓库中的 `ReviewWorkflow` 是离线合同切片，用来快速验证 Diff、模型、测试、Schema 和 Markdown 的边界。它不是完整官方 Reviewer graph，文档和面试中不得混淆两者。

## 5. 开发原则

1. **工作原型优先。** 可运行的真实 Review 比新增审计器、Schema 或形式化阶段更重要。
2. **一次只推进一个结果。** 当前阶段只围绕一个明确结果展开。
3. **阶段可调整。** 每阶段结束后，根据真实数据更新下一阶段，不提前锁死所有细节。
4. **强模型先行。** 先确认框架链路有效，再测试本地 4B，避免把框架故障误判为模型能力不足。
5. **本地只读先行。** 先固定 Diff 和本地输出，再接 GitHub 读取，最后才开放最小写权限。
6. **模型失败不是基础设施失败。** 正常漏报或误报保留为研究结果，不用重复运行粉饰结果。
7. **避免审计递归。** 不为每次失败创建 r01/r02/r03 诊断框架；只做定位当前阻塞所需的最小修复。
8. **不夸大结果。** Fake workflow 只说明合同可运行；只有真实模型和官方 graph 执行后才能声称 Open SWE 原型跑通。
9. **旧项目只读。** 只复用方法和经验，不修改旧代码、证据、Commit 或门禁。

## 6. 初步阶段路线

下面阶段表达研究顺序，不代表每阶段内部还要拆成很多检查点。阶段结束时允许根据结果合并、删除或修改后续内容。

### Phase 0：静态准备（已完成）

目标：用最低成本确认上游、接口和本地合同可行。

已完成：

- 固定 Open SWE 官方 Commit；
- 创建独立 Python 3.12 环境；
- 固定一个带明确逻辑回归的本地 Git Diff；
- 定义 Review JSON Schema 和 changed-line 约束；
- 实现 Fake Model/Fake Sandbox；
- 实现本地 Markdown 渲染；
- 确认 MiMo 应通过预配置 `ChatOpenAI` 使用 Chat Completions，而不是 Open SWE 默认 Responses API 路由；
- 13 项离线测试通过。

Phase 0 只证明静态合同成立，没有证明官方 Open SWE Reviewer 或 MiMo Review 已运行。

### Phase 1：可工作的本地 Diff Review 原型（已完成）

目标：真实 MiMo + 固定官方 Open SWE Reviewer 路径 + 固定本地 Diff，生成第一份真实 Review JSON 和 Markdown。

最小工作范围：

1. 提交当前静态基线，保持工作区干净。
2. 运行一次非基准 MiMo Tool Call 预检。
3. 把预配置 MiMo model 注入固定 Open SWE Reviewer 路径。
4. 用本地固定仓库提供 Base/Candidate Diff。
5. 禁用 GitHub 发布，以本地 JSON/Markdown 作为终点。
6. 运行固定测试命令并记录返回码。
7. 人工复核 finding 是否正确、是否锚定改动行、是否出现虚假问题。

验收结果：

- 至少完成一次真实模型调用；
- 生成 Schema 合法的 Review JSON；
- 生成可读 Markdown；
- 正确识别 fixture 的核心逻辑错误，或如实记录未识别；
- 没有 GitHub 写入、代码修改或凭据泄漏。

结果驱动决策：

- 若链路成功且 Review 基本正确：直接进入 Phase 2。
- 若模型响应结构不兼容：只修 MiMo/Open SWE 适配边界，然后补跑一次。
- 若官方 graph 的外部依赖过重：保留官方 Reviewer 约束，采用最薄本地 adapter 跑通原型，并清楚记录差异。
- 若 MiMo 正常运行但漏报/误报：作为模型结果，不创建额外审计阶段。

实际结果：MiMo Preflight 和真实 Review 均通过；模型一次调用生成一个结构化 Review Tool Call，正确指出 `calculator.py:2` 的零分母保护回归，核心缺陷召回 `1/1`，虚假 Finding `0`。测试真实返回 `1`，与已知回归一致。模型严重度为 `critical`，高于预期 `high`，记录为校准偏差。实际链路是 Reviewer-compatible local slice，不是官方完整 Pregel graph。

### Phase 2：三题 Diff Review Smoke（已完成）

目标：判断原型是否具有基本泛化，而不是只记住一道 fixture。

初步任务：

1. 明确逻辑错误。
2. 缺少边界或异常处理。
3. 危险或越权修改。

每题只需要固定 Base、Candidate、主要问题、允许的次要问题、禁止的虚假问题、测试和评分规则。优先人工可读，避免为三题建设通用评测平台。

核心指标：

- 关键问题召回率；
- Finding precision；
- 文件/行号准确率；
- Schema 合法率；
- 测试执行率；
- 重复评论数；
- 完成成功率；
- Token、延迟、费用；
- 安全违规数。

结果驱动决策：

- 若 3 题表现稳定：进入 GitHub 只读接入。
- 若只有某类任务失败：下一阶段围绕该具体缺口调整 Prompt、工具或上下文，不扩大平台范围。
- 若官方 Scaffold 成本明显高于价值：在报告中说明，并保留最小切片作为产品原型。

实际结果：三题只运行一次，边界题与权限题均生成准确、无误报的 changed-line Review；逻辑题在 `REVIEW_VALIDATION` 阶段因合同失败而失败关闭。人工核心缺陷召回 `2/3`、Finding precision `2/2`、虚假和重复 Finding 均为 `0`。两个有效 Finding 均高估一级，与 Phase 1 的严重度偏差同向。决定进入 Phase 3 GitHub 只读计划，但不补跑 Phase 2，也不自动执行 Phase 3。

### Phase 3：GitHub 只读接入（离线实现完成，未运行）

目标：对一个主对话批准的真实 PR 完成只读快照与本地 Review，不发布评论。

认证优先使用公开 PR 无 Token 模式；需要认证时只使用目标仓库的细粒度只读 Token。只允许读取 Metadata、Contents 和 Pull Requests，Review 仍写入本地证据。Token 不进入 Prompt、日志、产物或 Git。

计划采用 metadata A → files → raw diff → metadata B 的快照协议，要求 Base/Head SHA 稳定，并交叉验证文件列表、patch、raw diff 和 changed-line 集合。patch 缺失、Diff 超限、二进制或 SHA 漂移均失败关闭，不执行 PR 代码。

验收门槛：成功读取一个批准的 PR 快照；本地 Review Schema 与 changed-line 语义合法；GitHub 写操作为 `0`；凭据扫描和人工复核通过。离线 Client、Runner 和 Fake 测试已经实现并停在联网前，不能自动进入 Phase 4。

### Phase 4：最小 GitHub Review 写入（初步）

目标：把已在本地通过人工复核的 Review 发布到受控测试 PR。

只允许发布 PR Review、创建/更新 Check Run、更新 Agent 自己创建的评论。继续禁止自动 Merge、默认分支 Push、仓库设置修改、删分支和无关仓库权限。

验收结果：受控 PR 上出现一次正确 Review；重复运行不会制造重复评论；权限范围可解释。

### Phase 5：跨模型对照（可选，不预先承诺）

只有 MiMo + Open SWE Smoke 稳定后才考虑：

- MiMo V2.5 Pro + Open SWE；
- Qwen3.5-4B Base + Open SWE；
- 旧 mini-swe Adapter + Open SWE。

该阶段研究本地 4B 的最小 Diff Review 能力和 Adapter 的跨 Scaffold 迁移性。在看到结果前不生产新训练数据、不开始新 QLoRA。

## 7. 阶段协作方式

当前主对话负责审核和路线决策。每个实现阶段单独建立分支对话：

1. 主对话从本文抽取一个阶段的明确目标、边界和验收条件。
2. 主对话为该阶段创建或批准 `PLAN.md`。
3. 分支对话只实现该阶段，并同步维护 `CONCEPTS.md` 草稿，不擅自启动下一阶段。
4. 分支对话返回变更文件、运行命令、真实结果、失败、Hash、Git 状态和未完成项。
5. 主对话复审代码和证据，判断结果是否可信，并完成 `RESULTS.md`。
6. 主对话更新总体框架、技术复盘、交接文档和面试材料。
7. 复审通过后再提交；付费调用和 GitHub 写入需单独人工批准。

这套流程的目的不是制造门禁，而是避免不同对话丢失上下文或把预期结果写成真实结果。

## 8. 每阶段必须留下什么

从 Phase 1 开始，每个正式阶段在 `docs/phases/phase-XX-short-name/` 中维护：

- `PLAN.md`：阶段开始前的研究问题、范围、实现计划、验收条件和边界；
- `CONCEPTS.md`：技术原理、数据流、官方源码关系、关键代码和设计权衡；
- `RESULTS.md`：真实命令、指标、产物、失败、局限性和下一阶段决策。

详细模板见 `docs/phases/README.md`。这三份文档是为了让项目所有者理解 AI 完成的内容和准备面试，不是三个额外检查点。

最小必要记录：

- 目标与假设；
- 实际修改文件；
- 精确运行命令；
- 模型、上游 Commit 和关键配置；
- 真实指标与失败；
- 代表性输出；
- 结果如何改变下一阶段；
- 哪些内容明确没有运行。

不要求为每个步骤创建 Schema、状态机、独立审计器或多层 Manifest。只有结果容易混淆、涉及付费/写权限或必须机器校验时才增加结构化证据。

## 9. 安全边界

- API Key、GitHub Token、App private key 仅从运行时安全环境读取。
- 凭据不进入 Prompt、Sandbox、日志、配置或 Git。
- GitHub 写权限晚于本地只读验证。
- 第一版不得自动修改代码或 Merge。
- 本地 Sandbox 只处理明确指定的测试仓库和命令。
- 正常模型失败不自动重试；基础设施失败最多进行一次有证据的修复后补跑。

## 10. 最终可用于简历的交付形态

如果 Phase 1～4 成功，项目应能展示：

1. 一张从 GitHub PR 到结构化 Review 的架构图。
2. 三题 Smoke 的指标表和典型误报/漏报。
3. 一个受控 PR 上的真实 Review 截图或链接。
4. Open SWE Reviewer 定制点、changed-line 安全边界和最小权限设计。
5. 强模型与本地模型对照结论（若 Phase 5 有价值）。
6. 可复现命令、局限性和下一步，而不是只展示成功案例。

## 11. 本文更新规则

- 已完成阶段的事实、命令和结果只追加勘误，不因后续路线变化而重写历史。
- 未开始阶段可根据上一阶段结果修改、合并或取消。
- “计划”“已实现”“已运行”“通过”必须使用不同措辞。
- 每阶段结束后更新顶部状态和当前唯一下一步。
- 如果项目方向变化，先解释证据和原因，再修改后续路线。
