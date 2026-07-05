"""The OVAPI integration."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import OVAPIClient
from .const import (
    CONF_DESTINATION,
    CONF_ENABLE_LIVE_TRACKING,
    CONF_LINE_NUMBER,
    CONF_SCAN_INTERVAL,
    CONF_STOP_CODE,
    CONF_STOP_CODES,
    DEFAULT_ENABLE_LIVE_TRACKING,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

if TYPE_CHECKING:
    # Only needed for the type hint — kv6.py (and pyzmq) is imported for real
    # further down, and only when a config entry actually enables tracking.
    from .kv6 import KV6LiveTracker

_LOGGER = logging.getLogger(__name__)


def _platforms_for_entry(entry: ConfigEntry) -> list[Platform]:
    """Return the platforms this entry needs.

    DEVICE_TRACKER is only forwarded when live tracking is enabled, since it
    has nothing to show otherwise — see CONF_ENABLE_LIVE_TRACKING.
    """
    platforms: list[Platform] = [Platform.SENSOR]
    if entry.data.get(CONF_ENABLE_LIVE_TRACKING, DEFAULT_ENABLE_LIVE_TRACKING):
        platforms.append(Platform.DEVICE_TRACKER)
    return platforms


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up OVAPI from a config entry."""
    session = async_get_clientsession(hass)
    client = OVAPIClient(session)

    # Support both single stop_code and multiple stop_codes
    stop_codes = entry.data.get(CONF_STOP_CODES)
    if stop_codes is None:
        # Backward compatibility: single stop_code
        stop_codes = [entry.data[CONF_STOP_CODE]]

    kv6_manager: KV6LiveTracker | None = None
    if entry.data.get(CONF_ENABLE_LIVE_TRACKING, DEFAULT_ENABLE_LIVE_TRACKING):
        # Lazy import: pyzmq is only ever loaded into the process for entries
        # that actually opt in to live tracking.
        from .kv6 import KV6LiveTracker as _KV6LiveTracker

        kv6_manager = _KV6LiveTracker(hass, entry.entry_id)
        kv6_manager.start()

    coordinator = OVAPIDataUpdateCoordinator(
        hass,
        client=client,
        stop_codes=stop_codes,
        line_number=entry.data.get(CONF_LINE_NUMBER),
        destination=entry.data.get(CONF_DESTINATION),
        scan_interval=entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        kv6_manager=kv6_manager,
    )

    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    # Stashed on the coordinator (not recomputed from entry.data at unload
    # time) because the options flow updates entry.data *before* reloading —
    # async_unload_entry would otherwise see the post-toggle platform list,
    # which may not match what was actually forwarded at setup time.
    platforms = _platforms_for_entry(entry)
    coordinator.platforms = platforms
    await hass.config_entries.async_forward_entry_setups(entry, platforms)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    coordinator: OVAPIDataUpdateCoordinator = entry.runtime_data
    unload_ok = await hass.config_entries.async_unload_platforms(entry, coordinator.platforms)
    if coordinator.kv6_manager is not None:
        await coordinator.kv6_manager.async_stop()
    return unload_ok


class OVAPIDataUpdateCoordinator(DataUpdateCoordinator[list[dict[str, Any]]]):
    """Class to manage fetching OVAPI data."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: OVAPIClient,
        stop_codes: list[str],
        line_number: str | None,
        destination: str | None,
        scan_interval: int,
        kv6_manager: KV6LiveTracker | None = None,
    ) -> None:
        """Initialize."""
        self.client = client
        self.stop_codes = stop_codes
        # Backward compatibility
        self.stop_code = stop_codes[0] if stop_codes else None
        # Convert "All destinations" to None for filtering
        self.line_number = line_number
        self.destination = None if destination == "All destinations" else destination
        self.kv6_manager = kv6_manager
        # Set by async_setup_entry right after construction; declared here so
        # it always exists even if something inspects the coordinator before
        # that point (e.g. a test).
        self.platforms: list[Platform] = [Platform.SENSOR]

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )

    async def _async_update_data(self) -> list[dict[str, Any]]:
        """Update data via library."""
        try:
            all_passes: list[dict[str, Any]] = []

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
            all_passes.sort(key=lambda x: x.get("expected_arrival", ""))

            if self.kv6_manager is not None:
                # Feed KV6 subscriptions off data already fetched above — no
                # second HTTP call. DataOwnerCode is enough to pick the right
                # topics; the finer-grained match happens in get_position().
                owners = {p["data_owner_code"] for p in all_passes if p.get("data_owner_code")}
                self.kv6_manager.update_subscriptions(owners)

            _LOGGER.debug("Combined %d total passes, next: line %s to %s at %s",
                         len(all_passes),
                         all_passes[0].get("line_number") if all_passes else "N/A",
                         all_passes[0].get("destination") if all_passes else "N/A",
                         all_passes[0].get("expected_arrival") if all_passes else "N/A")

            return all_passes
        except Exception as err:
            _LOGGER.error("Error communicating with API: %s", err)
            raise UpdateFailed(f"Error communicating with API: {err}") from err
