"""Shared helpers: device naming and DeviceInfo built from the node config."""
from __future__ import annotations

from typing import Any, Optional

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN

MANUFACTURER = "BG Electrical"

PARAM_POWER = "Power"
PARAM_BRIGHTNESS = "brightness"
SOCKET_NAME_KEY = "SocketName"


PARAM_NAME = "Name"


def device_name_block(params: dict) -> Optional[str]:
    """Return the key of the params block that carries the device's Name.

    Sockets keep it on the SocketName service; dimmers keep it on the block
    that also carries Power/brightness. None if the device has no Name param.
    """
    socket_name = params.get(SOCKET_NAME_KEY)
    if isinstance(socket_name, dict) and PARAM_NAME in socket_name:
        return SOCKET_NAME_KEY

    for key, block in params.items():
        if isinstance(block, dict) and PARAM_POWER in block and PARAM_NAME in block:
            return key

    return None


def device_display_name(params: dict) -> Optional[str]:
    """Return the friendly name the user gave the device in the BG Smart app."""
    key = device_name_block(params)
    if key is None:
        return None
    name = params[key].get(PARAM_NAME)
    if isinstance(name, str) and name.strip():
        return name.strip()
    return None


def is_outlet(block: Any) -> bool:
    """Return True if a params block is a socket outlet (Power, no brightness)."""
    return (
        isinstance(block, dict)
        and PARAM_POWER in block
        and PARAM_BRIGHTNESS not in block
    )


def is_dimmer(block: Any) -> bool:
    """Return True if a params block is a dimmer (Power and brightness)."""
    return (
        isinstance(block, dict)
        and PARAM_POWER in block
        and PARAM_BRIGHTNESS in block
    )


def _default_model(params: dict) -> str:
    """Best-effort model name when the device config does not provide one."""
    if any(is_dimmer(block) for block in params.values()):
        return "Smart Dimmer"
    if sum(1 for block in params.values() if is_outlet(block)) > 1:
        return "Smart Double Socket"
    return "Smart Socket"


def build_device_info(entry: ConfigEntry, device: Any, params: dict) -> DeviceInfo:
    """Describe the physical device for the device registry.

    Identity is the config entry (stable across renames and IP changes).
    Model, firmware and platform come from the device's own "config"
    property when available, so the device page shows e.g.
    "Smart Socket · 822/HC-02 · firmware v1.0".
    """
    info: dict = getattr(device, "info", {}) or {}

    device_info = DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=device_display_name(params) or f"BG Smart ({device.host})",
        manufacturer=MANUFACTURER,
        model=info.get("name") or _default_model(params),
    )

    if info.get("model"):
        device_info["model_id"] = info["model"]
    if info.get("fw_version"):
        device_info["sw_version"] = info["fw_version"]
    if info.get("platform"):
        device_info["hw_version"] = info["platform"]
    if getattr(device, "node_id", ""):
        device_info["serial_number"] = device.node_id

    return device_info
