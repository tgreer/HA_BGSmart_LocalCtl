"""Support for BG Smart Local Control switches (smart sockets, LED indicator)."""
import logging
from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import DOMAIN
from .helpers import PARAM_POWER, build_device_info, is_outlet

_LOGGER = logging.getLogger(__name__)

PARAM_CHILDLOCK = "childlock"
# Despite the name this is a boolean: the status LED on/off (bg.param.ledindicator).
PARAM_LED_INDICATOR = "idcbrightness"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up BG Smart switches from a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    device = data["device"]
    coordinator = data["coordinator"]

    params = coordinator.data
    if not params:
        _LOGGER.debug("No params found in device properties; no switches created")
        return

    device_info = build_device_info(entry, device, params)
    entities: list[SwitchEntity] = []

    for outlet_key, outlet_params in params.items():
        if not is_outlet(outlet_params):
            continue
        _LOGGER.info("Creating power switch for outlet: %s", outlet_key)
        entities.append(
            BGSmartOutletSwitch(coordinator, device, outlet_key, device_info, entry)
        )
        if PARAM_CHILDLOCK in outlet_params:
            _LOGGER.info("Creating parental lock switch for outlet: %s", outlet_key)
            entities.append(
                BGSmartParentalLockSwitch(
                    coordinator, device, outlet_key, device_info, entry
                )
            )

    # The LED indicator lives on a service block (SocketName on sockets), not
    # on an outlet, so look for it anywhere in the params.
    for block_key, block in params.items():
        if isinstance(block, dict) and PARAM_LED_INDICATOR in block:
            _LOGGER.info("Creating LED indicator switch on block: %s", block_key)
            entities.append(
                BGSmartLedIndicatorSwitch(
                    coordinator, device, block_key, device_info, entry
                )
            )
            break

    if not entities:
        _LOGGER.debug("No switch-type parameters found")
        return

    _LOGGER.info("Adding %s switch entities", len(entities))
    async_add_entities(entities)


class BGSmartParamSwitch(CoordinatorEntity, SwitchEntity):
    """Base switch bound to a single boolean param on one params block."""

    _attr_has_entity_name = True
    _param_name: str
    _unique_suffix: str = ""

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        device,
        block_key: str,
        device_info: DeviceInfo,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._device = device
        self._block_key = block_key
        self._attr_device_info = device_info
        self._attr_unique_id = f"{entry.entry_id}_{block_key}{self._unique_suffix}"
        self._attr_is_on = self._read_state()

    def _block_params(self) -> dict:
        """Return the current params block this switch is bound to."""
        data = self.coordinator.data or {}
        block = data.get(self._block_key)
        return block if isinstance(block, dict) else {}

    def _read_state(self) -> bool:
        """Read the bound param from the coordinator data."""
        return bool(self._block_params().get(self._param_name, False))

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if self._block_key in (self.coordinator.data or {}):
            self._attr_is_on = self._read_state()
        self.async_write_ha_state()

    async def _async_set(self, value: bool) -> None:
        """Write the bound param and update state optimistically."""
        _LOGGER.debug("Setting %s.%s = %s", self._block_key, self._param_name, value)
        try:
            success = await self._device.set_param(
                self._block_key, self._param_name, value
            )
        except Exception as ex:  # noqa: BLE001
            _LOGGER.error(
                "Error setting %s.%s: %s",
                self._block_key,
                self._param_name,
                ex,
                exc_info=True,
            )
            return

        if not success:
            _LOGGER.error("Failed to set %s.%s", self._block_key, self._param_name)
            return

        self._attr_is_on = value
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        await self._async_set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        await self._async_set(False)


class BGSmartOutletSwitch(BGSmartParamSwitch):
    """Power switch for one socket outlet."""

    _param_name = PARAM_POWER
    _attr_device_class = SwitchDeviceClass.OUTLET

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        device,
        block_key: str,
        device_info: DeviceInfo,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the outlet power switch."""
        super().__init__(coordinator, device, block_key, device_info, entry)
        self._attr_name = block_key


class BGSmartParentalLockSwitch(BGSmartParamSwitch):
    """Parental lock switch for one socket outlet.

    The BG Smart app calls this "Parental Lock"; the device param is "childlock".
    """

    _param_name = PARAM_CHILDLOCK
    # Keep the device param name in the unique ID for stability.
    _unique_suffix = "_childlock"
    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:lock"

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        device,
        block_key: str,
        device_info: DeviceInfo,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the parental lock switch."""
        super().__init__(coordinator, device, block_key, device_info, entry)
        self._attr_name = f"{block_key} parental lock"


class BGSmartLedIndicatorSwitch(BGSmartParamSwitch):
    """Status LED on/off for the whole device."""

    _param_name = PARAM_LED_INDICATOR
    _unique_suffix = f"_{PARAM_LED_INDICATOR}"
    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:led-on"
    _attr_name = "LED indicator"
