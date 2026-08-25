# Open SWE GitHub Review Agent：项目交接

> 给主审核对话和阶段分支对话使用。开始任何工作前先读本文件，再按需阅读总体框架和技术复盘。

## 1. 当前状态

```text
project=open-swe-github-review-agent
repository=/home/zhengwenyi/projects/open-swe-github-review-agent
phase_0_static_preparation=COMPLETED
phase_1_real_local_review=COMPLETED
phase_1_plan_documents=READY
paid_api_called=true
phase_1_core_bug_recall=1/1
phase_2_plan_documents=READY
phase_2_offline_implementation=COMPLETED
phase_2_three_task_smoke=COMPLETED_WITH_FAILURES
phase_2_status=COMPLETED_WITH_FAILURES
phase_2_human_core_bug_recall=2/3
phase_2_human_finding_precision=2/2
phase_2_retry_allowed=false
severity_bias=SYSTEMATIC_ONE_LEVEL_OVERESTIMATION_OBSERVED
phase_3_plan_status=COMPLETED
phase_3_execution_status=COMPLETED
phase_3_target_contract_status=APPROVED_AND_CONSUMED
phase_3_repository=pallets/click
phase_3_pull_number=3021
phase_3_review_decision=APPROVE
phase_3_finding_count=0
phase_3_uncertainty_count=1
github_read_performed=true
phase_4_plan_status=COMPLETED
phase_4_implementation_status=COMPLETED
phase_4_target_status=APPROVED_AND_CONSUMED
phase_4_prepare_status=PASS
phase_4_publish_status=COMPLETED_WITH_VERIFICATION_FAILURE
official_reviewer_graph_executed=false
github_app_created=true
github_write_performed=true
github_review_write_requests=1
phase_4_retry_allowed=false
review_publish_allowed=false
local_4b_run=false
training_started=false
old_mini_swe_project_modified=false
github_repository=https://github.com/zhengwenyi07-cmyk/open-swe-github-review-agent
git_remote_origin=PUSHED
next_step=HUMAN_PROJECT_REVIEW
```

第一优先级是尽快获得可工作的 Diff Review 原型，不增加工业级证据冻结或新的前置阶段。

GitHub 仓库已经创建，`origin` 固定为 `https://github.com/zhengwenyi07-cmyk/open-swe-github-review-agent.git`。

## 2. 项目与上游路径

- 新项目：`/home/zhengwenyi/projects/open-swe-github-review-agent`
- 官方只读 checkout：`/home/zhengwenyi/projects/open-swe-upstream`
- 旧项目只读基线：`/home/zhengwenyi/projects/swe-agent`
- 上游 Commit：`daab5de0baf2d8b16a7e2ae3fadbcb632bace8cc`

旧项目不得修改。不要把新项目作为旧项目 Stage 6，也不要复制 mini-swe Agent loop。

## 3. 文档阅读顺序

1. `PROJECT_HANDOFF.md`：现在在哪里、下一步做什么。
2. `OPEN_SWE_GITHUB_REVIEW_FRAMEWORK.md`：总体路线、阶段和调整规则。
3. `OPEN_SWE_CONCEPTS_AND_RESULTS.md`：概念、源码路径、实现和真实结果。
4. `docs/UPSTREAM_AND_ARCHITECTURE.md`：官方 Reviewer 依据与当前差距。
5. `docs/MIMO_INTEGRATION.md`：MiMo 参数、秘密边界和拟执行命令。
6. `INTERVIEW_GUIDE.md`：面试讲述、问题和不可夸大边界。
7. `docs/phases/README.md`：每阶段 `PLAN`、`CONCEPTS`、`RESULTS` 文档规范。

## 4. 已完成文件

核心实现：

- `src/open_swe_review_agent/diff_parser.py`
- `src/open_swe_review_agent/contracts.py`
- `src/open_swe_review_agent/workflow.py`
- `src/open_swe_review_agent/fakes.py`
- `src/open_swe_review_agent/render.py`
- `src/open_swe_review_agent/mimo.py`

