# Phase 1～4 统一实验表

## 1. 总览

| 阶段 | 输入与目标 | 模型调用 | 核心结果 | GitHub 读/写 | 最终状态 |
|---|---|---:|---|---|---|
| Phase 1 | 固定逻辑回归 Diff；验证最小真实 Review 链路 | 1 次 Review；另有 1 次 Preflight | 核心缺陷召回 `1/1`；误报 `0`；严重度 `high→critical` | 0 / 0 | `COMPLETED` |
| Phase 2 | 逻辑、边界、权限三类冻结 Diff | 3 次，每题 1 次 | 人工召回 `2/3`；precision `2/2`；误报与重复均 `0`；1 次合同失败 | 0 / 0 | `COMPLETED_WITH_FAILURES` |
| Phase 3 | 公开 PR `pallets/click#3021`；验证真实 PR 只读快照 | 1 次 | 快照闭环；`APPROVE`；0 Finding；1 Uncertainty；无 Gold，不能报告召回率 | 4 GET / 0 POST | `COMPLETED` |
| Phase 4 | 所有者控制的 PR #1；验证最小权限受控发布 | 1 次 Prepare | 远端创建 1 个 Review，但回读验证失败且人工确认锚错一行 | Prepare 5 GET；Publish 1 POST | `COMPLETED_WITH_VERIFICATION_FAILURE` |

## 2. 统一指标

| 指标 | Phase 1 | Phase 2 | Phase 3 | Phase 4 |
|---|---:|---:|---:|---:|
| 任务/PR 数 | 1 | 3 | 1 | 1 |
| 合法 Review 数 | 1 | 2 | 1 | 本地 Review 合法；发布终态失败 |
| 人工核心缺陷召回 | `1/1` | `2/3` | 不适用，无 Gold | 模型识别缺陷，但锚点错误 |
| 人工 Finding precision | `1/1` | `2/2` | 不适用 | Finding 内容正确，位置错误，不能记为发布成功 |
| 虚假 Finding | 0 | 0 | 0 | 0；但有错误锚点 |
| 重复 Finding | 0 | 0 | 0 | 发布评论 1 条；无重复 POST |
| 严重度精确匹配 | `0/1` | `0/2` | 不适用 | 未冻结 Gold 严重度；模型给 `high` |
| 合同失败 | 0 | 1 | 0 | 1 次远端验证失败 |
| 自动重试 | 0 | 0 | 0 | 0 |
| PR 代码/测试执行 | 本地 Fixture 测试 | 本地 Fixture 测试 | 未执行 | 未执行 |

## 3. Token 与耗时

| 阶段 | Input Tokens | Output Tokens | Total Tokens | 记录耗时 |
|---|---:|---:|---:|---:|
| Phase 1 Review | 1,058 | 426 | 1,484 | 10.484 s |
| Phase 1 Preflight | 273 | 52 | 325 | 单独预检 |
| Phase 2 三题 | 3,155 | 1,473 | 4,628 | 成功两题合计 26.115 s；失败题耗时未保存 |
| Phase 3 | 2,937 | 2,987 | 5,924 | 63.601 s |
| Phase 4 Prepare | 1,208 | 500 | 1,708 | 12.379 s |

费用没有可靠账单归因，因此统一记录为 `NOT_AVAILABLE`，不估算或补造。

## 4. 阶段性结论如何演进

1. Phase 1 证明强模型可以在最小本地合同切片上识别真实逻辑回归。
2. Phase 2 证明能力可跨边界和权限缺陷，但暴露结构化合同失败与严重度一致上偏。
3. Phase 3 证明 GitHub PR 可以替代本地 Fixture，同时保持 Base/Head、Diff 和 changed-line 的只读闭环。
4. Phase 4 证明权限控制、双人工 Gate、确定性 Payload 和单次写路由可真实运行；同时证明 changed-line membership 不足以保证语义锚点正确。

## 5. 最终研究判断

项目已经实现从固定 Diff 到真实 GitHub PR、再到受控 Review 写入的完整路径探索，但没有达到“可靠自动发布”的标准。最关键的剩余缺口不是模型是否能描述缺陷，而是 Finding 的自然语言 Evidence 与目标行代码之间缺少强一致性验证。

Phase 4 不重试，Phase 5 暂不启动。该决定保留了负结果的真实性，也避免用额外运行把一次错误外部副作用掩盖掉。
