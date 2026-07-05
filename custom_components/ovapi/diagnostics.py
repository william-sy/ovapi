"""Diagnostics support for OVAPI."""
from __future__ import annotations

import dataclasses
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from . import OVAPIDataUpdateCoordinator
from .const import DOMAIN

TO_REDACT = {"latitude", "longitude", "stop_lat", "stop_lon"}


def _kv6_diagnostics(coordinator: OVAPIDataUpdateCoordinator) -> dict[str, Any]:
    """Summarize KV6 live-tracking state, if enabled.

    Uses dataclasses.asdict() so any position included keeps the
    latitude/longitude field names — TO_REDACT above catches those
    recursively with no changes needed here.
    """
    manager = coordinator.kv6_manager
    if manager is None:
        return {"enabled": False}

    def _position_or_none(index: int) -> dict[str, Any] | None:
        if not coordinator.data or len(coordinator.data) <= index:
            return None
        bus = coordinator.data[index]
        position = manager.get_position(
            bus.get("data_owner_code"),
            bus.get("line_planning_number"),
            bus.get("journey_number"),
            bus.get("operation_date"),
        )
        return dataclasses.asdict(position) if position is not None else None

    return {
        "enabled": True,
        "current_bus_position": _position_or_none(0),
        "next_bus_position": _position_or_none(1),
    }


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator: OVAPIDataUpdateCoordinator = entry.runtime_data

    diagnostics_data = {
        "entry": {
            "title": entry.title,
            "data": dict(entry.data),
        },
        "coordinator": {
            "stop_code": coordinator.stop_code,
            "line_number": coordinator.line_number,
            "destination": coordinator.destination,
            "last_update_success": coordinator.last_update_success,
            "update_interval": str(coordinator.update_interval),
        },
        "data": {
            "passes_count": len(coordinator.data) if coordinator.data else 0,
            "passes": coordinator.data if coordinator.data else [],
        },
        "kv6": _kv6_diagnostics(coordinator),
    }

    return async_redact_data(diagnostics_data, TO_REDACT)
