"""
Paymob payment gateway service.
Handles the 3-step flow: authenticate → create order → get payment key.
"""
import hmac
import hashlib
import requests
from django.conf import settings

PAYMOB_BASE = "https://accept.paymob.com/api"


class PaymobService:

    @staticmethod
    def _auth_token() -> str:
        """Step 1: Authenticate and return a short-lived auth token."""
        r = requests.post(
            f"{PAYMOB_BASE}/auth/tokens",
            json={"api_key": settings.PAYMOB_API_KEY},
            timeout=15,
        )
        r.raise_for_status()
        return r.json()["token"]

    @staticmethod
    def _create_paymob_order(auth_token: str, order_id: int, amount_cents: int) -> str:
        """Step 2: Register the order with Paymob and return the Paymob order ID."""
        r = requests.post(
            f"{PAYMOB_BASE}/ecommerce/orders",
            json={
                "auth_token": auth_token,
                "delivery_needed": False,
                "amount_cents": amount_cents,
                "currency": "EGP",
                "merchant_order_id": str(order_id),
                "items": [],
            },
            timeout=15,
        )
        r.raise_for_status()
        return str(r.json()["id"])

    @staticmethod
    def _get_payment_key(auth_token: str, paymob_order_id: str,
                         amount_cents: int, user) -> str:
        """Step 3: Request a payment key for the iframe."""
        r = requests.post(
            f"{PAYMOB_BASE}/acceptance/payment_keys",
            json={
                "auth_token": auth_token,
                "amount_cents": amount_cents,
                "expiration": 3600,
                "order_id": paymob_order_id,
                "currency": "EGP",
                "integration_id": settings.PAYMOB_INTEGRATION_ID,
                "billing_data": {
                    "first_name":    getattr(user, "first_name", None) or "N/A",
                    "last_name":     getattr(user, "last_name",  None) or "N/A",
                    "email":         user.email or "N/A",
                    "phone_number":  getattr(user, "phone", None) or "N/A",
                    "apartment":     "N/A",
                    "floor":         "N/A",
                    "street":        "N/A",
                    "building":      "N/A",
                    "shipping_method": "PKG",
                    "postal_code":   "N/A",
                    "city":          "N/A",
                    "country":       "EG",
                    "state":         "N/A",
                },
            },
            timeout=15,
        )
        r.raise_for_status()
        return r.json()["token"]

    @classmethod
    def initiate(cls, order, user) -> dict:
        """
        Full 3-step flow. Returns:
        {
            "payment_key":  "...",
            "paymob_order_id": "...",
            "iframe_url":   "https://accept.paymob.com/api/acceptance/iframes/<id>?payment_token=..."
        }
        """
        amount_cents = int(order.total_amount * 100)

        auth_token      = cls._auth_token()
        paymob_order_id = cls._create_paymob_order(auth_token, order.id, amount_cents)
        payment_key     = cls._get_payment_key(auth_token, paymob_order_id, amount_cents, user)

        iframe_url = (
            f"https://accept.paymob.com/api/acceptance/iframes/"
            f"{settings.PAYMOB_IFRAME_ID}?payment_token={payment_key}"
        )

        return {
            "payment_key":     payment_key,
            "paymob_order_id": paymob_order_id,
            "iframe_url":      iframe_url,
        }

    @staticmethod
    def verify_hmac(data: dict) -> bool:
        """
        Verify Paymob's HMAC signature on webhook callbacks.
        Paymob concatenates specific fields in a fixed alphabetical order.
        """
        # Fields Paymob uses for HMAC (fixed order defined by Paymob docs)
        hmac_fields = [
            "amount_cents", "created_at", "currency", "error_occured",
            "has_parent_transaction", "id", "integration_id", "is_3d_secure",
            "is_auth", "is_capture", "is_refunded", "is_standalone_payment",
            "is_voided", "order", "owner", "pending",
            "source_data.pan", "source_data.sub_type", "source_data.type",
            "success",
        ]

        obj = data.get("obj", data)  # webhook wraps data under "obj"

        def get_nested(d, key):
            """Resolve dot-notation keys like 'source_data.pan'."""
            parts = key.split(".")
            val = d
            for p in parts:
                val = val.get(p, "") if isinstance(val, dict) else ""
            return str(val)

        message = "".join(get_nested(obj, f) for f in hmac_fields)
        secret  = settings.PAYMOB_HMAC_SECRET.encode()
        computed = hmac.new(secret, message.encode(), hashlib.sha512).hexdigest()
        received = data.get("hmac", "")
        return hmac.compare_digest(computed, received)
