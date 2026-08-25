# Phase 4 讲解：最小权限 GitHub Review 发布

> 当前状态：`EXECUTED_ONCE_COMPLETED_WITH_VERIFICATION_FAILURE`
>
> 本文主要解释执行前设计。真实运行创建了远端 Review，但发布后验证失败且人工确认评论锚错一行；完整事实与证据边界见 `RESULTS.md`。

## 1. 为什么不是直接给 Phase 3 加一个 POST

Phase 3 的安全结论建立在“Client 根本没有写能力”上。Phase 4 一旦增加写入，会新增三类风险：权限过大、批准后内容被改变，以及网络失败导致重复发布。

因此 Phase 4 保留 Phase 3 的只读 Snapshot 与 Review 合同，把写入做成一个很窄的终点：只接受已经人工批准 Hash 的静态 Payload，只允许一个 `Create a review` endpoint。

## 2. GitHub Review、Review Comment 和 Issue Comment 的区别

GitHub PR 页面上看起来都是评论，但 API 语义不同：

- Pull Request Review：一次提交包含总体 body、event 和零到多个 inline comments；
- Review Comment：单独创建一条 Diff 行评论；
- Issue Comment：写入 PR 时间线，不锚定 Diff。

本阶段只用 Pull Request Review，因为一次 POST 可以把总体披露和多个 Finding 绑定到同一个 review id，证据边界最清楚。其他两种写接口全部禁止。

## 3. 为什么 event 固定为 COMMENT

GitHub Review 的 `APPROVE` 和 `REQUEST_CHANGES` 可能参与分支保护或影响维护者判断。实验原型没有资格自动改变合并门禁。

`COMMENT` 会发布 Review 内容，但不会表达正式批准或阻止合并。模型自己的 `decision` 仍保存在本地 `review.json`，不能直接映射成 GitHub event。

## 4. 为什么使用 line/side 而不是 position

GitHub 的旧 `position` 参数表示从 Diff hunk 起算的位置，不等同于文件行号，且官方正在收紧该用法。当前接口支持：

```text
path=<relative file path>
line=<candidate blob line>
side=RIGHT
```

项目现有 changed-line parser 已输出 candidate-side 文件行号，因此第一版只发布 `RIGHT` 侧单行评论，避免引入 deleted-line、multi-line 和跨 hunk 映射。

真实结果补充：Create Review 接受了 `line/side` Payload，但随后 `List review comments` 返回的是 `position/original_position`，没有验证器预期的 `line/side`，导致终态复核失败。人工再将 position 与 Diff 对照时发现，Payload 的第 7 行本身也不对应 Finding 文字描述的第 8 行缺陷。这说明 API 坐标兼容和模型语义锚点是两个独立问题。

## 5. GitHub App 最小权限的真实含义

GitHub App 默认没有权限。Phase 4 需要调用 Create Review，因此仓库权限必须包含 `Pull requests: Read and write`。这项权限在 GitHub 平台层面可能覆盖不止一个 endpoint，所以“最小权限”不能只靠 App 设置，还要靠代码的 host/path/method allowlist 将实际能力压缩到一个 POST。

App 只安装到测试仓库。即使 installation token 被误用，它也不应访问其他仓库。Contents、Issues、Checks、Actions 与 Administration 均不授权。

## 6. JWT 与 installation token

GitHub App 私钥用来签发短期 JWT，JWT 只用于向 GitHub 请求 installation token。installation token 再用于读取 PR 和发布 Review。

生命周期：

```text
private key (disk, outside Git)
  -> short-lived JWT (memory)
  -> POST installation token endpoint
  -> short-lived installation token (memory)
  -> allowed PR API requests
  -> process exits, token discarded
```

不能假设 Token 是固定前缀或固定长度；代码只把它当作秘密字符串。产物只记录 App/installation/repository 的非秘密身份与权限摘要。

## 7. 为什么准备和发布必须分开

如果 Runner 在模型输出后立即 POST，人类只能事后发现错误。Phase 4 把“模型推理”和“外部副作用”切开：

1. 准备动作生成 deterministic `publish_payload.json`；
2. 人类阅读准确文字和锚点；
3. approval contract 锁定 Payload SHA256；
4. 发布动作只读该文件，不再运行模型。

这样可以证明 GitHub 上出现的内容就是人类批准的内容，而不是“同一 Prompt 再跑一次后大概相同”的内容。

## 8. 确定性 Payload

同一个 Review 应总是生成同一份 JSON 字节。实现需要固定：

- key 顺序；
- UTF-8；
- 换行与空白；
- Finding 排序；
- body 模板；
- Marker；
- Head SHA；
- event 与 side。

Payload Hash 同时绑定内容和目标快照。人工批准后任何文字、行号或 Head 变化都会使 Hash 不匹配并在 POST 前失败。

## 9. 幂等 Marker

