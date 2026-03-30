"""ChatGPT Keygen v5 — 纯协议注册机平台插件"""
from __future__ import annotations

from core.base_platform import BasePlatform, Account, AccountStatus, RegisterConfig
from core.base_mailbox import BaseMailbox
from core.registration import ProtocolMailboxAdapter, RegistrationResult
from core.registry import register


@register
class ChatGPTKeygenPlatform(BasePlatform):
    name = "chatgpt_keygen"
    display_name = "ChatGPT (Keygen v5)"
    version = "5.0.0"
    group = "chatgpt"
    supported_executors = ["protocol"]
    supported_identity_modes = ["mailbox"]

    def __init__(self, config: RegisterConfig = None, mailbox: BaseMailbox = None):
        super().__init__(config)
        self.mailbox = mailbox

    def check_valid(self, account: Account) -> bool:
        try:
            from platforms.chatgpt.payment import check_subscription_status
            class _A: pass
            a = _A()
            extra = account.extra or {}
            a.access_token = extra.get("access_token") or account.token
            a.cookies = extra.get("cookies", "")
            status = check_subscription_status(a, proxy=self.config.proxy if self.config else None)
            return status not in ("expired", "invalid", "banned", None)
        except Exception:
            return False

    def build_protocol_mailbox_adapter(self):
        def _build_worker(ctx, artifacts):
            from .worker import ChatGPTKeygenWorker
            from core.config_store import ConfigStore

            extra = (self.config.extra or {}) if self.config else {}
            cs = ConfigStore()
            mail_service_url = extra.get("mail_service_url") or cs.get("keygen_mail_service_url") or "http://10.10.10.8:5500"
            mail_provider = extra.get("mail_provider") or cs.get("keygen_mail_provider") or "tempmail_lol"

            return ChatGPTKeygenWorker(
                proxy_url=ctx.proxy,
                mail_service_url=mail_service_url,
                mail_provider=mail_provider,
                log_fn=ctx.log,
            )

        def _map_result(ctx, result):
            extra = result.extra if isinstance(result.extra, dict) else {}
            return RegistrationResult(
                email=result.email,
                password=result.password or (ctx.password or ""),
                user_id=result.account_id,
                token=result.access_token,
                status=AccountStatus.REGISTERED,
                extra={
                    "access_token": result.access_token,
                    "refresh_token": result.refresh_token,
                    "id_token": result.id_token,
                    "session_token": result.session_token,
                    "chatgpt_account_id": result.chatgpt_account_id,
                    "chatgpt_user_id": result.chatgpt_user_id,
                    "plan_type": result.plan_type,
                },
            )

        from core.registration import OtpSpec

        return ProtocolMailboxAdapter(
            result_mapper=_map_result,
            worker_builder=_build_worker,
            register_runner=lambda worker, ctx, artifacts: worker.run(
                email=ctx.identity.email,
                password=ctx.password,
            ),
            otp_spec=OtpSpec(wait_message="等待验证码..."),
        )

    def get_platform_actions(self) -> list:
        return [
            {"id": "get_account_state", "label": "查询账号状态/订阅", "params": []},
            {"id": "refresh_token", "label": "刷新 Token", "params": []},
        ]

    def execute_action(self, action_id: str, account: Account, params: dict) -> dict:
        proxy = self.config.proxy if self.config else None
        extra = account.extra or {}

        class _A: pass
        a = _A()
        a.access_token = extra.get("access_token") or account.token
        a.refresh_token = extra.get("refresh_token", "")
        a.session_token = extra.get("session_token", "")
        a.cookies = extra.get("cookies", "")

        if action_id == "get_account_state":
            from platforms.chatgpt.switch import fetch_chatgpt_account_state
            data = fetch_chatgpt_account_state(
                access_token=a.access_token,
                session_token=a.session_token,
                cookies=a.cookies,
                proxy=proxy,
            )
            return {"ok": True, "data": data}

        if action_id == "refresh_token":
            from platforms.chatgpt.token_refresh import TokenRefreshManager
            manager = TokenRefreshManager(proxy_url=proxy)
            result = manager.refresh_account(a)
            if result.success:
                return {"ok": True, "data": {
                    "access_token": result.access_token,
                    "refresh_token": result.refresh_token,
                }}
            return {"ok": False, "error": result.error_message}

        raise NotImplementedError(f"未知操作: {action_id}")
