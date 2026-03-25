# 通用账号架构

本文档描述当前项目已经落地的账号归一化结构，以及新增平台时应遵循的建模边界。

## 重构目标

旧结构的问题主要有四类：

- `accounts` 主表混入平台特有字段，导致每接一个平台都想继续加列
- `status`、`trial_end_time`、`cashier_url` 这类字段语义混杂，本地状态和平台状态耦合
- `extra_json` 承担凭证、套餐、验证码邮箱、Provider 信息，难查询也难扩展
- 邮箱 Provider 的“账号”和“资源”没有拆层，像 MoeMail 这类先注册 Provider 再创建邮箱的场景无法通用表达

本轮重构后的原则是：

- `accounts` 只保留公共主字段，尤其保留 `password`
- 平台凭证、状态概览、Provider 账号、Provider 资源全部写入结构化子表
- 启动时先把历史旧列迁移进归一化结构，再从主表彻底删除
- API 可以继续返回兼容字段，但这些字段必须从归一化结构推导

## 当前表结构

### 1. `accounts`

账号主表，承载真正公共且稳定的主字段。

当前运行时核心字段：

- `id`
- `platform`
- `email`
- `password`
- `user_id`
- `created_at`
- `updated_at`

说明：

- `password` 明确保留在主表，属于所有平台都通用的公共字段
- 旧版 `region/token/status/trial_end_time/cashier_url/extra_json` 会在启动迁移时写入归一化表，然后从 `accounts` 主表删除

### 2. `account_overviews`

账号归一化概览表，用于表达账号状态和概览摘要。

关键字段：

- `lifecycle_status`
- `validity_status`
- `plan_state`
- `plan_name`
- `display_status`
- `remote_email`
- `checked_at`
- `summary_json`

其中 `summary_json` 用来承载“不值得单独建列、但又应该结构化保存”的摘要信息，例如：

- `trial_end_time`
- `cashier_url`
- `region`
- `trial_eligible`
- `membership_type`
- `usage_summary`
- `desktop_app_state`
- `quota_note`

### 3. `account_credentials`

平台凭证表，只存平台侧非密码凭证。

关键字段：

- `scope`
- `provider_name`
- `credential_type`
- `key`
- `value`
- `is_primary`
- `source`
- `metadata_json`

说明：

- 平台主密码不再重复写入本表
- `primary_token` 只是接口层的兼容输出，本质来自这里的主凭证记录

示例：

- Cursor: `access_token`、`refresh_token`、`session_token`
- ChatGPT: `access_token`、`refresh_token`、`cookies`
- Kiro: `accessToken`、`refreshToken`

### 4. `provider_accounts`

外部 Provider 账号表，表示“登录某个 Provider 本身所需的账号”。

关键字段：

- `provider_type`
- `provider_name`
- `login_identifier`
- `display_name`
- `credentials_json`
- `metadata_json`

适用场景：

- MoeMail provider 账号
- DuckMail provider 账号
- Freemail 管理账号
- 未来的短信、支付、工作区 Provider 账号

### 5. `provider_resources`

外部 Provider 资源表，表示“Provider 账号下面实际创建出的资源”。

关键字段：

- `provider_type`
- `provider_name`
- `resource_type`
- `resource_identifier`
- `handle`
- `display_name`
- `metadata_json`

适用场景：

- 验证码邮箱
- Provider 创建出的 mailbox
- Workspace / seat / profile / subscription endpoint

## 状态语义

### 1. `lifecycle_status`

本地流程维护的生命周期，不要求平台原生存在。

当前通用值：

- `registered`
- `trial`
- `subscribed`
- `expired`
- `invalid`

### 2. `plan_state`

平台套餐状态，来自平台接口、账单接口或使用量接口。

当前通用值：

- `trial`
- `subscribed`
- `free`
- `eligible`
- `expired`
- `unknown`

### 3. `validity_status`

