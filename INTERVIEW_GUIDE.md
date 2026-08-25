# Open SWE GitHub Review Agent：面试讲述指南（持续更新）

> 当前为 Phase 2 版本。GitHub 只读结果出现后必须继续更新数字与结论。本文不允许把计划写成成果。

## 1. 30 秒项目介绍

我在做一个基于官方 Open SWE Reviewer 约束的 GitHub Diff Review Agent。它读取固定 Diff，只在真实改动行上生成结构化 Finding，运行真实检查，并输出 JSON 和 Markdown。Phase 1 单题召回 `1/1`；Phase 2 三类 Diff 的人工核心缺陷召回为 `2/3`、Finding precision 为 `2/2`，没有误报或重复评论。一次结构化输出合同失败被安全拒绝，三个可观察正确 Finding 均高估一级。当前实现是 Reviewer-compatible 本地切片，下一步是 GitHub 只读接入计划。

## 2. 两分钟讲述框架

### 背景

我之前完成过一个 mini-swe 软件工程 Agent 研究，发现小模型的规划和 Tool Call 稳定性与 Agent 框架协议是两个不同问题。新项目把研究对象换成 GitHub Code Review，并选择官方 Open SWE Reviewer 作为 Scaffold。

### 核心问题

Code Review Agent 不只是让模型读代码。它必须绑定精确 Diff、限制评论位置、运行真实检查、区分确定问题和猜测，并控制 GitHub 权限。

### 我的方案

我固定 Open SWE Commit，先抽取 Reviewer 的核心边界：预先物化 Diff、计算 changed lines、结构化 findings。模型和 Sandbox 通过接口注入；最终 Review 先过 JSON Schema，再检查行锚定和决策语义，最后渲染成本地 Markdown。

### 当前结果

Phase 1 已完成真实 MiMo Preflight 和固定 Diff Review。Phase 2 又在逻辑、边界和权限三类 Diff 上各执行一次：边界与权限问题准确命中且无误报，逻辑题因 Review 合同失败而失败关闭。Phase 2 人工核心缺陷召回 `2/3`、Finding precision `2/2`；3 次调用共使用 4,628 Tokens。Phase 1 和 Phase 2 的三个可观察正确 Finding 都高估一级，说明严重度校准需要继续观察；完整官方 graph 和 GitHub 集成尚未完成。

### 下一步

Phase 2 已冻结且不补跑。下一步只创建和复审 Phase 3 GitHub 只读接入计划；在计划获批前不调用 GitHub API，也不开放写权限。

## 3. STAR 版本（当前草稿）

### Situation

在旧 mini-swe 项目中，我观察到模型能力和 Agent 完成协议会共同影响端到端结果。为了研究另一类真实 SWE 场景，我选择构建 GitHub Diff Review Agent，并要求它可解释、可评测且权限受控。

### Task

目标是在不过度建设平台的前提下，基于官方 Open SWE 快速跑通从固定 Diff 到结构化 Review 的最小链路，并为后续 GitHub App 和跨模型对照建立可信边界。

### Action

- 固定官方 Open SWE Repository 和 Commit，定位 Reviewer graph/factory。
- 分析官方 Reviewer 的仓库准备、Diff 物化、changed-line 和 finding 工具路径。
- 建立独立 Python 3.12 项目，不复制旧 mini-swe loop。
- 定义严格 Review Schema，分离 confirmed finding、suggestion 和 uncertainty。
- 实现 Diff 行解析、语义验证、Fake Model/Fake Sandbox 和 Markdown 渲染。
- 创建可确定性重建的双 Commit fixture，并用失败测试证明逻辑回归。
- 将 MiMo 固定为 OpenAI-compatible Chat Completions，避免误用 Open SWE 默认 Responses API。
- 采用“主对话审核、分支对话实现、结果回主对话”的 AI 辅助开发方式，并要求每阶段如实记录运行与未运行内容。

### Result

Phase 1 的真实结果是 MiMo 正确定位单题逻辑回归。Phase 2 扩展到三类 Diff 后，两个 Review 准确且无误报，一个因合同失败被安全拒绝，人工核心召回 `2/3`、precision `2/2`。这说明最小切片具备一定跨类别能力和失败关闭能力，但还不能证明广泛泛化；三个可观察正确 Finding 都高估一级，且当前仍未完成官方 graph 或 GitHub 集成。

