from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from django.conf import settings


@dataclass
class GatewayResult:
    ok: bool
    code: str = ""
    message: str = ""
    authority: str = ""
    reference_id: str = ""
    redirect_url: str = ""


class ZarinPalGateway:
    def __init__(self):
        self.merchant_id = getattr(settings, "ZARINPAL_MERCHANT_ID", "").strip()
        self.sandbox = bool(getattr(settings, "ZARINPAL_SANDBOX", True))
        self.currency = str(getattr(settings, "PAYMENT_CURRENCY", "IRR")).upper()
        self.timeout = int(getattr(settings, "PAYMENT_TIMEOUT", 15))
        base = "https://sandbox.zarinpal.com" if self.sandbox else "https://api.zarinpal.com"
        start = "https://sandbox.zarinpal.com/pg/StartPay/" if self.sandbox else "https://www.zarinpal.com/pg/StartPay/"
        self.request_url = f"{base}/pg/v4/payment/request.json"
        self.verify_url = f"{base}/pg/v4/payment/verify.json"
        self.start_url = start

    def _post_json(self, url: str, payload: dict) -> dict:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=body, method="POST", headers={
            "Content-Type": "application/json", "Accept": "application/json", "User-Agent": "Giftweb-Django/2.0",
        })
        with urllib.request.urlopen(req, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def _amount(self, toman: int) -> int:
        # Giftweb stores prices as Toman. IRR mode sends Rial (Toman x 10).
        return int(toman) * 10 if self.currency == "IRR" else int(toman)

    def create_payment(self, *, amount_toman: int, callback_url: str, description: str, mobile: str = "", email: str = "") -> GatewayResult:
        if not self.merchant_id:
            return GatewayResult(False, code="CONFIG", message="ZARINPAL_MERCHANT_ID تنظیم نشده است.")
        if self.currency not in {"IRR", "IRT"}:
            return GatewayResult(False, code="CONFIG", message="PAYMENT_CURRENCY باید IRR یا IRT باشد.")
        payload = {
            "merchant_id": self.merchant_id,
            "amount": self._amount(amount_toman),
            "callback_url": callback_url,
            "description": description[:255],
            "metadata": {"mobile": mobile, "email": email},
        }
        if self.currency == "IRT":
            payload["currency"] = "IRT"
        try:
            data = self._post_json(self.request_url, payload)
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            return GatewayResult(False, code="NETWORK", message=f"ارتباط با درگاه برقرار نشد: {exc}")
        result = data.get("data") or {}
        errors = data.get("errors") or {}
        code = str(result.get("code", errors.get("code", "")))
        authority = str(result.get("authority", "") or "")
        if code == "100" and authority:
            return GatewayResult(True, code=code, message=str(result.get("message", "Success")), authority=authority, redirect_url=self.start_url + authority)
        return GatewayResult(False, code=code, message=str(errors.get("message") or result.get("message") or "خطا در ایجاد تراکنش."))

    def verify_payment(self, *, amount_toman: int, authority: str) -> GatewayResult:
        if not self.merchant_id:
            return GatewayResult(False, code="CONFIG", message="ZARINPAL_MERCHANT_ID تنظیم نشده است.")
        payload = {"merchant_id": self.merchant_id, "amount": self._amount(amount_toman), "authority": authority}
        try:
            data = self._post_json(self.verify_url, payload)
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            return GatewayResult(False, code="NETWORK", message=f"ارتباط برای تأیید پرداخت برقرار نشد: {exc}")
        result = data.get("data") or {}
        errors = data.get("errors") or {}
        code = str(result.get("code", errors.get("code", "")))
        ref = str(result.get("ref_id", "") or "")
        if code in {"100", "101"}:
            return GatewayResult(True, code=code, message=str(result.get("message", "Paid")), reference_id=ref, authority=authority)
        return GatewayResult(False, code=code, message=str(errors.get("message") or result.get("message") or "پرداخت تأیید نشد."), authority=authority)


def get_gateway():
    gateway_name = str(getattr(settings, "PAYMENT_GATEWAY", "zarinpal")).lower()
    if gateway_name == "zarinpal":
        return ZarinPalGateway()
    raise RuntimeError(f"درگاه پرداخت پشتیبانی نمی‌شود: {gateway_name}")
