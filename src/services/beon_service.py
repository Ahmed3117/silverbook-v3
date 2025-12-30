import logging
from typing import List, Union

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 10


def _build_phone_list(phone_numbers: Union[str, List[str]]) -> List[str]:
    """Normalize phone numbers into a list of strings."""
    if isinstance(phone_numbers, str):
        phone_numbers = [phone_numbers]
    return [str(phone).strip() for phone in phone_numbers if str(phone).strip()]


def send_beon_sms(phone_numbers: Union[str, List[str]], message: str) -> dict:
    """Send an SMS message through the BeOn API.

    Returns a dictionary containing a success flag and any returned data/error details.
    """
    normalized_numbers = _build_phone_list(phone_numbers)
    if not normalized_numbers:
        logger.error("BeOn SMS: phone number list is empty")
        return {"success": False, "error": "Phone number list is empty"}

    api_url = getattr(settings, "BEON_SMS_BASE_URL", "https://v3.api.beon.chat/api/v3/messages/sms/bulk")
    token = getattr(settings, "BEON_SMS_TOKEN", None)

    if not token:
        logger.error("BeOn SMS token is not configured")
        return {"success": False, "error": "BeOn SMS token is not configured"}

    payload = {
        "phoneNumbers": normalized_numbers,
        "message": message,
    }

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "beon-token": token,
    }

    try:
        response = requests.post(api_url, json=payload, headers=headers, timeout=DEFAULT_TIMEOUT)
        response.raise_for_status()
        try:
            data = response.json()
        except ValueError:
            data = {"raw": response.text}

        logger.info("BeOn SMS sent to %s", normalized_numbers)
        return {"success": True, "data": data}
    except requests.RequestException as exc:
        logger.exception("Failed to send BeOn SMS: %s", exc)
        error_detail = None
        if exc.response is not None:
            try:
                error_detail = exc.response.json()
            except ValueError:
                error_detail = exc.response.text

        return {
            "success": False,
            "error": str(exc),
            "detail": error_detail,
        }
