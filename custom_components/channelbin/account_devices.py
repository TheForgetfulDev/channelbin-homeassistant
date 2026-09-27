"""Per-account devices: which provider accounts the server reports, and the plain conversions
their sensors need.

Each account is its own device, linked under the ChannelBin device and keyed on the account
id, never its name, so a rename in ChannelBin renames the device without breaking an
automation. A server that sends no account list gets no account devices, and keeps the
ChannelBin device's sensors exactly as before, so reading the list needs no
MIN_CHANNELBIN_VERSION bump.

Kept free of Home Assistant imports so the ChannelBin repo's test suite can load this file on
its own (tests/test_ha_integration_packaging.py).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

# Home Assistant's limit on a state's length.
STATE_MAX_LENGTH = 255

# Lowercase because Home Assistant only translates lowercase enum states. A status this list
# does not know reads Unknown rather than raising: an enum sensor refuses a value outside
# its options.
ACCOUNT_STATUSES = ("ok", "error", "syncing", "unsynced")

ACCOUNT_MODELS = {"xtream": "Xtream account", "m3u": "M3U account"}


def account_list(data: Any) -> list[dict[str, Any]] | None:
    """The per-account list, or None for a server that does not send one."""
    accounts = data.get("accounts") if isinstance(data, dict) else None
    listed = accounts.get("list") if isinstance(accounts, dict) else None
    return listed if isinstance(listed, list) else None


def accounts_by_id(data: Any) -> dict[int, dict[str, Any]]:
    return {a["id"]: a for a in account_list(data) or () if isinstance(a, dict) and "id" in a}


def account_device_key(entry_id: str, account_id: int) -> str:
    return f"{entry_id}_account_{account_id}"


def account_id_of_device(domain: str, entry_id: str, identifiers) -> int | None:
    """The account a device stands for, or None for the ChannelBin device itself."""
    prefix = f"{entry_id}_account_"
    for ident_domain, ident in identifiers:
        if ident_domain == domain and isinstance(ident, str) and ident.startswith(prefix):
            try:
                return int(ident[len(prefix):])
            except ValueError:
                return None
    return None


def device_is_removable(domain: str, entry_id: str, identifiers, data: Any) -> bool:
    """Whether a user may delete this device by hand: only an account device whose account
    the server no longer reports. The ChannelBin device, and a live account's, would come
    straight back on the next poll."""
    account_id = account_id_of_device(domain, entry_id, identifiers)
    if account_id is None:
        return False
    return account_id not in accounts_by_id(data)


def utc_from_wire(value: Any) -> datetime | None:
    """A naive UTC ISO string off the wire, as the timezone-aware value a TIMESTAMP sensor
    requires. UTC is attached, never converted: treating the naive value as Home
    Assistant's local time would shift it by the UTC offset."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def status_state(value: Any) -> str | None:
    state = value.lower() if isinstance(value, str) else None
    return state if state in ACCOUNT_STATUSES else None


def truncated_state(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    if len(value) <= STATE_MAX_LENGTH:
        return value
    return value[:STATE_MAX_LENGTH - 3] + "..."
