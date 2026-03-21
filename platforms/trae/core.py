"""Trae.ai 注册协议核心实现"""
import random, string
from typing import Optional, Callable

BASE_URL = "https://ug-normal.trae.ai"
API_SG   = "https://api-sg-central.trae.ai"
AID      = "677332"
SDK_VER  = "2.1.10-tiktok"
def _gen_verify_fp():
    """动态生成 verifyFp，避免固定值被封"""
    import secrets
    p0 = secrets.token_hex(4)
    parts = [secrets.token_hex(2)[:4] for _ in range(4)]
    tail = secrets.token_urlsafe(9)[:12]
    return "verify_" + p0 + "_" + "_".join(parts) + "_" + tail


def _rand_password(n=14):
    chars = string.ascii_letters + string.digits + "!@#"
    return "".join(random.choices(chars, k=n))


def _base_params():
    return {
        "aid": AID,
        "account_sdk_source": "web",
        "sdk_version": SDK_VER,
        "language": "en",
        "verifyFp": _gen_verify_fp(),
    }


class TraeRegister:
    def __init__(self, executor, log_fn: Callable = print):
        self.ex = executor
        self.log = log_fn
        self._verify_fp = _gen_verify_fp()

    def _params(self):
        return {
            "aid": AID,
            "account_sdk_source": "web",
            "sdk_version": SDK_VER,
            "language": "en",
            "verifyFp": self._verify_fp,
        }

    def step1_region(self):
        self.ex.post(f"{BASE_URL}/passport/web/region/",
                     params=self._params(), data={"type": "2"})

    def step2_send_code(self, email: str) -> str:
        self.log("发送验证码...")
        r = self.ex.post(f"{BASE_URL}/passport/web/email/send_code/",
                         params=self._params(),
                         data={"type": "1", "email": email,
                               "password": "", "email_logic_type": "2"})
        if r.json().get("message") != "success":
            raise RuntimeError(f"send_code 失败: {r.text}")
        self.log("验证码已发送，等待邮件...")
        return r.json().get("data", {}).get("email_ticket", "")

    def step3_register(self, email: str, password: str, otp: str):  # 注意：不传 email_ticket，传了反而报 error_code 10
        self.log(f"提交注册... otp={otp}")

        r = self.ex.post(f"{BASE_URL}/passport/web/email/register_verify_login/",
                         params=self._params(),
                         data=data)
        j = r.json()
        if j.get("message") != "success" and not j.get("data", {}).get("user_id_str"):
            raise RuntimeError(f"register 失败: {r.text}")
        return j["data"]["user_id_str"]

    def step4_trae_login(self):
        self.ex.post(f"{BASE_URL}/cloudide/api/v3/trae/Login",
                     params={"type": "email"},
                     json={"UtmSource": "", "UtmMedium": "", "UtmCampaign": "",
                           "UtmTerm": "", "UtmContent": "", "BDVID": "",
                           "LoginChannel": "ide_platform"})

    def step5_get_token(self):
        r = self.ex.post(f"{API_SG}/cloudide/api/v3/common/GetUserToken", json={})
        return r.json().get("Result", {}).get("Token", "")

    def step6_check_login(self):
        r = self.ex.post(f"{BASE_URL}/cloudide/api/v3/trae/CheckLogin",
                         json={"GetAIPayHost": True, "GetNickNameEditStatus": True})
        return r.json().get("Result", {})

    def step7_create_order(self, token: str):
        try:
            r = self.ex.post(f"{API_SG}/trae/api/v1/pay/create_order",
                             headers={"Authorization": f"Cloud-IDE-JWT {token}"},
                             json={"product_ids": ["2"],
                                   "result_url": "https://www.trae.ai/account-setting"
                                                 "?type=upgrade&identity=1#subscription"})
            self.log(f"  create_order status={r.status_code} resp={r.text[:200]}")
            return r.json().get("order_info", {}).get("cashier_url", "")
        except Exception as e:
            self.log(f"  create_order 失败: {e}")
            return ""

    def register(self, email: str, password: str = None,
                 otp_callback: Optional[Callable] = None) -> dict:
        if not password:
            password = _rand_password()
        self.step1_region()
        email_ticket = self.step2_send_code(email)
        otp = otp_callback() if otp_callback else input("OTP: ")
        if not otp:
            raise RuntimeError("未获取到验证码")
        self.log(f"验证码: {otp}")
        user_id = self.step3_register(email, password, otp, email_ticket)
        self.step4_trae_login()
        token = self.step5_get_token()
        result = self.step6_check_login()
        cashier_url = self.step7_create_order(token)
        return {
            "email": email, "password": password,
            "user_id": user_id, "token": token,
            "region": result.get("Region", ""),
            "cashier_url": cashier_url,
            "ai_pay_host": result.get("AIPayHost", ""),
        }
