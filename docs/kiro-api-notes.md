# Kiro 接口梳理

本文档记录当前项目里已验证过的 Kiro Web Portal / 桌面端相关接口，以及项目中的接入方式。

## 结论

Kiro 不只是能做 token 刷新校验。

基于抓包和实测，当前已经确认：

- 可以查询用户信息
- 可以查询订阅与 credits usage
- 可以查询可购买套餐列表
- 但这些 Portal 接口依赖浏览器 Web 会话，不是只拿 `accessToken` 就一定能调通

## Portal 调用前提

当前可稳定打通 Kiro Web Portal 的条件是：

- 有可用的 `accessToken`
- 有可用的 `sessionToken`
- 带浏览器 Cookie：
  - `AccessToken`
  - `SessionToken`
  - `Idp=BuilderId`
  - `UserId`

其中：

- `UserId` 可以先访问 `https://app.kiro.dev/account/usage` 后，从响应 Cookie 或 HTML 里的 `<meta name="user-id">` 提取
- `profileArn` 在当前项目里使用 `DEFAULT_PROFILE_ARN` 也已实测可用

## 已验证接口

### 1. 查询用户信息

- 方法：`POST https://app.kiro.dev/service/KiroWebPortalService/operation/GetUserInfo`
- 协议：`application/cbor`
- 认证：依赖上面的 Portal Cookie 组合
- 请求体：

```json
{
  "origin": "KIRO_IDE",
  "profileArn": "<profileArn>"
}
```

- 典型响应字段：
  - `email`
  - `status`
  - `idp`
  - `userId`
  - `featureFlags`

### 2. 查询 usage 与 limits

- 方法：`POST https://app.kiro.dev/service/KiroWebPortalService/operation/GetUserUsageAndLimits`
- 协议：`application/cbor`
- 请求体：

```json
{
  "origin": "KIRO_IDE",
  "isEmailRequired": true,
  "profileArn": "<profileArn>"
}
```

- 典型响应字段：
  - `subscriptionInfo.subscriptionTitle`
  - `subscriptionInfo.type`
  - `nextDateReset`
  - `daysUntilReset`
  - `overageConfiguration.overageEnabled`
  - `usageBreakdownList[*].currentUsage`
  - `usageBreakdownList[*].usageLimit`
  - `usageBreakdownList[*].freeTrialInfo.freeTrialStatus`
  - `usageBreakdownList[*].freeTrialInfo.freeTrialExpiry`
  - `usageBreakdownList[*].freeTrialInfo.usageLimit`

这意味着 Kiro 的“额度”并不是只能做模糊提示，当前已经能拿到较完整的 credits / trial / overage 信息。

### 3. 查询可购买套餐

- 方法：`POST https://app.kiro.dev/service/KiroWebPortalService/operation/GetAvailableSubscriptionPlans`
- 协议：`application/cbor`
- 请求体：

```json
{
  "profileArn": "<profileArn>"
}
```

- 当前抓包里已确认的套餐包括：
  - `KIRO_FREE`
  - `KIRO_PRO`
  - `KIRO_PRO_PLUS`
  - `KIRO_POWER`

### 4. 获取 account usage 页面

- 方法：`GET https://app.kiro.dev/account/usage`
- 用途：
  - 获取 Web 会话上下文
  - 提取 `UserId`

返回 HTML 中可以看到：

- `<meta name="user-id" ...>`
- `<meta name="idp" content="BuilderId">`

## 当前项目接入情况

### 已接入后端

- `platforms/kiro/switch.py`
  - `get_kiro_portal_state`
  - `summarize_kiro_usage`
- `platforms/kiro/plugin.py`
  - `get_account_state`
  - `switch_account`

### 当前返回的数据

执行 Kiro 的 `get_account_state` 时，当前会返回：

- `remote_validation`
- `portal_user`
- `usage_limits`
- `available_subscription_plans`
- `usage_summary`
- `portal_session`
- `local_app_account`
- `quota_note`

## 已知限制

- 这些接口依赖 `sessionToken` 浏览器会话
- 如果只有 `refreshToken/accessToken`，但没有有效 `sessionToken`，就无法稳定查询 Portal usage
- 因此前端展示时应把它理解为“可查询的订阅/credits 状态”，前提是该账号保存了可用的 Web 会话
