"""Diagnostics support for OVAPI."""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from . import OVAPIDataUpdateCoordinator
from .const import DOMAIN

TO_REDACT = {"latitude", "longitude", "stop_lat", "stop_lon"}


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
    }

    return async_redact_data(diagnostics_data, TO_REDACT)
