"""Server-side verification of Google Play purchases via the Android Publisher API.

Uses the service-account key in settings.GOOGLE_PLAY_SERVICE_ACCOUNT_JSON. Only `google-auth` and
`requests` (already installed) are needed - plain REST calls, no extra SDK.
"""
import json
from datetime import datetime, timezone as dt_timezone
from urllib.parse import quote

from django.conf import settings

_API = "https://androidpublisher.googleapis.com/androidpublisher/v3/applications"
_SCOPES = ["https://www.googleapis.com/auth/androidpublisher"]
_session = None

ACTIVE_STATES = {
    "SUBSCRIPTION_STATE_ACTIVE",
    "SUBSCRIPTION_STATE_IN_GRACE_PERIOD",
}


class PlayVerificationError(Exception):
    """Raised when a purchase cannot be verified. `status` is the HTTP status to return."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def is_configured():
    return bool(settings.GOOGLE_PLAY_SERVICE_ACCOUNT_JSON and settings.GOOGLE_PLAY_PACKAGE_NAME)


def _get_session():
    global _session
    if _session is not None:
        return _session
    if not is_configured():
        raise PlayVerificationError("Google Play billing is not configured on the server.", 503)
    from google.auth.transport.requests import AuthorizedSession
    from google.oauth2 import service_account

    try:
        info = json.loads(settings.GOOGLE_PLAY_SERVICE_ACCOUNT_JSON)
        creds = service_account.Credentials.from_service_account_info(info, scopes=_SCOPES)
    except Exception as e:  # bad JSON / bad key
        raise PlayVerificationError(f"Invalid Google Play service account configuration: {e}", 503)
    _session = AuthorizedSession(creds)
    return _session


def _parse_time(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(dt_timezone.utc)
    except ValueError:
        return None


def _get(url):
    resp = _get_session().get(url, timeout=20)
    if resp.status_code in (400, 404, 410):
        raise PlayVerificationError("Google Play does not recognise this purchase.", 400)
    if resp.status_code in (401, 403):
        raise PlayVerificationError(
            "The server's Google Play service account is not allowed to read this purchase. "
            "Check Play Console > API access permissions.",
            503,
        )
    if not resp.ok:
        raise PlayVerificationError(f"Google Play verification failed ({resp.status_code}).", 502)
    return resp.json()


def verify_subscription(purchase_token):
    """Return dict(active, product_id, expires_at, order_id, auto_renewing, state) for a subscription token."""
    pkg = settings.GOOGLE_PLAY_PACKAGE_NAME
    data = _get(f"{_API}/{pkg}/purchases/subscriptionsv2/tokens/{quote(purchase_token, safe='')}")
    items = data.get("lineItems") or []
    if not items:
        raise PlayVerificationError("Subscription has no line items.", 400)
    item = items[0]
    state = data.get("subscriptionState", "")
    expires_at = _parse_time(item.get("expiryTime"))
    return {
        "active": state in ACTIVE_STATES and (expires_at is None or expires_at > datetime.now(dt_timezone.utc)),
        "product_id": item.get("productId", ""),
        "expires_at": expires_at,
        "order_id": (data.get("latestOrderId") or ""),
        "auto_renewing": bool((item.get("autoRenewingPlan") or {}).get("autoRenewEnabled")),
        "state": state,
    }


def verify_one_time(product_id, purchase_token):
    """Return dict(active, product_id, order_id, consumed) for a one-time (day pass) purchase."""
    pkg = settings.GOOGLE_PLAY_PACKAGE_NAME
    data = _get(
        f"{_API}/{pkg}/purchases/products/{quote(product_id, safe='')}/tokens/{quote(purchase_token, safe='')}"
    )
    # purchaseState: 0 = purchased, 1 = canceled, 2 = pending
    return {
        "active": data.get("purchaseState") == 0,
        "product_id": product_id,
        "order_id": data.get("orderId", ""),
        "consumed": data.get("consumptionState") == 1,
    }
