"""Support for BG Smart Local Control text entities (device name, time zone)."""
import logging

from homeassistant.components.text import TextEntity, TextMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import DOMAIN
from .helpers import PARAM_NAME, build_device_info, device_name_block
from .timezone import PARAM_TZ, TZ_BLOCK, async_set_device_timezone

_LOGGER = logging.getLogger(__name__)

# The device config declares no bound for Name; the BG app keeps names short.
NAME_MAX_LENGTH = 32


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up BG Smart text entities from a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    device = data["device"]
    coordinator = data["coordinator"]

    params = coordinator.data or {}
    device_info = build_device_info(entry, device, params)
    entities: list[TextEntity] = []

    name_block = device_name_block(params)
    if name_block is not None:
        _LOGGER.info("Creating device name text on block: %s", name_block)
        entities.append(
            BGSmartDeviceNameText(coordinator, device, name_block, device_info, entry)
        )

    time_block = params.get(TZ_BLOCK)
    if isinstance(time_block, dict) and PARAM_TZ in time_block:
        _LOGGER.info("Creating time zone text")
        entities.append(
            BGSmartTimeZoneText(coordinator, device, TZ_BLOCK, device_info, entry)
        )

    if not entities:
        _LOGGER.debug("No text-type parameters found")
        return

    async_add_entities(entities)


class BGSmartParamText(CoordinatorEntity, TextEntity):
    """Base text entity bound to one string param on one params block."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = TextMode.TEXT
    _param_name: str

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        device,
        block_key: str,
        device_info: DeviceInfo,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the text entity."""
        super().__init__(coordinator)
        self._device = device
        self._entry = entry
        self._block_key = block_key
        self._attr_device_info = device_info
        self._attr_unique_id = f"{entry.entry_id}_{block_key}_{self._param_name}"
        self._attr_native_value = self._read_value()

    def _block_params(self) -> dict:
        """Return the current params block this entity is bound to."""
        data = self.coordinator.data or {}
        block = data.get(self._block_key)
        return block if isinstance(block, dict) else {}

    def _read_value(self) -> str:
        """Read the bound param from the coordinator data."""
        value = self._block_params().get(self._param_name)
        return value if isinstance(value, str) else ""

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if self._block_key in (self.coordinator.data or {}):
            self._attr_native_value = self._read_value()
        self.async_write_ha_state()


class BGSmartDeviceNameText(BGSmartParamText):
    """The device's name as shown in the BG Smart app.

    Writing it renames the device on the hardware, and Home Assistant's
    device and config entry follow so everything stays in step.
    """

    _param_name = PARAM_NAME
    _attr_name = "Name"
    _attr_icon = "mdi:rename-box"
    _attr_native_min = 1
    _attr_native_max = NAME_MAX_LENGTH

    async def async_set_value(self, value: str) -> None:
        """Rename the device."""
        new_name = value.strip()
        if not new_name:
            raise HomeAssistantError("Device name cannot be empty")

        success = await self._device.set_param(self._block_key, self._param_name, new_name)
        if not success:
            raise HomeAssistantError("Device rejected the new name")

        self._attr_native_value = new_name
        self.async_write_ha_state()

        # Keep HA's view of the device in step. name_by_user (a rename done in
        # HA) is left alone; only the device-provided name is updated.
        registry = dr.async_get(self.hass)
        ha_device = registry.async_get_device(identifiers={(DOMAIN, self._entry.entry_id)})
        if ha_device is not None and ha_device.name != new_name:
            registry.async_update_device(ha_device.id, name=new_name)
        if self._entry.title != new_name:
            self.hass.config_entries.async_update_entry(self._entry, title=new_name)

        await self.coordinator.async_request_refresh()


class BGSmartTimeZoneText(BGSmartParamText):
    """The device's IANA time zone (e.g. Europe/London).

    The device also wants the matching POSIX rule (TZ-POSIX), which is
    derived from the zoneinfo database and written in the same request.
    """

    _param_name = PARAM_TZ
    _attr_name = "Time zone"
    _attr_icon = "mdi:map-clock"
    _attr_native_min = 1
    _attr_native_max = 64

    async def async_set_value(self, value: str) -> None:
        """Set the device time zone from an IANA zone name."""
        await async_set_device_timezone(self.hass, self._device, value)
        self._attr_native_value = value.strip()
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()