合同与 Fixture：

- `schemas/review.schema.json`
- `fixtures/phase1_logic_error/fixture.json`
- `fixtures/phase1_logic_error/diff.patch`
- `upstream_lock.json`

脚本与测试：

- `scripts/materialize_phase1_fixture.py`
- `scripts/run_fake_review.py`
- `scripts/run_mimo_preflight.py`
- `tests/test_review_workflow.py`
- `tests/test_mimo_adapter.py`

## 5. 已验证事实

- 39 项 unittest 通过，其中 Phase 2 专项 `15/15`。
- JSON Schema Draft 2020-12 合法。
- `pip check` 通过。
- Fixture Base/Candidate/Diff Hash 可重复。
- Fake workflow 可生成合同合法 JSON 和 Markdown。
- MiMo Preflight 与 Phase 1 真实 Review 均为 `PASS`。
- 核心缺陷召回 `1/1`，Finding 准确锚定 `calculator.py:2`，虚假 Finding 为 `0`。
- Phase 1 使用 Reviewer-compatible local slice；官方完整 Pregel graph 尚未运行。
- Phase 2 的逻辑、边界和权限三道 Fixture 已冻结，三个 Candidate 固定测试均真实返回 `1`。
- Phase 2 已按冻结合同执行一次：边界和权限题生成有效 Review，逻辑题因 `REVIEW_CONTRACT_FAILURE` 失败关闭。
- 人工核心缺陷召回为 `2/3`，Finding precision 为 `2/2`，虚假和重复 Finding 均为 `0`。
- Phase 1 与 Phase 2 的三个可观察正确 Finding 均高估一个严重度等级；这是小样本观察，不是统计证明。
- Phase 2 的核心召回先经冻结语义 rubric 筛选，最终指标由主对话人工确认；单题失败会保存脱敏证据并继续，且不存在自动进入下一阶段的门槛。
- Phase 2 失败证据区分六个固定执行阶段及模型响应子原因；Scoring Rubric 与 Fixture 预期身份会交叉验证。
- Phase 3 已在公开 PR `pallets/click#3021` 上完成唯一一次正式只读运行，并由主对话人工复审通过；六份原始产物及 SHA256 已冻结。
- Phase 3 采用 PR metadata 双读、Base/Head SHA 稳定性、files/raw diff 交叉校验和 changed-line 门禁；patch 缺失或超限时失败关闭。
- Phase 3 快照固定 Base `27aaed3...`、Head `27de74a...`、3 个 changed files、4,659 bytes raw diff 和 38 个 candidate changed lines；各层身份验证一致。
- MiMo 只调用 1 次，返回 `APPROVE`、0 个 Finding、1 个锚定 `src/click/termui.py:122` 的 Uncertainty；Schema 与语义验证通过。
- 该 PR 没有冻结人工 Gold Finding，不能声称召回率或 Finding precision；只读模式未执行 PR 测试，`APPROVE` 不是运行时正确性证明。
- Phase 3 共执行 4 次 GitHub GET，写请求为 0；没有执行 PR 代码、发布 Review 或自动重试。
- Phase 3 专项离线测试 `25/25`、完整回归 `64` 项通过（另有 1 项既有已消费生命周期跳过）。
- Phase 4 已在所有者控制的 PR #1 上运行：最小权限 GitHub App、目标合同、Prepare 和独立 Payload Hash Gate 均生效；唯一一次 Create Review 使用 `COMMENT`，没有 Issue Comment、Check Run、Merge、Branch 或 Contents 写入。
- 修复后 Prepare 使用 MiMo 一次生成 1 条可发布评论，Payload SHA256 为 `94ee086...9507a`；批准合同由提交 `d6864a3` 单独冻结。
- 唯一 Publish POST 已在远端创建 Review `5020924942` 和评论 `3854679061`，之后没有重试。Runner 因 `REMOTE_COMMENTS_MISMATCH` 失败关闭。
- 人工复核发现真正缺陷位于 `examples/phase4_average.py:8`，但 Payload 和远端评论锚定第 7 行；第 7 行是 `raise ValueError(...)`。因此最终状态为 `COMPLETED_WITH_VERIFICATION_FAILURE`，不能声称 Phase 4 PASS。
- 原始 `failure.json` 保持不变；远端副作用由独立只读复核写入 `post_publish_audit.json`。Phase 4 不补跑、不补发，也不通过编辑或删除远端内容掩盖结果。
- Phase 4 专项测试 `33/33`；Head 漂移、重复 Marker、Payload/终态篡改、非法 POST JSON 的歧义对账、远端回执保留和凭据脱敏均有离线覆盖。
- 旧项目 HEAD 为 `a6610921630c51a58efe3970c0bf8a6844e96c32`，工作区干净。
- 官方 checkout 位于固定 Commit，工作区干净。
- 新仓库已完成首次提交并推送，`main` 正在跟踪 `origin/main`。

