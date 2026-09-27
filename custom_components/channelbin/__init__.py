"""The ChannelBin integration.

Sets up the DataUpdateCoordinator that polls GET /api/ha/v1/status and forwards setup to
the sensor/binary_sensor platforms in PLATFORMS. Also keeps the per-account devices in step
with the server: a deleted account's device is removed, taking its entities with it, and a
renamed account's device is renamed. Adding an account's device is the sensor platform's job.
"""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr

from .account_devices import account_id_of_device, account_list, accounts_by_id, device_is_removable
from .const import DOMAIN
from .coordinator import ChannelBinDataUpdateCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]

type ChannelBinConfigEntry = ConfigEntry[ChannelBinDataUpdateCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: ChannelBinConfigEntry) -> bool:
    coordinator = ChannelBinDataUpdateCoordinator(hass, entry.data)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    @callback
    def _sync_account_devices() -> None:
        _update_account_devices(hass, entry, coordinator)

    # Once now as well, for an account deleted while Home Assistant was not running.
    _sync_account_devices()
    entry.async_on_unload(coordinator.async_add_listener(_sync_account_devices))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ChannelBinConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: ChannelBinConfigEntry, device_entry: dr.DeviceEntry
) -> bool:
    # An entry that failed to load has no coordinator, and nothing to bring a device back.
    coordinator = getattr(entry, "runtime_data", None)
    return device_is_removable(DOMAIN, entry.entry_id, device_entry.identifiers,
                               coordinator.data if coordinator else None)


@callback
def _update_account_devices(
    hass: HomeAssistant, entry: ChannelBinConfigEntry, coordinator: ChannelBinDataUpdateCoordinator
) -> None:
    # A failed poll or a server that sends no list says nothing about which accounts exist,
    # so neither may remove a device.
    if not coordinator.last_update_success or account_list(coordinator.data) is None:
        return
    accounts = accounts_by_id(coordinator.data)
    registry = dr.async_get(hass)
    for device in dr.async_entries_for_config_entry(registry, entry.entry_id):
        account_id = account_id_of_device(DOMAIN, entry.entry_id, device.identifiers)
        if account_id is None:
            continue
        account = accounts.get(account_id)
        if account is None:
            registry.async_update_device(device.id, remove_config_entry_id=entry.entry_id)
        elif account.get("name") and device.name != account["name"]:
            registry.async_update_device(device.id, name=account["name"])
