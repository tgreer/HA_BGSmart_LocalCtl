"""mDNS helpers for locating BG Smart devices by node_id."""
from __future__ import annotations

import logging
from typing import Optional

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# BG Smart devices advertise ESP Local Control and publish their node_id as
# the mDNS hostname, e.g. "C3GNXiRBoiyPb5p5mGzHtZ.local.".
ZEROCONF_SERVICE_TYPE = "_esp_local_ctrl._tcp.local."
EXPECTED_CONTROL_ENDPOINT = "/esp_local_ctrl/control"
DEFAULT_RESOLVE_TIMEOUT_MS = 3000


def mdns_hostname(node_id: str) -> str:
    """Return the fully qualified mDNS hostname for a node_id."""
    return f"{node_id}.local."


async def async_resolve_host(
    hass: HomeAssistant,
    node_id: str,
    timeout_ms: int = DEFAULT_RESOLVE_TIMEOUT_MS,
) -> Optional[str]:
    """Resolve a device's current IPv4 address from its node_id via mDNS.

    Uses Home Assistant's shared zeroconf instance. Returns None if the
    device cannot be resolved (mDNS not reachable, device offline, or the
    zeroconf library is too old to expose an address resolver).
    """
    if not node_id:
        return None

    try:
        from homeassistant.components import zeroconf as ha_zeroconf
        from zeroconf import AddressResolverIPv4, IPVersion
    except ImportError as ex:  # pragma: no cover - very old HA/zeroconf
        _LOGGER.debug("mDNS address resolution unavailable: %s", ex)
        return None

    hostname = mdns_hostname(node_id)

    try:
        aiozc = await ha_zeroconf.async_get_async_instance(hass)
        resolver = AddressResolverIPv4(hostname)
        if not await resolver.async_request(aiozc.zeroconf, timeout_ms):
            _LOGGER.debug("mDNS lookup for %s timed out", hostname)
            return None

        addresses = resolver.ip_addresses_by_version(IPVersion.V4Only)
    except Exception as ex:  # noqa: BLE001
        _LOGGER.debug("mDNS lookup for %s failed: %s", hostname, ex)
        return None

    if not addresses:
        return None

    host = str(addresses[0])
    _LOGGER.debug("Resolved %s to %s", hostname, host)
    return host
