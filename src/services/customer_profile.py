import re
from typing import Dict, Optional

DEFAULT_PHONE_LOCAL = "01000000000"
DEFAULT_PHONE_INTL = "+201000000000"
DEFAULT_COUNTRY = "Egypt"
DEFAULT_ADDRESS_SUFFIX = "Digital order"
DEFAULT_NAME = "Customer"
DEFAULT_LAST_NAME = "User"


def _normalize_phone(phone: Optional[str]) -> Dict[str, str]:
    """Return both local and international representations of the phone number."""
    if not phone:
        return {"local": DEFAULT_PHONE_LOCAL, "international": DEFAULT_PHONE_INTL}

    digits = re.sub(r"\D", "", phone)
    if not digits:
        return {"local": DEFAULT_PHONE_LOCAL, "international": DEFAULT_PHONE_INTL}

    if digits.startswith("20"):
        local_body = digits[2:]
        if not local_body.startswith("0"):
            local_body = "0" + local_body
        local = local_body
        international = "+" + digits
    elif digits.startswith("0"):
        local = digits
        international = "+2" + digits
    else:
        local = digits if digits.startswith("0") else "0" + digits
        international = "+20" + digits

    return {"local": local, "international": international}


def _split_name(full_name: Optional[str]) -> Dict[str, str]:
    if not full_name:
        return {"first": DEFAULT_NAME, "last": DEFAULT_LAST_NAME}
    parts = [part for part in full_name.strip().split(" ") if part]
    if not parts:
        return {"first": DEFAULT_NAME, "last": DEFAULT_LAST_NAME}
    first = parts[0]
    last = " ".join(parts[1:]) if len(parts) > 1 else DEFAULT_LAST_NAME
    return {"first": first, "last": last}


def _resolve_government_name(source) -> Optional[str]:
    if not source:
        return None
    try:
        display = source.get_government_display()
        if display:
            return display
    except AttributeError:
        pass
    return getattr(source, "government", None)


def get_customer_profile(pill) -> Dict[str, str]:
    """Build a unified customer profile for payment gateways.

    Changes:
    - Removed support for `pilladdress` (model removed).
    - Prefer `user.username` as the phone (frontend ensures username is a phone number).
      Use `parent_phone` only when `username` is not a valid local phone.
    """
    user = getattr(pill, "user", None)

    # Full name: prefer user.name then username then default
    full_name = getattr(user, "name", None) or getattr(user, "username", None) or DEFAULT_NAME

    # Phone: prefer username if it's a valid local phone, otherwise fallback to parent_phone
    def _is_valid_local_phone(value: Optional[str]) -> bool:
        if not value:
            return False
        digits = re.sub(r"\D", "", value)
        # Egyptian local mobile numbers: start with '01' and have 11 digits total (01XXXXXXXXX)
        return bool(re.match(r"^01\d{9}$", digits))

    username_phone = getattr(user, "username", None)
    if _is_valid_local_phone(username_phone):
        phone = username_phone
    else:
        phone = getattr(user, "parent_phone", None)

    # Email fallback
    user_email = getattr(user, "email", None)
    email = user_email or f"customer_{getattr(pill, 'id', 'unknown')}@bookefay.com"

    # Address / government
    government_name = _resolve_government_name(user) or DEFAULT_COUNTRY
    address_line = f"{DEFAULT_ADDRESS_SUFFIX} - {government_name}"

    phone_numbers = _normalize_phone(phone)
    name_parts = _split_name(full_name)

    return {
        "full_name": full_name,
        "first_name": name_parts["first"],
        "last_name": name_parts["last"],
        "email": email,
        "phone": phone_numbers["local"],
        "international_phone": phone_numbers["international"],
        "address": address_line,
        "government": government_name or DEFAULT_COUNTRY,
    }
