"""The BG Smart Local Control integration."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN
from .discovery import async_resolve_host

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.BUTTON, Platform.LIGHT, Platform.SWITCH, Platform.TEXT]
SCAN_INTERVAL = timedelta(seconds=30)

CONF_NODE_ID = "node_id"
DEFAULT_PORT = 8080


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the BG Smart Local Control component."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up BG Smart Local Control from a config entry.

    The device identity is its node_id (from mDNS). The stored host is only a
    cache of the last known address: if it stops answering and we know the
    node_id, the current address is looked up over mDNS and the entry updated.
    Manually added devices without a node_id fall back to the fixed host.
    """
    # Lazy import to avoid loading protobuf during HA startup
    from .esp_local_control import ESPLocalControlError, ESPLocalDevice

    host: str | None = entry.data.get(CONF_HOST)
    port: int = entry.data.get(CONF_PORT, DEFAULT_PORT)
    node_id: str = entry.data.get(CONF_NODE_ID, "")
    # Entries created by older versions also carry "pop" and "security_type";
    # neither is used on the wire, so they are simply ignored.

    if not host:
        # Discovered entry with no cached address yet: resolve before connecting.
        host = await async_resolve_host(hass, node_id)
        if not host:
            raise ConfigEntryNotReady(
                f"Could not resolve BG Smart device {node_id or entry.title} via mDNS"
            )
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_HOST: host}
        )

    device = ESPLocalDevice(host, port, node_id)

    async def _async_relocate() -> bool:
        """Try to find the device at a new address. Returns True if it moved."""
        # device.node_id may have been learned from the device itself, so use
        # it rather than the (possibly empty) value stored in the entry.
        if not device.node_id:
            return False
        new_host = await async_resolve_host(hass, device.node_id)
        if not new_host or new_host == device.host:
            return False
        device.update_host(new_host)
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_HOST: new_host}
        )
        return True

    async def _async_update_data() -> dict[str, Any]:
        """Poll the device, re-resolving its address over mDNS if it moved."""
        try:
            return await device.get_params()
        except ESPLocalControlError as err:
            if not await _async_relocate():
                raise UpdateFailed(str(err)) from err
            try:
                return await device.get_params()
            except ESPLocalControlError as err2:
                raise UpdateFailed(str(err2)) from err2

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"{DOMAIN}_{entry.entry_id}",
        update_method=_async_update_data,
        update_interval=SCAN_INTERVAL,
    )

    # Raises ConfigEntryNotReady (and schedules a retry) if the device is unreachable.
    await coordinator.async_config_entry_first_refresh()

    if not node_id and device.node_id:
        _async_adopt_node_id(hass, entry, device.node_id)

    hass.data[DOMAIN][entry.entry_id] = {
        "device": device,
        "coordinator": coordinator,
        "host": device.host,
        "port": port,
    }

    # The config flow updates the stored host when a device is rediscovered
    # (or re-added manually) at a new address, always with
    # reload_on_update=False. This listener applies the change to the running
    # client in place. Do not add reloading flow methods alongside it: HA
    # 2026.6 deprecates that combination (error from 2026.12) because it can
    # double-reload or race.
    entry.async_on_unload(entry.add_update_listener(_async_entry_updated))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


def _async_adopt_node_id(hass: HomeAssistant, entry: ConfigEntry, node_id: str) -> None:
    """Upgrade a host-keyed entry to the node_id the device reported.

    Entries added manually before the device started telling us its node_id
    are keyed on the IP address. Re-keying them enables mDNS IP tracking and
    lets discovery recognise the device instead of offering it again.
    """
    for other in hass.config_entries.async_entries(DOMAIN):
        if other.entry_id != entry.entry_id and other.unique_id == node_id:
            _LOGGER.warning(
                "Not adopting node_id %s for entry %s: already used by entry %s",
                node_id, entry.title, other.title,
            )
            return

    _LOGGER.info("Entry %s: adopting device-reported node_id %s", entry.title, node_id)
    updates: dict[str, Any] = {"data": {**entry.data, CONF_NODE_ID: node_id}}
    if entry.unique_id != node_id:
        updates["unique_id"] = node_id
    # Called before the update listener is registered, and the host is
    # unchanged anyway. No reload is involved.
    hass.config_entries.async_update_entry(entry, **updates)


async def _async_entry_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle config entry data changes (e.g. host updated by discovery)."""
    data = hass.data[DOMAIN].get(entry.entry_id)
    if data is None:
        return
    new_host = entry.data.get(CONF_HOST)
    if new_host and new_host != data["device"].host:
        data["device"].update_host(new_host)
        data["host"] = new_host
        await data["coordinator"].async_request_refresh()


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
