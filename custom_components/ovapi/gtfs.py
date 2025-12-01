"""GTFS data handler for OVAPI integration."""
import asyncio
import csv
import logging
import zipfile
from datetime import datetime, timedelta
from io import BytesIO, StringIO
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

GTFS_BASE_URL = "https://gtfs.ovapi.nl/govi"
GTFS_CACHE_DURATION = timedelta(days=1)  # Cache GTFS data for 1 day


class GTFSStopCache:
    """Cache for GTFS stop data."""

    def __init__(self) -> None:
        """Initialize the cache."""
        self._stops: dict[str, dict[str, str]] = {}
        self._last_update: datetime | None = None

    def is_expired(self) -> bool:
        """Check if cache is expired."""
        if self._last_update is None:
            return True
        return datetime.now() - self._last_update > GTFS_CACHE_DURATION

    def get_stops(self) -> dict[str, dict[str, str]]:
        """Get cached stops."""
        return self._stops

    def update_stops(self, stops: dict[str, dict[str, str]]) -> None:
        """Update cached stops."""
        self._stops = stops
        self._last_update = datetime.now()

    def search(self, query: str, limit: int = 10) -> list[dict[str, str]]:
        """Search stops by name or code."""
        query_lower = query.lower()
        results = []

        for stop_code, stop_data in self._stops.items():
            stop_name = stop_data.get("stop_name", "").lower()
            
            # Match on stop code or stop name
            if query_lower in stop_code.lower() or query_lower in stop_name:
                results.append({
                    "stop_code": stop_code,
                    "stop_name": stop_data.get("stop_name", ""),
                    "stop_lat": stop_data.get("stop_lat", ""),
                    "stop_lon": stop_data.get("stop_lon", ""),
                })
                
                if len(results) >= limit:
                    break

        return results


class GTFSDataHandler:
    """Handler for GTFS data from OVAPI."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        """Initialize the handler."""
        self._session = session
        self._cache = GTFSStopCache()

    async def get_gtfs_filename(self) -> str | None:
        """Get the current GTFS filename from the directory."""
        try:
            async with asyncio.timeout(10):
                # Try to construct the filename based on today's date
                today = datetime.now().strftime("%Y%m%d")
                filename = f"gtfs-kv7-{today}.zip"
                
                # Check if this file exists
                url = f"{GTFS_BASE_URL}/{filename}"
                async with self._session.head(url) as response:
                    if response.status == 200:
                        return filename
                
                # If not, try yesterday's date
                yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
                filename = f"gtfs-kv7-{yesterday}.zip"
                
                url = f"{GTFS_BASE_URL}/{filename}"
                async with self._session.head(url) as response:
                    if response.status == 200:
                        return filename
                
                _LOGGER.warning("Could not determine GTFS filename")
                return None
                
        except Exception as err:
            _LOGGER.error("Error determining GTFS filename: %s", err)
            return None

    async def download_and_parse_stops(self) -> dict[str, dict[str, str]]:
        """Download GTFS file and parse stops.txt."""
        filename = await self.get_gtfs_filename()
        if not filename:
            raise ValueError("Could not determine GTFS filename")

        url = f"{GTFS_BASE_URL}/{filename}"
        _LOGGER.info("Downloading GTFS data from %s", url)

        try:
            async with asyncio.timeout(30):
                async with self._session.get(url) as response:
                    response.raise_for_status()
                    zip_data = await response.read()

            # Parse the ZIP file
            stops = {}
            with zipfile.ZipFile(BytesIO(zip_data)) as zip_file:
                if "stops.txt" not in zip_file.namelist():
                    raise ValueError("stops.txt not found in GTFS archive")

                with zip_file.open("stops.txt") as stops_file:
                    # Read as text
                    stops_text = stops_file.read().decode("utf-8")
                    reader = csv.DictReader(StringIO(stops_text))

                    for row in reader:
                        stop_id = row.get("stop_id", "")
                        if stop_id:
                            stops[stop_id] = {
                                "stop_name": row.get("stop_name", ""),
                                "stop_lat": row.get("stop_lat", ""),
                                "stop_lon": row.get("stop_lon", ""),
                            }

            _LOGGER.info("Parsed %d stops from GTFS data", len(stops))
            return stops

        except asyncio.TimeoutError as err:
            _LOGGER.error("Timeout downloading GTFS data: %s", err)
            raise
        except Exception as err:
            _LOGGER.error("Error downloading/parsing GTFS data: %s", err)
            raise

    async def ensure_cache(self) -> None:
        """Ensure cache is populated and not expired."""
        if self._cache.is_expired():
            stops = await self.download_and_parse_stops()
            self._cache.update_stops(stops)

    async def search_stops(self, query: str, limit: int = 10) -> list[dict[str, str]]:
        """Search for stops by name or code."""
        await self.ensure_cache()
        return self._cache.search(query, limit)

    async def get_stop_name(self, stop_code: str) -> str | None:
        """Get the name of a stop by its code."""
        await self.ensure_cache()
        stops = self._cache.get_stops()
        stop_data = stops.get(stop_code)
        return stop_data.get("stop_name") if stop_data else None

    def get_cached_stop_name(self, stop_code: str) -> str | None:
        """Get stop name from cache without fetching (sync method)."""
        stops = self._cache.get_stops()
        stop_data = stops.get(stop_code)
        return stop_data.get("stop_name") if stop_data else None
