# Open SWE GitHub Review Agent

这是一个与已结束的 `swe-agent` 完全独立的求职作品集原型。目标是沿用 Open SWE 官方 Reviewer 的核心约束，逐步实现：固定 Git Diff → 模型审查 → 必要检查 → 严格 Review JSON → 本地 Markdown；只有本地只读链路稳定后，才考虑 GitHub App 读权限与最小 Review 写入。

项目采用结果驱动的初步路线：总体方向固定，但未开始的阶段会根据上一阶段真实结果调整。第一优先级始终是尽快获得一个可工作的 GitHub Diff Review 原型，而不是建设工业级平台或不断增加检查点。

## 当前状态

Phase 0、Phase 1 与 Phase 2 已完成：

- 固定 Open SWE 官方上游 Commit；
- 建立独立 Python 3.12 环境；
- 定义严格 Review Schema 与 changed-line 语义门禁；
- 固定一个可重建的本地 Git Diff fixture；
- Fake Model/Fake Sandbox 离线工作流与测试；
- MiMo V2.5 Pro Chat Completions 适配入口和一次性付费预检门禁；
- 本地 JSON/Markdown 生成器；
- MiMo V2.5 Pro 真实 Preflight；
- 固定逻辑回归 Diff 的真实 Review：核心缺陷召回 `1/1`，Finding 锚定 `calculator.py:2`，虚假 Finding `0`。

Phase 1 使用 `OPEN_SWE_REVIEWER_COMPATIBLE_LOCAL_SLICE`，并非官方完整 Pregel graph。尚未创建 GitHub App、写入 GitHub、运行本地 4B、训练或运行 Docker。

Phase 2 已完成一次性 MiMo 三题 Smoke：两题生成合同合法且语义准确的 Review，人工核心缺陷召回 `2/3`、Finding precision `2/2`，虚假和重复 Finding 均为 `0`；逻辑题因 Review 合同失败而按漏报计。两个有效 Finding 均高估一级，结合 Phase 1 显示小样本中的一致严重度上偏。Phase 2 不补跑，且没有调用或写入 GitHub。

Phase 3 GitHub PR 只读接入已经完成离线实现：包含受限 GET Client、PR metadata 双读、files/raw diff 交叉验证、changed-line 门禁和 Fake Client 测试。真实 PR 与 MiMo Review 尚未运行。下一步是主对话复审并提交实现，再批准一个精确目标 PR；GitHub Review 发布仍被禁止。

## 文档导航

建议按以下顺序阅读：

1. [PROJECT_HANDOFF.md](PROJECT_HANDOFF.md)：当前状态、下一步、分支对话交付格式。
2. [OPEN_SWE_GITHUB_REVIEW_FRAMEWORK.md](OPEN_SWE_GITHUB_REVIEW_FRAMEWORK.md)：初步总体路线、阶段目标和结果驱动调整原则。
3. [OPEN_SWE_CONCEPTS_AND_RESULTS.md](OPEN_SWE_CONCEPTS_AND_RESULTS.md)：概念、实现细节、真实结果与未完成内容。
4. [INTERVIEW_GUIDE.md](INTERVIEW_GUIDE.md)：STAR 讲述、常见问题、AI 辅助开发的诚实表述。
5. [docs/UPSTREAM_AND_ARCHITECTURE.md](docs/UPSTREAM_AND_ARCHITECTURE.md)：固定官方 Reviewer 路径及当前本地切片与官方 graph 的差距。
6. [docs/MIMO_INTEGRATION.md](docs/MIMO_INTEGRATION.md)：MiMo Chat Completions 适配和拟执行命令。
7. [docs/phases/README.md](docs/phases/README.md)：每阶段计划、技术讲解和结果文档的统一规范。

每个实现阶段由单独分支对话完成，并维护 `PLAN.md`、`CONCEPTS.md`、`RESULTS.md`。当前主对话负责批准计划、复审结果、决定下一阶段，并更新上述长期文档。已完成历史只追加勘误；未开始阶段允许根据真实结果调整。

## 冻结身份

- 上游：`https://github.com/langchain-ai/open-swe.git`
- Commit：`daab5de0baf2d8b16a7e2ae3fadbcb632bace8cc`
- Reviewer graph：`agent.graphs.reviewer:traced_reviewer_agent`
- Reviewer factory：`agent.reviewer:get_reviewer_agent`
- 本地只读 checkout：`/home/zhengwenyi/projects/open-swe-upstream`

完整身份见 `upstream_lock.json`。

## 离线复现

```bash
cd /home/zhengwenyi/projects/open-swe-github-review-agent
source .venv/bin/activate

python scripts/materialize_phase1_fixture.py --check
python -m unittest discover -s tests -v
python scripts/run_fake_review.py
python scripts/run_mimo_preflight.py --check
```

Fake 输出位于被 Git 忽略的 `artifacts/fake_review/`。它验证 Schema、Diff 行锚定、测试结果与 Markdown 渲染，不代表官方 Open SWE 云端 Reviewer 已执行。

## 边界

第一版不包含 Slack、Linear、Web UI、自动 Merge、默认分支写入、自动修复、多 Agent 平台、训练数据管线或企业级部署。旧项目 `/home/zhengwenyi/projects/swe-agent` 保持只读；不会复制其 Agent loop、配置、Parser、Trajectory 或历史证据。

架构依据与差异见 `docs/UPSTREAM_AND_ARCHITECTURE.md`，MiMo 拟执行步骤见 `docs/MIMO_INTEGRATION.md`。
