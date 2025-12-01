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
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up OVAPI from a config entry."""
    session = async_get_clientsession(hass)
    client = OVAPIClient(session)

    coordinator = OVAPIDataUpdateCoordinator(
        hass,
        client=client,
        stop_code=entry.data[CONF_STOP_CODE],
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
        stop_code: str,
        line_number: str | None,
        destination: str | None,
        scan_interval: int,
    ) -> None:
        """Initialize."""
        self.client = client
        self.stop_code = stop_code
        self.line_number = line_number
        self.destination = destination

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )

    async def _async_update_data(self):
        """Update data via library."""
        try:
            stop_data = await self.client.get_stop_info(self.stop_code)
            passes = self.client.filter_passes(
                stop_data,
                line_number=self.line_number,
                destination=self.destination,
            )
            return passes
        except Exception as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err
