"""Sensor platform for the ChannelBin integration.

All sensors are CoordinatorEntity subclasses reading fields off
ChannelBinDataUpdateCoordinator.data (the decoded GET /api/ha/v1/status payload -
app/routes/ha.py in the ChannelBin repo). No sensor polls on its own; the coordinator
(coordinator.py) is the only thing that talks to the network.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfInformation
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import ChannelBinConfigEntry
from .account_devices import (
    ACCOUNT_MODELS,
    ACCOUNT_STATUSES,
    account_device_key,
    account_list,
    accounts_by_id,
    status_state,
    truncated_state,
    utc_from_wire,
)
from .const import DOMAIN
from .coordinator import ChannelBinDataUpdateCoordinator


@dataclass(frozen=True, kw_only=True)
class ChannelBinSensorEntityDescription(SensorEntityDescription):
    """Describes a ChannelBin sensor - value_fn/attrs_fn pull from coordinator.data."""

    value_fn: Callable[[dict[str, Any]], Any]
    attrs_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None


def _next_recording_value(data: dict[str, Any]) -> datetime | None:
    nxt = data['recording'].get('next_recording')
    return utc_from_wire(nxt['start_time']) if nxt else None


# The attrs functions always return the same keys, null when there is nothing to report:
# Home Assistant draws an entity's Attributes panel only when at least one attribute exists,
# so an empty dict hides it exactly when someone opens the entity to see why it reads Unknown.
def _next_recording_attrs(data: dict[str, Any]) -> dict[str, Any]:
    nxt = data['recording'].get('next_recording') or {}
    return {
        'name': nxt.get('name'),
        'channel': nxt.get('channel'),
        'recording_id': nxt.get('id'),
    }


def _capturing(data: dict[str, Any]) -> list[dict[str, Any]]:
    return data['recording'].get('capturing') or []


def _current_recording_value(data: dict[str, Any]) -> str | None:
    capturing = _capturing(data)
    return truncated_state(capturing[0].get('name')) if capturing else None


def _capturing_entry(rec: dict[str, Any]) -> dict[str, Any]:
    # account/account_id arrive from ChannelBin 0.22.0 on and read null before it.
    return {
        'recording_id': rec.get('id'),
        'channel': rec.get('channel'),
        'account': rec.get('account'),
        'account_id': rec.get('account_id'),
        'started_at': utc_from_wire(rec.get('started_at')),
        'stop_time': utc_from_wire(rec.get('stop_time')),
    }


# Two recordings at once must never read as one: the first is the state, the rest are listed
# in also_recording, each carrying its own name since the state names only the first.
def _current_recording_attrs(data: dict[str, Any]) -> dict[str, Any]:
    first, *rest = _capturing(data) or [{}]
    return {
        **_capturing_entry(first),
        'also_recording': [{'name': rec.get('name'), **_capturing_entry(rec)} for rec in rest],
    }


def _unread_alerts_attrs(data: dict[str, Any]) -> dict[str, Any]:
    latest = data['alerts'].get('latest') or {}
    return {
        'severity': latest.get('severity'),
        'title': latest.get('title'),
        'created_at': latest.get('created_at'),
    }


def _accounts_ok_attrs(data: dict[str, Any]) -> dict[str, Any]:
    accounts = data['accounts']
    return {'error_count': accounts['error_count'], 'total': accounts['total']}


def _accounts_error_attrs(data: dict[str, Any]) -> dict[str, Any]:
    accounts = data['accounts']
    return {'ok_count': accounts['ok_count'], 'total': accounts['total']}


SENSOR_DESCRIPTIONS: tuple[ChannelBinSensorEntityDescription, ...] = (
    ChannelBinSensorEntityDescription(
        key='capturing',
        translation_key='capturing',
        icon='mdi:record-rec',
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data['recording']['capturing_count'],
    ),
    ChannelBinSensorEntityDescription(
        key='converting',
        translation_key='converting',
        icon='mdi:cog-sync',
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data['recording']['converting_count'],
    ),
    ChannelBinSensorEntityDescription(
        key='next_recording',
        translation_key='next_recording',
        icon='mdi:calendar-clock',
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_next_recording_value,
        attrs_fn=_next_recording_attrs,
    ),
    # No device_class, so nothing capturing reads None: that is a fact the server reported,
    # not a value it is missing. binary_sensor.channelbin_recording stays the one to test on.
    ChannelBinSensorEntityDescription(
        key='current_recording',
        translation_key='current_recording',
        icon='mdi:record-rec',
        value_fn=_current_recording_value,
        attrs_fn=_current_recording_attrs,
    ),
    ChannelBinSensorEntityDescription(
        key='disk_free',
        translation_key='disk_free',
        icon='mdi:harddisk',
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_unit_of_measurement=UnitOfInformation.GIGABYTES,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data['disk']['free_bytes'],
    ),
    ChannelBinSensorEntityDescription(
        key='disk_used_percent',
        translation_key='disk_used_percent',
        icon='mdi:harddisk',
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data['disk']['used_pct'],
    ),
    ChannelBinSensorEntityDescription(
        key='unread_alerts',
        translation_key='unread_alerts',
        icon='mdi:alert-circle',
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data['alerts']['unread_count'],
        attrs_fn=_unread_alerts_attrs,
    ),
    ChannelBinSensorEntityDescription(
        key='accounts_ok',
        translation_key='accounts_ok',
        icon='mdi:account-check',
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data['accounts']['ok_count'],
        attrs_fn=_accounts_ok_attrs,
    ),
    # ERROR only, never total - ok_count: SYNCING and UNSYNCED are not faults, and counting
    # them would move this every time a sync runs and alarm on a never-synced account.
    ChannelBinSensorEntityDescription(
        key='accounts_error',
        translation_key='accounts_error',
        icon='mdi:account-alert',
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data['accounts']['error_count'],
        attrs_fn=_accounts_error_attrs,
    ),
)



@dataclass(frozen=True, kw_only=True)
class ChannelBinAccountSensorEntityDescription(SensorEntityDescription):
    """Describes one sensor on a provider account's device - value_fn/attrs_fn read that
    account's entry in the payload's accounts list; exists_fn says whether the account gets
    this sensor at all."""

    value_fn: Callable[[dict[str, Any]], Any]
    attrs_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None
    exists_fn: Callable[[dict[str, Any]], bool] = lambda account: True


ACCOUNT_SENSOR_DESCRIPTIONS: tuple[ChannelBinAccountSensorEntityDescription, ...] = (
    ChannelBinAccountSensorEntityDescription(
        key='status',
        translation_key='account_status',
        icon='mdi:account-check',
        device_class=SensorDeviceClass.ENUM,
        options=list(ACCOUNT_STATUSES),
        value_fn=lambda account: status_state(account.get('status')),
    ),
    ChannelBinAccountSensorEntityDescription(
        key='last_sync',
        translation_key='account_last_sync',
        icon='mdi:sync',
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda account: utc_from_wire(account.get('last_sync_at')),
    ),
    ChannelBinAccountSensorEntityDescription(
        key='next_sync',
        translation_key='account_next_sync',
        icon='mdi:calendar-sync',
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda account: utc_from_wire(account.get('next_sync_at')),
    ),
    ChannelBinAccountSensorEntityDescription(
        key='last_error',
        translation_key='account_last_error',
        icon='mdi:alert-circle-outline',
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda account: truncated_state(account.get('last_error')),
    ),
    ChannelBinAccountSensorEntityDescription(
        key='channels',
        translation_key='account_channels',
        icon='mdi:television-classic',
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda account: account.get('channel_count'),
    ),
    ChannelBinAccountSensorEntityDescription(
        key='hidden_channels',
        translation_key='account_hidden_channels',
        icon='mdi:eye-off',
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda account: account.get('hidden_channel_count'),
    ),
    ChannelBinAccountSensorEntityDescription(
        key='connections',
        translation_key='account_connections',
        icon='mdi:lan-connect',
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda account: account.get('connections_in_use'),
        attrs_fn=lambda account: {'max_connections': account.get('max_connections')},
    ),
    # Only an Xtream provider reports an expiry; on an M3U account it could only ever read
    # Unknown.
    ChannelBinAccountSensorEntityDescription(
        key='provider_expiry',
        translation_key='account_provider_expiry',
        icon='mdi:calendar-alert',
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda account: utc_from_wire(account.get('provider_exp_date')),
        exists_fn=lambda account: account.get('type') == 'xtream',
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ChannelBinConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        ChannelBinSensor(coordinator, entry, description)
        for description in SENSOR_DESCRIPTIONS
    )

    # Account devices come and go with the payload. Adding is here; removing a deleted
    # account's device, which takes its entities with it, is in __init__.py.
    known: set[int] = set()

    @callback
    def _add_new_accounts() -> None:
        if account_list(coordinator.data) is None:
            return
        accounts = accounts_by_id(coordinator.data)
        known.intersection_update(accounts)
        new = [account_id for account_id in accounts if account_id not in known]
        if not new:
            return
        known.update(new)
        async_add_entities(
            ChannelBinAccountSensor(coordinator, entry, account_id, description)
            for account_id in new
            for description in ACCOUNT_SENSOR_DESCRIPTIONS
            if description.exists_fn(accounts[account_id])
        )

    _add_new_accounts()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_accounts))


class ChannelBinSensor(CoordinatorEntity[ChannelBinDataUpdateCoordinator], SensorEntity):
    """A single ChannelBin status field, read off the shared coordinator."""

    entity_description: ChannelBinSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ChannelBinDataUpdateCoordinator,
        entry: ChannelBinConfigEntry,
        description: ChannelBinSensorEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f'{entry.entry_id}_{description.key}'
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name='ChannelBin',
            manufacturer='ChannelBin',
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(self.coordinator.data)


class ChannelBinAccountSensor(CoordinatorEntity[ChannelBinDataUpdateCoordinator], SensorEntity):
    """One field of one provider account, on that account's own device."""

    entity_description: ChannelBinAccountSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ChannelBinDataUpdateCoordinator,
        entry: ChannelBinConfigEntry,
        account_id: int,
        description: ChannelBinAccountSensorEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._account_id = account_id
        device_key = account_device_key(entry.entry_id, account_id)
        self._attr_unique_id = f'{device_key}_{description.key}'
        account = accounts_by_id(coordinator.data)[account_id]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_key)},
            name=account.get('name'),
            manufacturer='ChannelBin',
            model=ACCOUNT_MODELS.get(account.get('type'), 'Provider account'),
            entry_type=DeviceEntryType.SERVICE,
            via_device=(DOMAIN, entry.entry_id),
        )

    @property
    def _account(self) -> dict[str, Any] | None:
        return accounts_by_id(self.coordinator.data).get(self._account_id)

    @property
    def available(self) -> bool:
        return super().available and self._account is not None

    @property
    def native_value(self) -> Any:
        account = self._account
        return self.entity_description.value_fn(account) if account else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        account = self._account
        if self.entity_description.attrs_fn is None or account is None:
            return None
        return self.entity_description.attrs_fn(account)
