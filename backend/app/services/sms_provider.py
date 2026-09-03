"""
SMS verification provider interface for phone verification during registration.
Supports 5sim, SMS-Activate, and custom providers.
"""
from abc import ABC, abstractmethod
import requests
import time
import re
import json
from dataclasses import dataclass
from typing import Optional


@dataclass
class SmsConfig:
    provider: str = "5sim"  # 5sim, sms-activate, smspool
    api_key: str = ""
    country: str = "Indonesia"  # Country for phone number
    operator: str = "any"  # Operator preference


class BaseSmsProvider(ABC):
    @abstractmethod
    def get_number(self, country: str, operator: str = "any") -> dict:
        pass

    @abstractmethod
    def get_otp(self, order_id: str, timeout: int = 120) -> Optional[str]:
        pass

    @abstractmethod
    def release_number(self, order_id: str):
        pass


class Sms5simProvider(BaseSmsProvider):
    BASE = "https://5sim.net/v1"

    def __init__(self, api_key: str):
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def get_number(self, country: str, operator: str = "any") -> dict:
        country_code = self._country_code(country)
        op = operator if operator != "any" else "any"
        url = f"{self.BASE}/user/buy/activation/{country}/{op}/microsoft"
        resp = requests.get(url, headers=self.headers, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            return {"order_id": str(data.get("id")), "phone": data.get("phone", "")}
        raise Exception(f"5sim get_number failed: {resp.status_code} {resp.text[:200]}")

    def get_otp(self, order_id: str, timeout: int = 120) -> Optional[str]:
        url = f"{self.BASE}/user/check/{order_id}"
        deadline = time.time() + timeout
        while time.time() < deadline:
            resp = requests.get(url, headers=self.headers, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                sms_list = data.get("sms", [])
                for sms in sms_list:
                    code = sms.get("code", "")
                    if code:
                        return code
                    text = sms.get("text", "")
                    match = re.search(r"(\d{4,8})", text)
                    if match:
                        return match.group(1)
            time.sleep(3)
        return None

    def release_number(self, order_id: str):
        url = f"{self.BASE}/user/finish/{order_id}"
        requests.get(url, headers=self.headers, timeout=30)

    def _country_code(self, country: str) -> str:
        mapping = {
            "Indonesia": "indonesia",
            "India": "india",
            "Philippines": "philippines",
            "Vietnam": "vietnam",
            "Thailand": "thailand",
            "Brazil": "brazil",
            "Mexico": "mexico",
            "Russia": "russia",
            "China": "china",
        }
        return mapping.get(country, country.lower().replace(" ", ""))


class SmsActivateProvider(BaseSmsProvider):
    BASE = "https://api.sms-activate.org/stubs/handler_api.php"

    def __init__(self, api_key: str):
        self.api_key = api_key

    def get_number(self, country: str, operator: str = "any") -> dict:
        country_id = self._country_id(country)
        params = {
            "api_key": self.api_key,
            "action": "getNumber",
            "service": "ms",
            "country": country_id,
        }
        resp = requests.get(self.BASE, params=params, timeout=30)
        text = resp.text
        if "ACCESS_NUMBER" in text:
            parts = text.split(":")
            return {"order_id": parts[1], "phone": parts[2]}
        raise Exception(f"SMS-Activate get_number failed: {text[:200]}")

    def get_otp(self, order_id: str, timeout: int = 120) -> Optional[str]:
        deadline = time.time() + timeout
        while time.time() < deadline:
            params = {
                "api_key": self.api_key,
                "action": "getStatus",
                "id": order_id,
            }
            resp = requests.get(self.BASE, params=params, timeout=30)
            text = resp.text
            if "STATUS_OK" in text:
                code = text.split(":")[1] if ":" in text else text
                match = re.search(r"(\d{4,8})", code)
                return match.group(1) if match else code
            time.sleep(3)
        return None

    def release_number(self, order_id: str):
        params = {
            "api_key": self.api_key,
            "action": "setStatus",
            "id": order_id,
            "status": "8",
        }
        requests.get(self.BASE, params=params, timeout=30)

    def _country_id(self, country: str) -> str:
        mapping = {
            "Indonesia": "6",
            "India": "1",
            "Philippines": "5",
            "Vietnam": "19",
            "Thailand": "14",
            "Brazil": "31",
            "Mexico": "38",
            "Russia": "7",
            "China": "1",
        }
        return mapping.get(country, "6")


class SmsService:
    def __init__(self, config: SmsConfig):
        self.config = config
        self._provider = self._create_provider()

    def _create_provider(self) -> BaseSmsProvider:
        if self.config.provider == "5sim":
            return Sms5simProvider(self.config.api_key)
        elif self.config.provider == "sms-activate":
            return SmsActivateProvider(self.config.api_key)
        raise ValueError(f"Unknown SMS provider: {self.config.provider}")

    def get_phone(self) -> dict:
        return self._provider.get_number(self.config.country, self.config.operator)

    def wait_for_otp(self, order_id: str, timeout: int = 120) -> Optional[str]:
        return self._provider.get_otp(order_id, timeout)

    def release(self, order_id: str):
        self._provider.release_number(order_id)

    def get_balance(self) -> float:
        try:
            if self.config.provider == "5sim":
                resp = requests.get(
                    "https://5sim.net/v1/user/profile",
                    headers={"Authorization": f"Bearer {self.config.api_key}"},
                    timeout=15,
                )
                if resp.status_code == 200:
                    return float(resp.json().get("balance", 0))
            elif self.config.provider == "sms-activate":
                params = {"api_key": self.config.api_key, "action": "getBalance"}
                resp = requests.get(SmsActivateProvider.BASE, params=params, timeout=15)
                text = resp.text
                if "ACCESS_BALANCE" in text:
                    return float(text.split(":")[1])
        except Exception:
            pass
        return 0.0
