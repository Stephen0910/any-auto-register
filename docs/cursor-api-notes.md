# Cursor 接口梳理

本文档记录当前项目里已经验证过、并接入的 Cursor Web 接口，供后续维护和迁移使用。

## 认证

- 当前实测可用的认证方式是只带 `WorkosCursorSessionToken`
- 代码里统一通过 `Cookie: WorkosCursorSessionToken=<token>` 调用
- 对应实现见 `platforms/cursor/switch.py`

## 已验证接口

### 1. 获取账号信息

- 方法：`GET https://cursor.com/api/auth/me`
- 用途：校验 token 是否有效，并拿到用户 `sub`
- 关键字段：
  - `email`
  - `sub`
  - `id`

### 2. 获取套餐/试用状态

- 方法：`GET https://cursor.com/api/auth/stripe`
- 用途：查询免费/订阅状态、试用资格、试用时长、账单状态
- 常见字段：
  - `membershipType`
  - `individualMembershipType`
  - `trialEligible`
  - `trialLengthDays`
  - `isOnBillableAuto`
  - `isYearlyPlan`

### 3. 查询是否已绑定有效支付方式

- 方法：`GET https://cursor.com/api/auth/has_valid_payment_method`
- 用途：判断账号是否已绑卡
- 响应示例：

```json
{
  "hasValidPaymentMethod": false
}
```

### 4. 查询 usage

- 方法：`GET https://cursor.com/api/usage?user=<sub>`
- 依赖：先调 `/api/auth/me` 取得 `sub`
- 用途：查询按模型分组的请求数、token 使用量，以及部分账号可见的上限字段
- 响应示例：

```json
{
  "gpt-4": {
    "numRequests": 0,
    "numRequestsTotal": 0,
    "numTokens": 0,
    "maxTokenUsage": null,
    "maxRequestUsage": null
  },
  "startOfMonth": "2026-03-21T06:40:25.120Z"
}
```

说明：

- 这是已验证可用的 usage 接口
- 但它不保证一定返回“额度上限”
- 当 `maxTokenUsage` / `maxRequestUsage` 为 `null` 时，只能展示已用量，无法精确计算剩余额度

### 5. 生成 7 天 Pro 试用结账链接

- 方法：`POST https://cursor.com/api/checkout`
- 请求体：

```json
{
  "tier": "pro",
  "allowTrial": true,
  "allowAutomaticPayment": false,
  "yearly": false
}
```

- 返回值：一个 Stripe Checkout URL 字符串
- 用途：为当前账号生成新的 7 天 Pro 试用入口

## 不建议直接对接的下游接口

HAR 中还能看到：

- `POST https://api.stripe.com/v1/payment_pages/<cs_live...>/init`

这个接口只是 Stripe Checkout 页面的下游初始化请求，不应作为项目对接入口。原因：

- `cs_live_*` 是动态生成的，不稳定
- `payment_pages/*` 依赖上游 checkout session
- 正确做法是调用 Cursor 自己的 `/api/checkout`

## 当前项目接入情况

### 已接入后端

- `platforms/cursor/plugin.py`
  - `get_account_state`
  - `switch_account`
  - `generate_trial_link`
- `platforms/cursor/switch.py`
  - `get_cursor_user_info`
  - `get_cursor_billing_info`
  - `has_cursor_valid_payment_method`
  - `get_cursor_usage`
  - `generate_cursor_checkout_link`

### 当前返回的数据

执行 `get_account_state` 时，当前会返回：

- `remote_user`
- `billing_info`
- `has_valid_payment_method`
- `trial_eligible`
- `trial_length_days`
- `membership_type`
- `usage_info`
- `usage_summary`
- `local_app_account`
- `quota_note`

## 已知限制

- `usage` 接口看起来是 Web 侧接口，未来存在变更风险
- 有些账号只能拿到 usage 已用量，拿不到 usage 上限
- 目前尚未发现稳定公开的“剩余次数”专用接口
- 因此前端展示时应把它视为“usage/额度提示”，而不是严格的“剩余配额结算”
