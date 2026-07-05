"""Device tracker platform for OVAPI live vehicle positions (opt-in).

Only forwarded when CONF_ENABLE_LIVE_TRACKING is on (see __init__.py's
_platforms_for_entry) — there is nothing for these entities to show
otherwise. Two fixed entities per config entry, mirroring sensor.py's
current_bus/next_bus split (coordinator.data[0]/[1]) rather than one entity
per live vehicle: the latter would mean entities dynamically appearing and
disappearing as buses come and go, which this integration's quality-scale
position (dynamic-devices: exempt, single device per entry) explicitly
avoids.
"""
from __future__ import annotations

import time
from typing import Any

from homeassistant.components.device_tracker.config_entry import TrackerEntity
from homeassistant.components.device_tracker.const import SourceType
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import OVAPIDataUpdateCoordinator
from .const import DOMAIN, TRACKER_CURRENT_BUS, TRACKER_NEXT_BUS
from .kv6 import KV6VehiclePosition

# Duplicated from sensor.py rather than imported, deliberately: keeps the two
# platforms fully decoupled so a future change to one can't ripple into the
# other's entities.
_TRANSPORT_ICONS = {
    "BUS": "mdi:bus",
    "TRAM": "mdi:tram",
    "METRO": "mdi:subway-variant",
    "TRAIN": "mdi:train",
    "FERRY": "mdi:ferry",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up OVAPI device trackers based on a config entry."""
    coordinator: OVAPIDataUpdateCoordinator = entry.runtime_data
    if coordinator.kv6_manager is None:
        # Belt-and-suspenders: _platforms_for_entry already prevents this
        # platform from being forwarded when tracking is disabled.
        return

    async_add_entities([
        OVAPICurrentBusTracker(coordinator, entry),
        OVAPINextBusTracker(coordinator, entry),
    ])


class OVAPIBaseBusTracker(CoordinatorEntity[OVAPIDataUpdateCoordinator], TrackerEntity):
    """Base class for OVAPI live vehicle trackers."""

    _attr_has_entity_name = True
    _attr_source_type = SourceType.GPS
    _pass_index: int

    def __init__(
        self,
        coordinator: OVAPIDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the tracker."""
        super().__init__(coordinator)
        self._entry = entry

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info.

        Overrides the property (not _attr_device_info) because
        BaseTrackerEntity's type stub pins _attr_device_info to exactly
        None — a stricter type than TrackerEntity's actual runtime support
        for device grouping via config entries.
        """
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": f"Bus Stop {self.coordinator.stop_code}",
            "manufacturer": "OVAPI",
            "model": "Bus Stop",
        }

    async def async_added_to_hass(self) -> None:
        """Subscribe to KV6 updates so this refreshes between coordinator polls."""
        await super().async_added_to_hass()
        assert self.coordinator.kv6_manager is not None
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                self.coordinator.kv6_manager.signal_name,
                self._handle_kv6_update,
            )
        )

    @callback
    def _handle_kv6_update(self) -> None:
        """Handle a new KV6 fix arriving on the background thread."""
        self.async_write_ha_state()

    def _bus(self) -> dict[str, Any] | None:
        """Return the pass this tracker follows (current or next), if any."""
        if not self.coordinator.data or len(self.coordinator.data) <= self._pass_index:
            return None
        return self.coordinator.data[self._pass_index]

    def _position(self) -> KV6VehiclePosition | None:
        """Look up the live GPS fix for this tracker's trip, if any."""
        bus = self._bus()
        if not bus:
            return None
        assert self.coordinator.kv6_manager is not None
        return self.coordinator.kv6_manager.get_position(
            bus.get("data_owner_code"),
            bus.get("line_planning_number"),
            bus.get("journey_number"),
            bus.get("operation_date"),
        )

    @property
    def latitude(self) -> float | None:
        """Return latitude, or None if this trip has no live fix yet."""
        position = self._position()
        return position.latitude if position else None

    @property
    def longitude(self) -> float | None:
        """Return longitude, or None if this trip has no live fix yet."""
        position = self._position()
        return position.longitude if position else None

    @property
    def icon(self) -> str:
        """Return the icon based on transport type."""
        bus = self._bus()
        transport_type = bus.get("transport_type", "BUS") if bus else "BUS"
        return _TRANSPORT_ICONS.get(transport_type, "mdi:bus")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        bus = self._bus()
        if not bus:
            return {}
        attributes: dict[str, Any] = {
            "line_number": bus.get("line_number"),
            "destination": bus.get("destination"),
            "stop_code": bus.get("stop_code"),
        }
        position = self._position()
        if position is not None:
            attributes["punctuality_seconds"] = position.punctuality
            attributes["vehicle_number"] = position.vehicle_number
            attributes["omloop_number"] = position.omloop_number
            attributes["age_seconds"] = round(time.time() - position.timestamp)
        return attributes


class OVAPICurrentBusTracker(OVAPIBaseBusTracker):
    """Tracker for the currently approaching vehicle."""

    _attr_translation_key = TRACKER_CURRENT_BUS
    _pass_index = 0

    def __init__(self, coordinator: OVAPIDataUpdateCoordinator, entry: ConfigEntry) -> None:
        """Initialize the tracker."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_current_bus_location"


class OVAPINextBusTracker(OVAPIBaseBusTracker):
    """Tracker for the vehicle after the current one."""

    _attr_translation_key = TRACKER_NEXT_BUS
    _attr_entity_registry_enabled_default = False
    _pass_index = 1

    def __init__(self, coordinator: OVAPIDataUpdateCoordinator, entry: ConfigEntry) -> None:
        """Initialize the tracker."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_next_bus_location"
