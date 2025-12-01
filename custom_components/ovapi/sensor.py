"""Sensor platform for OVAPI integration."""
from __future__ import annotations

from datetime import datetime
import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import OVAPIDataUpdateCoordinator
from .const import (
    CONF_WALKING_TIME,
    DEFAULT_WALKING_TIME,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up OVAPI sensors based on a config entry."""
    coordinator: OVAPIDataUpdateCoordinator = entry.runtime_data
    walking_time: int = entry.data.get(CONF_WALKING_TIME, DEFAULT_WALKING_TIME)

    sensors: list[SensorEntity] = [
        OVAPICurrentBusSensor(coordinator, entry),
        OVAPINextBusSensor(coordinator, entry),
        OVAPICurrentDelayTimeSensor(coordinator, entry),
        OVAPINextDelayTimeSensor(coordinator, entry),
        OVAPICurrentDepartureTimeSensor(coordinator, entry),
        OVAPINextDepartureTimeSensor(coordinator, entry),
    ]
    
    # Only add walking planner sensor if walking time is configured (> 0)
    if walking_time > 0:
        sensors.append(OVAPIWalkingPlannerSensor(coordinator, entry, walking_time))

    async_add_entities(sensors)


class OVAPIBaseSensor(CoordinatorEntity[OVAPIDataUpdateCoordinator], SensorEntity):
    """Base class for OVAPI sensors."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: OVAPIDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": f"Bus Stop {coordinator.stop_code}",
            "manufacturer": "OVAPI",
            "model": "Bus Stop",
        }


class OVAPICurrentBusSensor(OVAPIBaseSensor):
    """Sensor for current/next upcoming bus."""

    _attr_icon = "mdi:bus"
    _attr_translation_key = "current_bus"

    def __init__(
        self,
        coordinator: OVAPIDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_current_bus"

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        if not self.coordinator.data or len(self.coordinator.data) == 0:
            return None
        
        bus = self.coordinator.data[0]
        line = bus.get("line_number", "Unknown")
        destination = bus.get("destination", "Unknown")
        _LOGGER.debug("Current bus sensor: %s → %s", line, destination)
        return f"{line} → {destination}"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        if not self.coordinator.data or len(self.coordinator.data) == 0:
            return {}
        
        bus = self.coordinator.data[0]
        minutes_until = self.coordinator.client.get_time_until_departure(
            bus.get("expected_arrival")
        )
        
        return {
            "line_number": bus.get("line_number"),
            "destination": bus.get("destination"),
            "expected_arrival": bus.get("expected_arrival"),
            "target_arrival": bus.get("target_arrival"),
            "delay_minutes": bus.get("delay"),
            "transport_type": bus.get("transport_type"),
            "minutes_until_departure": minutes_until,
        }


class OVAPINextBusSensor(OVAPIBaseSensor):
    """Sensor for the bus after the current one."""

    _attr_icon = "mdi:bus-clock"
    _attr_translation_key = "next_bus"
    _attr_entity_registry_enabled_default = False

    def __init__(
        self,
        coordinator: OVAPIDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_next_bus"

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        if not self.coordinator.data or len(self.coordinator.data) < 2:
            return None
        
        bus = self.coordinator.data[1]
        line = bus.get("line_number", "Unknown")
        destination = bus.get("destination", "Unknown")
        return f"{line} → {destination}"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        if not self.coordinator.data or len(self.coordinator.data) < 2:
            return {}
        
        bus = self.coordinator.data[1]
        minutes_until = self.coordinator.client.get_time_until_departure(
            bus.get("expected_arrival")
        )
        
        return {
            "line_number": bus.get("line_number"),
            "destination": bus.get("destination"),
            "expected_arrival": bus.get("expected_arrival"),
            "target_arrival": bus.get("target_arrival"),
            "delay_minutes": bus.get("delay"),
            "transport_type": bus.get("transport_type"),
            "minutes_until_departure": minutes_until,
        }


class OVAPICurrentDelayTimeSensor(OVAPIBaseSensor):
    """Sensor for current bus delay."""

    _attr_icon = "mdi:clock-alert"
    _attr_translation_key = "current_delay"
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: OVAPIDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_current_delay"

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        if not self.coordinator.data or len(self.coordinator.data) == 0:
            return None
        
        return self.coordinator.data[0].get("delay", 0)


class OVAPINextDelayTimeSensor(OVAPIBaseSensor):
    """Sensor for next bus delay."""

    _attr_icon = "mdi:clock-alert"
    _attr_translation_key = "next_delay"
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(
        self,
        coordinator: OVAPIDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_next_delay"

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        if not self.coordinator.data or len(self.coordinator.data) < 2:
            return None
        
        return self.coordinator.data[1].get("delay", 0)


class OVAPICurrentDepartureTimeSensor(OVAPIBaseSensor):
    """Sensor for minutes until current bus departure."""

    _attr_icon = "mdi:clock-outline"
    _attr_translation_key = "current_departure"
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.DURATION

    def __init__(
        self,
        coordinator: OVAPIDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_current_departure_time"

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        if not self.coordinator.data or len(self.coordinator.data) == 0:
            return None
        
        bus = self.coordinator.data[0]
        return self.coordinator.client.get_time_until_departure(
            bus.get("expected_arrival")
        )


class OVAPINextDepartureTimeSensor(OVAPIBaseSensor):
    """Sensor for minutes until next bus departure."""

    _attr_icon = "mdi:clock-outline"
    _attr_translation_key = "next_departure"
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_entity_registry_enabled_default = False

    def __init__(
        self,
        coordinator: OVAPIDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_next_departure_time"

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        if not self.coordinator.data or len(self.coordinator.data) < 2:
            return None
        
        bus = self.coordinator.data[1]
        return self.coordinator.client.get_time_until_departure(
            bus.get("expected_arrival")
        )


class OVAPIWalkingPlannerSensor(OVAPIBaseSensor):
    """Sensor that calculates when to leave based on walking time."""

    _attr_icon = "mdi:walk"
    _attr_translation_key = "time_to_leave"
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.DURATION

    def __init__(
        self,
        coordinator: OVAPIDataUpdateCoordinator,
        entry: ConfigEntry,
        walking_time: int,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry)
        self._walking_time = walking_time
        self._attr_unique_id = f"{entry.entry_id}_walking_planner"

    @property
    def native_value(self) -> StateType:
        """Return minutes until you need to leave."""
        if not self.coordinator.data or len(self.coordinator.data) == 0:
            return None
        
        bus = self.coordinator.data[0]
        minutes_until_bus = self.coordinator.client.get_time_until_departure(
            bus.get("expected_arrival")
        )
        
        if minutes_until_bus is None:
            return None
        
        # Calculate when to leave: bus arrival time - walking time
        time_to_leave = minutes_until_bus - self._walking_time
        
        # Return 0 if we should already have left
        return max(0, time_to_leave)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        if not self.coordinator.data or len(self.coordinator.data) == 0:
            return {"walking_time_minutes": self._walking_time}
        
        bus = self.coordinator.data[0]
        minutes_until_bus = self.coordinator.client.get_time_until_departure(
            bus.get("expected_arrival")
        )
        
        time_to_leave = None
        should_leave_now = False
        
        if minutes_until_bus is not None:
            time_to_leave = minutes_until_bus - self._walking_time
            should_leave_now = time_to_leave <= 0
        
        return {
            "walking_time_minutes": self._walking_time,
            "bus_arrival_minutes": minutes_until_bus,
            "should_leave_now": should_leave_now,
            "bus_line": bus.get("line_number"),
            "bus_destination": bus.get("destination"),
        }
