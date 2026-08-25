# 简历项目描述

## 1. 中文项目标题

**Open SWE GitHub Diff Review Agent｜Python、GitHub REST API、GitHub App、JSON Schema、MiMo V2.5 Pro**

## 2. 中文简历版（推荐）

基于固定版本 Open SWE Reviewer 约束实现 GitHub Diff Review 原型，构建 Diff 快照、candidate changed-line、结构化 Finding、JSON Schema/语义校验和 Markdown 输出链路；在本地三类缺陷实验中取得人工核心召回 `2/3`、Finding precision `2/2`、误报 `0`，并识别严重度一致上偏与结构化合同失败。进一步实现仅限单仓库的最小权限 GitHub App、目标 PR 与 Payload Hash 双人工 Gate，以及唯一 `COMMENT` Review 写路由；真实写入暴露模型错误行号锚定，系统停止重试并冻结负结果，明确区分“属于 Diff”与“语义上对应目标代码行”两类可靠性要求。

## 3. 中文三条 Bullet

- 基于 Open SWE Reviewer-compatible 约束实现 Python Code Review 流水线：固定 Base/Head 与 Diff，计算 candidate changed lines，使用 MiMo V2.5 Pro 生成严格 Review JSON，并通过 Draft 2020-12 Schema、运行时语义校验和确定性 Markdown 渲染。
- 设计四阶段受控实验：单题核心缺陷召回 `1/1`；三类 Smoke 人工召回 `2/3`、precision `2/2`、误报与重复 Finding 均为 `0`；真实公开 PR 通过 4 次只读 GET 完成 Base/Head、3 文件和 38 changed lines 快照闭环。
- 实现单仓库最小权限 GitHub App、Prepare/Publish 分离、Payload SHA256 人工审批、幂等 Marker 和单次 `COMMENT` 写入；发布后发现评论锚错一行，禁止重试并保留远端负结果，定位 changed-line membership 无法保证 Evidence 与具体代码行语义一致。

## 4. 一行精简版

实现基于 Open SWE 约束的 GitHub Diff Review Agent，以严格 changed-line 合同和最小权限 GitHub App 控制模型 Review；完成本地/真实 PR 四阶段实验，并通过一次错误锚点负结果定位语义行号验证缺口。

## 5. English version

**Open SWE GitHub Diff Review Agent | Python, GitHub REST API, GitHub App, JSON Schema, MiMo V2.5 Pro**

- Built an Open SWE Reviewer-compatible diff review pipeline that binds Base/Head commits, normalized diffs, candidate changed lines, structured findings, JSON Schema validation, runtime semantic checks, and deterministic Markdown output.
- Designed a four-phase evaluation: achieved `1/1` core-bug recall on the initial fixture and `2/3` human-reviewed recall with `2/2` finding precision and zero false findings on a three-category smoke set; validated a real public PR snapshot using four read-only GitHub requests across three files and 38 changed lines.
- Implemented a single-repository least-privilege GitHub App, separate target/payload approval gates, deterministic payload hashing, an idempotency marker, and exactly one `COMMENT` review write; preserved a real wrong-line-anchor failure without retrying, demonstrating that changed-line membership alone does not guarantee semantic anchor correctness.

## 6. 面试诚信边界

简历中不要写：

- 官方完整 Open SWE Pregel graph 已部署；
- GitHub 自动 Review 发布成功；
- 真实 PR recall/precision；
- 生产级、多仓库或无人值守系统。

如果面试官问 Phase 4，应主动说明：远端 Review 被创建，但评论锚在相邻错误行，因此最终状态是 `COMPLETED_WITH_VERIFICATION_FAILURE`。这不是隐藏的缺陷，而是项目最重要的实验结论之一。
