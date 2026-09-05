"""Support for BG Smart Local Control buttons (device reboot)."""
import logging

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import DOMAIN
from .helpers import build_device_info
from .timezone import PARAM_TZ, TZ_BLOCK, async_set_device_timezone

_LOGGER = logging.getLogger(__name__)

SYSTEM_KEY = "System"
PARAM_REBOOT = "Reboot"
# "Factory-Reset" and "Wi-Fi-Reset" also exist on the System block. They are
# deliberately not exposed: Wi-Fi reset drops the device off the network and
# it must be re-provisioned with the BG Smart app.


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up BG Smart buttons from a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    device = data["device"]
    coordinator = data["coordinator"]

    params = coordinator.data or {}
    device_info = build_device_info(entry, device, params)
    entities: list[ButtonEntity] = []

    system = params.get(SYSTEM_KEY)
    if isinstance(system, dict) and PARAM_REBOOT in system:
        _LOGGER.info("Creating reboot button")
        entities.append(BGSmartRebootButton(coordinator, device, device_info, entry))

    time_block = params.get(TZ_BLOCK)
    if isinstance(time_block, dict) and PARAM_TZ in time_block:
        _LOGGER.info("Creating sync time zone button")
        entities.append(
            BGSmartSyncTimeZoneButton(coordinator, device, device_info, entry)
        )

    if not entities:
        _LOGGER.debug("No button-type parameters found")
        return

    async_add_entities(entities)


class BGSmartRebootButton(CoordinatorEntity, ButtonEntity):
    """Reboot the device (System.Reboot = true)."""

    _attr_has_entity_name = True
    _attr_name = "Restart"
    _attr_device_class = ButtonDeviceClass.RESTART
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        device,
        device_info: DeviceInfo,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self._device = device
        self._attr_device_info = device_info
        self._attr_unique_id = f"{entry.entry_id}_{SYSTEM_KEY}_{PARAM_REBOOT}"

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success

    async def async_press(self) -> None:
        """Ask the device to reboot.

        The device drops off the network for a few seconds; the next poll may
        fail and the entities briefly show unavailable, then recover.
        """
        _LOGGER.info("Rebooting BG Smart device %s", self._device.host)
        try:
            success = await self._device.set_param(SYSTEM_KEY, PARAM_REBOOT, True)
        except Exception as ex:  # noqa: BLE001
            raise HomeAssistantError(f"Failed to reboot device: {ex}") from ex
        if not success:
            raise HomeAssistantError("Device rejected the reboot request")


class BGSmartSyncTimeZoneButton(CoordinatorEntity, ButtonEntity):
    """Set the device's time zone to Home Assistant's configured time zone."""

    _attr_has_entity_name = True
    _attr_name = "Sync time zone"
    _attr_icon = "mdi:clock-check-outline"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        device,
        device_info: DeviceInfo,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self._device = device
        self._attr_device_info = device_info
        self._attr_unique_id = f"{entry.entry_id}_{TZ_BLOCK}_sync"

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success

    async def async_press(self) -> None:
        """Push Home Assistant's time zone to the device."""
        await async_set_device_timezone(self.hass, self._device, self.hass.config.time_zone)
        await self.coordinator.async_request_refresh()
