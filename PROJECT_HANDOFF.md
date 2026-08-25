# Open SWE GitHub Review Agent：项目交接

> 给主审核对话和阶段分支对话使用。开始任何工作前先读本文件，再按需阅读总体框架和技术复盘。

## 1. 当前状态

```text
project=open-swe-github-review-agent
repository=/home/zhengwenyi/projects/open-swe-github-review-agent
phase_0_static_preparation=COMPLETED
phase_1_real_local_review=NOT_STARTED
paid_api_called=false
official_reviewer_graph_executed=false
github_app_created=false
github_write_performed=false
local_4b_run=false
training_started=false
old_mini_swe_project_modified=false
github_repository=https://github.com/zhengwenyi07-cmyk/open-swe-github-review-agent
git_remote_origin=PUSHED
next_step=REAL_MIMO_FIXED_DIFF_REVIEW_PROTOTYPE
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

- 13 项 unittest 通过。
- JSON Schema Draft 2020-12 合法。
- `pip check` 通过。
- Fixture Base/Candidate/Diff Hash 可重复。
- Fake workflow 可生成合同合法 JSON 和 Markdown。
- MiMo 离线检查为 `network=NOT_RUN`。
- 旧项目 HEAD 为 `a6610921630c51a58efe3970c0bf8a6844e96c32`，工作区干净。
- 官方 checkout 位于固定 Commit，工作区干净。
- 新仓库已完成首次提交并推送，`main` 正在跟踪 `origin/main`。

## 6. 当前分支对话任务

当前主审核对话应先复审并提交 Phase 0 静态基线。之后建立一个分支对话，只完成 Phase 1 原型：

1. 运行一次 MiMo Tool Call 预检。
2. 用最薄适配层把预配置 MiMo model 注入固定 Open SWE Reviewer 路径。
3. 使用现有固定 Fixture。
4. 以本地 JSON 和 Markdown 为终点。
5. 运行一次真实 Review。
6. 返回真实结果并停止。

分支不得创建 GitHub App、发布评论、运行本地 4B、训练、设计 3 题 Smoke 平台或启动下一阶段。

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

主对话收到结果后必须先区分：实现缺陷、基础设施失败、模型正常失败。然后再更新后续阶段，不能自动进入 Phase 2。

## 8. 当前允许与禁止

允许：

- 修改新仓库；
- 读取固定官方源码；
- 运行离线测试；
- 经人工批准调用一次 MiMo 预检和一次固定 Diff Review；
- 保存本地 JSON/Markdown 和必要日志。

禁止：

- 修改旧项目；
- GitHub 写入；
- 自动代码修改；
- 本地 4B 或训练；
- Docker 长任务；
- 自动重试正常模型失败；
- 为失败建立通用审计器或 r01/r02/r03 链；
- 擅自进入下一阶段。

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