账号有效性，来自 `check_valid`、`get_account_state` 或同类检查逻辑。

当前通用值：

- `valid`
- `invalid`
- `unknown`

### 4. `display_status`

前端展示状态，由概览层统一推导，不再直接读取旧版 `accounts.status`。

## 读写边界

### 写入

当前新写路径是：

1. 公共字段写入 `accounts`
2. 结构化字段通过 `sync_platform_account_graph()` 或 `patch_account_graph()` 写入归一化子表
3. 启动时 `init_db()` 会调用 `sync_all_account_graphs()`，把旧数据回填成新结构

### 读取

当前 API 和前端优先读取：

- `overview`
- `credentials`
- `provider_accounts`
- `provider_resources`
- `display_status`
- `lifecycle_status`
- `plan_state`
- `validity_status`

兼容保留的派生字段：

- `primary_token`
- `trial_end_time`
- `cashier_url`

这些字段仍可返回给旧前端或旧导出逻辑，但都必须从归一化结构推导，不能再回退到 `accounts.token` 等旧列。

## Provider 建模

邮箱/验证码等外部能力统一拆成两层：

### Provider Account

表示你登录 Provider 所需的账号。

例如 MoeMail：

- `username`
- `password`
- `session_token`

### Provider Resource

表示 Provider 下实际创建出的资源。

例如 MoeMail 创建出的邮箱：

- `resource_type = mailbox`
- `resource_identifier = email_id`
- `handle = 实际邮箱地址`

## 已接入 Provider 元数据

当前 `BasePlatform._attach_identity_metadata()` 会把结构化身份信息挂到账号上，并同步进归一化表。

已接入的邮箱 Provider 包括：

- `laoudo`
- `tempmail_lol`
- `duckmail`
- `cfworker`
- `moemail`
- `freemail`

同步落表位置：

- `provider_accounts`
- `provider_resources`
- `account_credentials`

## API 写入约定

`/api/accounts` 新增和更新现在支持两层输入：

公共字段：

- `email`
- `password`
- `user_id`

归一化扩展字段：

- `overview`
- `credentials`
- `provider_accounts`
- `provider_resources`
- `lifecycle_status`

兼容别名：

- `primary_token`
- `cashier_url`
- `region`
- `trial_end_time`

兼容别名会被折叠进归一化结构，不会再直接写回旧列。

其中：

- 列表状态徽章用 `display_status`
- 仪表盘统计按 `by_plan_state` / `by_lifecycle_status` / `by_validity_status`
- 详情页直接展示 provider 账号和平台凭证

## 新平台接入规范

新增平台时，建议遵循下面的输出方式：

### 注册阶段

注册或动作执行时，插件返回的 `Account.extra` / action data 中尽量包含：

- `account_overview`
- 平台 token / cookie / secret
- `provider_accounts`
- `provider_resources`

### 状态查询阶段

`get_account_state` 返回中尽量包含：

- `valid`
- `membership_type` 或 `plan`
- `trial_eligible`
- `usage_summary`
- `remote_user` / `portal_user`

运行时会自动把这些信息归一化到 `account_overviews`。

### 本地切换阶段

如果桌面客户端真实依赖多段凭证，不要只存一个 `token`，应同时输出：

- `access_token`
- `refresh_token`
- `session_token`
- 其它必要字段

这些会自动进入 `account_credentials`。如果某个平台仍需要 `token/region/extra` 这类旧形态，统一由 `core/platform_accounts.py` 从归一化数据反向投影给插件运行时。

## 后续还可以继续做的事

当前已经完成“结构层重构 + 读写接线 + 前端切换 + 桌面状态展示”。后续还可以继续增强：

- 给 `provider_accounts` / `account_credentials` 增加掩码显示和权限分级
- 增加 `account_snapshots` 历史快照表，保留每次查询结果
- 给 `list_accounts` 增加显式 `status_scope` 过滤参数，而不是兼容式混合过滤