## 6. 当前分支对话任务

Phase 2、Phase 3 和 Phase 4 都已完成一次性运行并进入证据冻结。Phase 4 的远端 Review 已创建，但发布后验证失败且人工确认行号锚点错误；不允许再次 POST、补发、编辑或删除来改变实验结果。当前只允许复审和冻结 Phase 4 证据、更新项目结论，再由主对话决定是否结束项目；不得自动进入 Phase 5。

## 7. 分支对话回报格式

分支完成后至少返回：

```text
目标是否完成：
修改文件：
实际运行命令：
模型/API配置：
模型调用次数：
Token/耗时/费用：
Review JSON路径与Hash：
Markdown路径与Hash：
Finding列表：
测试命令和返回码：
核心缺陷是否识别：
虚假问题：
Schema是否合法：
是否调用GitHub写API：
是否泄漏凭据：
失败与局限：
Git状态：
明确未执行内容：
```

主对话收到结果后必须先区分：实现缺陷、基础设施失败、模型正常失败。Phase 2 与 Phase 3 均已结束，不能补跑。Phase 4 当前停在离线实现复审门；不能自行创建 App/PR、调用 MiMo 或写入 GitHub。

## 8. 当前允许与禁止

允许：

- 修改新仓库；
- 读取固定官方源码；
- 运行离线测试；
- 只读检查已冻结的 Phase 3 证据和维护说明文档；
- 保存本地 JSON/Markdown 和必要日志。

禁止：

- 修改旧项目；
- 再次进行 GitHub Review 写入；
- 自动代码修改；
- 本地 4B 或训练；
- Docker 长任务；
- 自动重试正常模型失败；
- 为失败建立通用审计器或 r01/r02/r03 链；
- 擅自进入 Phase 5。

## 9. 常用离线命令

```bash
cd /home/zhengwenyi/projects/open-swe-github-review-agent
source .venv/bin/activate

python scripts/materialize_phase1_fixture.py --check
python scripts/run_fake_review.py
python scripts/run_mimo_preflight.py --check
python -m unittest discover -s tests -v
python -m pip check
git diff --check
git status --short
```

## 10. 主对话复审核对

每个分支结果至少问：

1. 运行的是官方 Reviewer 路径还是本地合同切片？
2. 输入是否真的是固定 Base/Candidate Diff？
3. Finding 是否落在 changed line？
4. 测试结果来自真实命令还是模型文本？
5. 是否把 uncertainty 伪装成 confirmed defect？
6. 是否发生未授权网络或 GitHub 写入？
7. 失败是否足以改变下一阶段？
8. 文档是否区分计划、实现和真实运行？

## 11. 文档维护责任

阶段分支只负责返回完整事实；主审核对话负责把结果写入总体框架、技术复盘和面试材料。已完成历史不得为配合新路线而重写，未完成阶段可以根据证据调整。
