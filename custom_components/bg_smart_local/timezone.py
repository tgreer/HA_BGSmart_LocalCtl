"""Time zone helpers: IANA name validation and POSIX TZ string derivation.

The device's Time service takes both an IANA zone name ("Europe/London") and
the equivalent POSIX TZ rule ("GMT0BST,M3.5.0/1,M10.5.0"). The POSIX rule is
stored verbatim in the footer of every version 2+ TZif file, so it can be
read straight out of the system or tzdata zoneinfo database.

The module-level functions do blocking file IO; async_set_device_timezone
wraps them in the executor for use from entities.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

_LOGGER = logging.getLogger(__name__)

TZ_BLOCK = "Time"
PARAM_TZ = "TZ"
PARAM_TZ_POSIX = "TZ-POSIX"

_available: Optional[frozenset[str]] = None


def available_timezones() -> frozenset[str]:
    """Return all IANA zone names known to this Python (cached)."""
    global _available
    if _available is None:
        import zoneinfo

        _available = frozenset(zoneinfo.available_timezones())
    return _available


def is_valid_timezone(name: str) -> bool:
    """Return True if name is an IANA zone this Python can resolve."""
    return bool(name) and name in available_timezones()


def _read_tzif(name: str) -> Optional[bytes]:
    """Return the raw TZif bytes for an IANA zone, from TZPATH or the tzdata package."""
    import zoneinfo

    for root in zoneinfo.TZPATH:
        path = Path(root, *name.split("/"))
        if path.is_file():
            return path.read_bytes()

    try:  # pragma: no cover - depends on the tzdata package being installed
        from importlib import resources

        return resources.files("tzdata.zoneinfo").joinpath(*name.split("/")).read_bytes()
    except Exception as ex:  # noqa: BLE001
        _LOGGER.debug("No tzdata resource for %s: %s", name, ex)
        return None


def posix_tz_string(name: str) -> Optional[str]:
    """Return the POSIX TZ rule for an IANA zone, or None if it cannot be derived.

    TZif version 2+ files end with "\\n<posix rule>\\n"; the rule is whatever
    sits between the final two newlines.
    """
    data = _read_tzif(name)
    if not data or not data.startswith(b"TZif"):
        return None
    if data[4:5] in (b"\x00",):  # version 1 files have no footer
        return None

    stripped = data.rstrip(b"\n")
    footer = stripped.rsplit(b"\n", 1)[-1]
    try:
        rule = footer.decode("ascii").strip()
    except UnicodeDecodeError:
        return None
    return rule or None


async def async_set_device_timezone(hass: HomeAssistant, device, zone: str) -> None:
    """Validate an IANA zone and write TZ (+ TZ-POSIX when derivable) to the device.

    Shared by the "Time zone" text entity and the "Sync time zone" button.
    Raises HomeAssistantError on invalid input or device refusal.
    """
    zone = (zone or "").strip()
    if not await hass.async_add_executor_job(is_valid_timezone, zone):
        raise HomeAssistantError(
            f"'{zone}' is not a valid IANA time zone (e.g. Europe/London)"
        )

    values = {PARAM_TZ: zone}
    posix = await hass.async_add_executor_job(posix_tz_string, zone)
    if posix:
        values[PARAM_TZ_POSIX] = posix
    else:
        _LOGGER.warning(
            "Could not derive a POSIX rule for %s; sending TZ only and relying on "
            "the device to resolve it",
            zone,
        )

    _LOGGER.info("Setting device %s time zone to %s", device.host, values)
    if not await device.set_block_params(TZ_BLOCK, values):
        raise HomeAssistantError("Device rejected the time zone")
