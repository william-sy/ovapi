"""API client for OVAPI.nl."""
import asyncio
import logging
from datetime import datetime
from typing import Any

import aiohttp

from .const import API_BASE_URL, API_TIMEOUT

_LOGGER = logging.getLogger(__name__)


class OVAPIClient:
    """OVAPI API client."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        """Initialize the API client."""
        self._session = session

    async def get_stop_info(self, stop_code: str) -> dict[str, Any]:
        """Get information for a specific stop."""
        url = f"{API_BASE_URL}/stopareacode/{stop_code}"
        
        try:
            async with asyncio.timeout(API_TIMEOUT):
                response = await self._session.get(url)
                response.raise_for_status()
                data = await response.json()
                return data
        except asyncio.TimeoutError as err:
            _LOGGER.error("Timeout fetching data from OVAPI: %s", err)
            raise
        except aiohttp.ClientError as err:
            _LOGGER.error("Error fetching data from OVAPI: %s", err)
            raise
        except Exception as err:
            _LOGGER.error("Unexpected error fetching data from OVAPI: %s", err)
            raise

    def filter_passes(
        self,
        stop_data: dict[str, Any],
        line_number: str | None = None,
        destination: str | None = None,
    ) -> list[dict[str, Any]]:
        """Filter passes by line number and destination."""
        passes = []
        total_passes_found = 0
        
        # OVAPI returns data in format: {stop_code: {TransportType: {DataOwnerCode: {LinePlanningNumber: {...}}}}}
        for stop_code, stop_info in stop_data.items():
            if stop_code == "stopareacode":
                continue
            
            _LOGGER.debug("Processing stop_code: %s", stop_code)
                
            for transport_type, transport_data in stop_info.items():
                _LOGGER.debug("  Transport type: %s", transport_type)
                for owner_code, owner_data in transport_data.items():
                    _LOGGER.debug("    Owner code: %s", owner_code)
                    for line_key, line_data in owner_data.items():
                        _LOGGER.debug("      Line key: %s", line_key)
                        # Extract passes
                        if "Passes" in line_data:
                            _LOGGER.debug("        Found %d passes", len(line_data["Passes"]))
                            for pass_data in line_data["Passes"].values():
                                total_passes_found += 1
                                pass_line = pass_data.get("LinePublicNumber")
                                pass_dest = pass_data.get("DestinationName50")
                                
                                _LOGGER.debug("          Pass: line=%s, dest=%s", pass_line, pass_dest)
                                
                                # Filter by line number
                                if line_number and pass_line != line_number:
                                    _LOGGER.debug("            Skipped: line filter (want %s, got %s)", line_number, pass_line)
                                    continue
                                
                                # Filter by destination
                                if destination and destination.lower() not in pass_dest.lower():
                                    _LOGGER.debug("            Skipped: dest filter (want %s, got %s)", destination, pass_dest)
                                    continue
                                
                                passes.append({
                                    "line_number": pass_data.get("LinePublicNumber"),
                                    "destination": pass_data.get("DestinationName50"),
                                    "expected_arrival": pass_data.get("ExpectedArrivalTime"),
                                    "target_arrival": pass_data.get("TargetArrivalTime"),
                                    "delay": self._calculate_delay(
                                        pass_data.get("ExpectedArrivalTime"),
                                        pass_data.get("TargetArrivalTime")
                                    ),
                                    "transport_type": pass_data.get("TransportType"),
                                })
                                _LOGGER.debug("            MATCHED!")
        
        _LOGGER.debug("Total passes found: %d, After filtering: %d", total_passes_found, len(passes))
        
        # Sort by expected arrival time
        passes.sort(key=lambda x: x.get("expected_arrival", ""))
        return passes

    def _calculate_delay(self, expected: str | None, target: str | None) -> int | None:
        """Calculate delay in minutes."""
        if not expected or not target:
            return None
        
        try:
            # OVAPI times are in format: "2023-12-01T14:30:00"
            expected_dt = datetime.fromisoformat(expected.replace("Z", "+00:00"))
            target_dt = datetime.fromisoformat(target.replace("Z", "+00:00"))
            delay_seconds = (expected_dt - target_dt).total_seconds()
            return int(delay_seconds / 60)
        except (ValueError, AttributeError) as err:
            _LOGGER.debug("Error calculating delay: %s", err)
            return None

    def get_time_until_departure(self, departure_time: str | None) -> int | None:
        """Get minutes until departure."""
        if not departure_time:
            return None
        
        try:
            departure_dt = datetime.fromisoformat(departure_time.replace("Z", "+00:00"))
            now = datetime.now(departure_dt.tzinfo)
            minutes = int((departure_dt - now).total_seconds() / 60)
            return max(0, minutes)  # Don't return negative values
        except (ValueError, AttributeError) as err:
            _LOGGER.debug("Error calculating time until departure: %s", err)
            return None
