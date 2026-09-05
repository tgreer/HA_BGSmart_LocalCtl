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
    system = params.get(SYSTEM_KEY)
    if not isinstance(system, dict) or PARAM_REBOOT not in system:
        _LOGGER.debug("Device exposes no System.Reboot param; no buttons created")
        return

    device_info = build_device_info(entry, device, params)
    _LOGGER.info("Creating reboot button")
    async_add_entities([BGSmartRebootButton(coordinator, device, device_info, entry)])


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