## 4. 关键设计问题与回答

### 为什么不直接把完整 Diff 发给模型？

模型可以读完整 Diff，但发布 Review 时还需要知道哪些 Candidate 行是真实改动。Changed-line set 提供了确定的锚定边界，可以拒绝 Diff 外评论，降低误报对用户的干扰。

### 为什么同时需要 JSON Schema 和 Python 语义检查？

Schema 适合验证字段、类型、枚举和未知字段；“Finding 必须位于 Diff”“REQUEST_CHANGES 必须有 confirmed high/critical”依赖运行时上下文，更适合语义检查。二者职责不同。

### 为什么先用 MiMo，不先用本地 4B？

强模型先验证链路，可以降低归因混淆。如果强模型也无法完成最小 Review，优先检查 Scaffold 或适配；链路稳定后再运行本地模型，才能更可信地讨论能力差异。

### 为什么不马上创建 GitHub App？

GitHub 写权限会引入身份、权限、幂等和误发布风险。本地 JSON/Markdown 先验证 Review 质量，把模型问题和平台集成问题拆开。读取权限和写入权限也分两个阶段开放。

### 为什么 Fake workflow 有价值？

它不证明模型效果，但可以低成本验证控制流、Schema、拒绝规则和渲染。这样真实付费调用失败时，能更快判断是合同问题还是模型/官方 graph 集成问题。

### 为什么不做工业级证据冻结？

这是求职作品集原型。必要配置、Commit、结果和代表性证据必须保留，但为每次失败建立状态机、审计器或新阶段会延迟核心原型。项目采用与风险成比例的证据策略。

## 5. AI 辅助开发如何诚实表达

推荐说法：

> 这是一个 AI-assisted engineering 项目。我负责选择问题、定义边界、设计实验、审核实现和判断结果；AI 负责大量代码与文档生成。我通过固定输入、测试、源码核对和阶段复审确保自己能够解释关键路径，而不是把生成代码当作黑箱。

不要声称所有代码都是逐行手写。面试重点应放在你能解释：为什么选择 Open SWE、如何约束 Finding、为什么强模型先行、如何区分模型与框架问题、以及结果如何改变路线。

## 6. 面试前必须能现场解释的代码

1. `diff_parser.py` 如何跟踪 Base/Candidate 行号。
2. `contracts.py` 为什么要做二次语义验证。
3. `workflow.py` 中 Model 与 Sandbox 如何解耦。
4. `mimo.py` 为什么禁用 Responses API。
5. Fixture 的错误是什么，测试为什么失败。
6. Fake 测试能证明什么、不能证明什么。

## 7. 不能夸大的内容

在对应阶段完成前，不要说：

- 已经部署 GitHub App；
- 已在真实 PR 上达到某个 precision/recall；
- 已经运行本地 4B 跨框架对照；
- 官方 Open SWE 完整 graph 已在本地稳定运行；
- Fake Model 的成功代表 MiMo 或其他模型的质量。

## 8. 未来结果表（待真实实验填充）

| 阶段 | 模型/输入 | 核心结果 | 状态 |
|---|---|---|---|
| Phase 0 | Fake Model + 固定 Diff | 13 项离线测试通过，JSON/Markdown 可生成 | 完成 |
| Phase 1 | MiMo + 固定 Diff | 核心缺陷召回 1/1，误报 0；严重度偏高一级 | 完成 |
| Phase 2 | MiMo + 3 题 Smoke | 人工召回 2/3、precision 2/2、误报 0；1 次合同失败，严重度均高估一级 | 完成 |
| Phase 3 | 受控 GitHub PR，只读 | 待运行 | 未开始 |
| Phase 4 | 受控 GitHub PR，最小写入 | 待运行 | 未开始 |
| Phase 5 | 本地模型对照 | 根据前序结果决定 | 可选 |

## 9. 项目完成后应补充的面试材料

- 一张架构图；
- 一页实验指标表；
- 一个正确 Finding 和一个误报/漏报案例；
- GitHub 受控 PR Review 截图；
- 权限模型说明；
- 复现命令；
- 最终 STAR 版本；
- 局限性与下一步。

每完成一个阶段，都应更新本文中的结果数字、代表性案例和 STAR 的 Result，而不是等到项目结束凭记忆补写。
