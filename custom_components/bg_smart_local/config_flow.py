"""Config flow for BG Smart Local Control integration."""
from __future__ import annotations

import logging
from typing import Any, Optional

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.helpers import network

try:  # Home Assistant 2024.11+
    from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
except ImportError:  # pragma: no cover - older Home Assistant
    from homeassistant.components.zeroconf import ZeroconfServiceInfo

from .const import DOMAIN
from .discovery import EXPECTED_CONTROL_ENDPOINT

_LOGGER = logging.getLogger(__name__)

CONF_NODE_ID = "node_id"
DEFAULT_PORT = 8080


class CannotConnect(Exception):
    """Raised when the device cannot be reached or returns no params."""


def _device_display_name(params: dict) -> Optional[str]:
    """Return a friendly name from the device params, if one is present.

    Sockets expose it as SocketName.Name; dimmers expose it as <key>.Name on
    the block that also carries Power/brightness.
    """
    socket_name = params.get("SocketName")
    if isinstance(socket_name, dict):
        name = socket_name.get("Name")
        if isinstance(name, str) and name.strip():
            return name.strip()

    for block in params.values():
        if isinstance(block, dict) and "Power" in block:
            name = block.get("Name")
            if isinstance(name, str) and name.strip():
                return name.strip()

    return None


def _looks_like_bg_device(params: dict) -> bool:
    """Return True if the params contain at least one controllable block."""
    return any(
        isinstance(block, dict) and "Power" in block for block in params.values()
    )


async def _fetch_params(host: str, port: int, node_id: str) -> dict:
    """Connect to the device and return its params, or raise CannotConnect."""
    # Lazy import to avoid loading protobuf during HA startup.
    from .esp_local_control import ESPLocalControlError, ESPLocalDevice

    device = ESPLocalDevice(host, port, node_id)
    try:
        params = await device.get_params()
    except ESPLocalControlError as err:
        raise CannotConnect(str(err)) from err
    if not params:
        raise CannotConnect("Device returned empty params")
    return params


class BGSmartLocalConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for BG Smart Local Control."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""
        super().__init__()
        self._host: Optional[str] = None
        self._port: int = DEFAULT_PORT
        self._node_id: str = ""
        self._name: Optional[str] = None

    # ------------------------------------------------------------------
    # Zeroconf discovery
    # ------------------------------------------------------------------

    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> config_entries.ConfigFlowResult:
        """Handle a device discovered via mDNS (_esp_local_ctrl._tcp)."""
        properties = discovery_info.properties or {}
        node_id = (properties.get("node_id") or "").strip()
        control_endpoint = properties.get("control_endpoint", "")

        # Any ESP-IDF project can use ESP Local Control; only accept records
        # that look like the BG Smart firmware.
        if not node_id or control_endpoint != EXPECTED_CONTROL_ENDPOINT:
            _LOGGER.debug(
                "Ignoring ESP Local Control service without BG Smart markers: %s",
                discovery_info.name,
            )
            return self.async_abort(reason="not_bg_device")

        host = discovery_info.host
        port = discovery_info.port or DEFAULT_PORT

        _LOGGER.debug(
            "Discovered ESP Local Control device node_id=%s at %s:%s",
            node_id, host, port,
        )

        # Devices are keyed on node_id so a DHCP change just updates the cached
        # host. The integration's update listener swaps the address in place,
        # so no reload is needed.
        await self.async_set_unique_id(node_id)
        self._abort_if_unique_id_configured(
            updates={CONF_HOST: host, CONF_PORT: port},
            reload_on_update=False,
        )

        # Entries created by older versions are keyed on the IP address. If
        # one matches this host, upgrade it to the node_id and stop here.
        for entry in self._async_current_entries(include_ignore=False):
            if entry.data.get(CONF_HOST) == host and entry.unique_id != node_id:
                _LOGGER.info(
                    "Migrating entry %s from host-based to node_id-based unique ID",
                    entry.title,
                )
                self.hass.config_entries.async_update_entry(
                    entry,
                    unique_id=node_id,
                    data={**entry.data, CONF_NODE_ID: node_id, CONF_PORT: port},
                )
                return self.async_abort(reason="already_configured")

        try:
            params = await _fetch_params(host, port, node_id)
        except Exception as ex:  # noqa: BLE001
            _LOGGER.debug("Discovered device at %s did not respond: %s", host, ex)
            return self.async_abort(reason="cannot_connect")

        if not _looks_like_bg_device(params):
            return self.async_abort(reason="not_bg_device")

        self._host = host
        self._port = port
        self._node_id = node_id
        self._name = _device_display_name(params) or f"BG Smart ({host})"

        self.context["title_placeholders"] = {"name": self._name}
        return await self.async_step_zeroconf_confirm()

    async def async_step_zeroconf_confirm(
        self, user_input: Optional[dict[str, Any]] = None
    ) -> config_entries.ConfigFlowResult:
        """Ask the user to confirm adding the discovered device."""
        if user_input is not None:
            return self.async_create_entry(
                title=self._name,
                data={
                    CONF_HOST: self._host,
                    CONF_PORT: self._port,
                    CONF_NODE_ID: self._node_id,
                },
            )

        return self.async_show_form(
            step_id="zeroconf_confirm",
            description_placeholders={
                "name": self._name,
                "host": self._host,
            },
        )

    # ------------------------------------------------------------------
    # Manual setup
    # ------------------------------------------------------------------

    async def async_step_user(
        self, user_input: Optional[dict[str, Any]] = None
    ) -> config_entries.ConfigFlowResult:
        """Handle manual setup by IP address."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            port = user_input[CONF_PORT]
            node_id = (user_input.get(CONF_NODE_ID) or "").strip()

            params: Optional[dict] = None
            try:
                params = await _fetch_params(host, port, node_id)
            except Exception as ex:  # noqa: BLE001
                _LOGGER.error("Failed to connect to device at %s:%s: %s", host, port, ex)
                errors["base"] = "cannot_connect"

            if params is not None:
                if not _looks_like_bg_device(params):
                    errors["base"] = "not_bg_device"
                else:
                    # Prefer node_id when supplied; fall back to host so manual
                    # entries still get a stable identity.
                    await self.async_set_unique_id(node_id or host)
                    self._abort_if_unique_id_configured()

                    title = _device_display_name(params) or f"BG Smart ({host})"
                    return self.async_create_entry(
                        title=title,
                        data={
                            CONF_HOST: host,
                            CONF_PORT: port,
                            CONF_NODE_ID: node_id,
                        },
                    )

        ha_ip = await self._get_ha_local_ip()
        suggested_ip = self._suggest_device_ip(ha_ip)

        data_schema = vol.Schema({
            vol.Required(CONF_HOST, default=suggested_ip): str,
            vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
            vol.Optional(CONF_NODE_ID, default=""): str,
        })

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _get_ha_local_ip(self) -> str:
        """Get Home Assistant's local IP address."""
        try:
            adapters = await network.async_get_adapters(self.hass)
            for adapter in adapters:
                if adapter.get("default") and adapter.get("ipv4"):
                    for ipv4 in adapter["ipv4"]:
                        if ipv4.get("address"):
                            return ipv4["address"]
        except Exception as ex:  # noqa: BLE001
            _LOGGER.debug("Could not determine HA IP: %s", ex)

        return "192.168.1.1"

    @staticmethod
    def _suggest_device_ip(ha_ip: str) -> str:
        """Suggest a device IP by replacing the last octet of HA's IP with xxx."""
        parts = ha_ip.split(".")
        if len(parts) == 4:
            return f"{parts[0]}.{parts[1]}.{parts[2]}.xxx"
        return "192.168.1.xxx"
