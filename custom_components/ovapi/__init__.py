"""The OVAPI integration."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import OVAPIClient
from .const import (
    CONF_DESTINATION,
    CONF_LINE_NUMBER,
    CONF_SCAN_INTERVAL,
    CONF_STOP_CODE,
    CONF_STOP_CODES,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up OVAPI from a config entry."""
    session = async_get_clientsession(hass)
    client = OVAPIClient(session)

    # Support both single stop_code and multiple stop_codes
    stop_codes = entry.data.get(CONF_STOP_CODES)
    if stop_codes is None:
        # Backward compatibility: single stop_code
        stop_codes = [entry.data[CONF_STOP_CODE]]

    coordinator = OVAPIDataUpdateCoordinator(
        hass,
        client=client,
        stop_codes=stop_codes,
        line_number=entry.data.get(CONF_LINE_NUMBER),
        destination=entry.data.get(CONF_DESTINATION),
        scan_interval=entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
    )

    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


class OVAPIDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching OVAPI data."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: OVAPIClient,
        stop_codes: list[str],
        line_number: str | None,
        destination: str | None,
        scan_interval: int,
    ) -> None:
        """Initialize."""
        self.client = client
        self.stop_codes = stop_codes
        # Backward compatibility
        self.stop_code = stop_codes[0] if stop_codes else None
        # Convert "All destinations" to None for filtering
        self.line_number = line_number
        self.destination = None if destination == "All destinations" else destination
        
        _LOGGER.warning("Coordinator init: stop_codes=%s, line=%s, destination_raw='%s', destination_filtered=%s", 
                       stop_codes, line_number, destination, self.destination)

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )

    async def _async_update_data(self):
        """Update data via library."""
        try:
            all_passes = []
            
            # Fetch data from all stop codes and combine
            for stop_code in self.stop_codes:
                stop_data = await self.client.get_stop_info(stop_code)
                
                passes = self.client.filter_passes(
                    stop_data,
                    line_number=self.line_number,
                    destination=self.destination,
                )
                
                _LOGGER.debug("Stop %s returned %d passes (line=%s, dest=%s)", 
                             stop_code, len(passes), self.line_number, self.destination)
                
                all_passes.extend(passes)
            
            # Sort by expected arrival time
            all_passes.sort(key=lambda x: x.get("ExpectedArrivalTime", ""))
            
            _LOGGER.debug("Combined %d total passes, next: %s to %s at %s", 
                         len(all_passes),
                         all_passes[0].get("LinePublicNumber") if all_passes else "N/A",
                         all_passes[0].get("DestinationName50") if all_passes else "N/A",
                         all_passes[0].get("ExpectedArrivalTime") if all_passes else "N/A")
            
            return all_passes
        except Exception as err:
            _LOGGER.error("Error communicating with API: %s", err)
            raise UpdateFailed(f"Error communicating with API: {err}") from err