GitHub Create Review 没有客户端提供的通用幂等键。项目在 Review body 中加入不可见 HTML Marker，并在发布前列出已有 Reviews。Marker 由 repository、PR、Head SHA 与 `review.json` SHA256 计算；不能直接包含 `publish_payload.json` SHA256，否则会产生自引用 Hash。

Marker 不是为了删除或更新评论，而是为了检测：同一目标、同一 Head、同一 Payload 是否已经发布。存在 Marker 时直接停止，不能“再发一遍试试”。

## 10. 不确定写入状态

最危险的场景是 GitHub 已接受 POST，但客户端在收到响应前断线。此时重试会制造重复 Review。

处理方式：

1. 不重试 POST；
2. 只读列出 Reviews 并寻找唯一 Marker；
3. 找到唯一项则恢复回执；
4. 找不到或多个匹配则记录 `AMBIGUOUS_WRITE_STATE`，交给人工查看 GitHub 页面。

“最多一次 POST”比“确保最终成功”更重要，因为本阶段研究的是受控副作用。

## 11. Head SHA 漂移

Inline comment 的行号属于特定 Head Diff。准备后 PR 可能收到新 Commit。发布前必须重新读取 PR metadata，并要求 Head SHA 与 approval contract 完全一致。

若漂移，旧 Payload 作废。Phase 4 不自动读取新 Diff、重新调用模型或移动评论位置；主对话决定是否终止阶段。

## 12. 为什么只发布 confirmed Finding

现有 Review 合同区分：

- Finding：模型认为有具体证据的问题；
- Suggestion：改进建议；
- Uncertainty：证据不足的问题。

自动把 Suggestion 或 Uncertainty 变成行内评论容易制造噪声。第一版只允许人工复核后的 confirmed Finding。其他内容仍保存在本地 Markdown，必要时由人类自行决定是否讨论。

## 13. 披露文本

发布的 Review 应明确说明：

- 来源是实验性自动代码审查 Agent；
- 已经过人工发布批准；
- 只审查 Diff；
- 未执行 PR 代码或测试；
- 证据可以通过仓库 Commit/Hash 追踪。

这既防止维护者误解，也能在面试中体现结果边界意识。

## 14. 写入证据

仅保存“发生了什么”，不保存认证材料：

- approved repository、PR、Base/Head；
- Payload SHA256；
- GitHub review id、state、commit id、HTML URL；
- POST 数量和精确 endpoint 类型；
- exact review 与该 review comments 的 verification GET 结果 Hash；
- 每条远端 comment 的 path、line、side 与 body 是否等于批准 Payload；
- Marker 是否唯一；
- GitHub 写入、Merge、Check、Issue 等计数；
- 人工页面复核结论。

## 15. 失败如何解释

- App token 获取失败：认证或权限配置问题，未评价模型。
- Snapshot/Head 漂移：目标状态变化，Payload 不再安全。
- Review 没有 confirmed Finding：模型结果，不应伪造写入。
- Payload 合同失败：本地实现问题，禁止发布。
- POST 返回 403/422：权限或 GitHub 接口问题，禁止换接口绕过。
- 模糊写入状态：必须人工查看，不重试。
- POST 成功但 GET 内容不符：严重实现/平台一致性失败，不修改已发布内容。

## 16. 与 Phase 3 的连续性

继续复用：

- metadata A/files/diff/metadata B 快照协议；
- 输入预算；
- changed-line parser；
- MiMo 单调用与模型身份校验；
- Review Schema 和 Markdown renderer；
- Prompt Injection 边界；
- 合同失败不补跑。

Phase 4 新增的唯一研究变量是受控 GitHub Review 发布。不能顺便加入测试执行、自动修复、Check Run、Webhook 或官方完整 Pregel graph。

## 17. 官方接口依据

实现前应再次核对 GitHub 官方文档：

- [Create a review for a pull request](https://docs.github.com/en/rest/pulls/reviews)；
- [Pull request review comments](https://docs.github.com/en/rest/pulls/comments) 的 line/side 语义；
- [Choosing permissions for a GitHub App](https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/choosing-permissions-for-a-github-app)；
- [Generating an installation access token](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-an-installation-access-token-for-a-github-app)。

当前计划依据：Create Review 支持 GitHub App installation token，并要求 Pull requests repository permission 为 write；GitHub 建议使用 `line`/`side` 描述行评论；App 默认无权限，应按 endpoint 选择最小权限；installation token 是短期凭据。

## 18. 当前未知

- 测试 PR 编号与 Base/Head；
- GitHub App id 与 installation id（不得写入本文）；
- MiMo 是否会生成 confirmed Finding；
- 实际 Payload 文本、Hash 和评论数量；
- App token 与发布调用耗时；
- GitHub review id 与页面 URL；
- 是否发生 Head 漂移或模糊写入；
- Phase 4 最终是 `COMPLETED` 还是 `PREPARED_NOT_PUBLISHED`。

这些只能写入 `RESULTS.md` 的真实结果栏。
