"""GTFS data handler for OVAPI integration."""
import asyncio
import csv
import json
import logging
import zipfile
from datetime import datetime, timedelta
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

GTFS_BASE_URL = "https://gtfs.ovapi.nl/govi"
GTFS_FALLBACK_URL = "https://github.com/william-sy/ovapi/raw/refs/heads/main/rate_limit/gtfs-kv7.zip"
GTFS_CACHE_DURATION = timedelta(days=1)  # Cache GTFS data for 1 day
GTFS_CACHE_FILE = "ovapi_gtfs_cache.json"


class GTFSStopCache:
    """Cache for GTFS stop data."""

    def __init__(self, cache_dir: Path) -> None:
        """Initialize the cache."""
        self._stops: dict[str, dict[str, str]] = {}
        self._last_update: datetime | None = None
        self._cache_dir = cache_dir
        self._cache_file = cache_dir / GTFS_CACHE_FILE
        
        # Load cache from disk if available
        self._load_from_disk()

    def _load_from_disk(self) -> None:
        """Load cache from disk."""
        if not self._cache_file.exists():
            return
        
        try:
            with open(self._cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                self._stops = data.get("stops", {})
                last_update_str = data.get("last_update")
                if last_update_str:
                    self._last_update = datetime.fromisoformat(last_update_str)
                    _LOGGER.info("Loaded GTFS cache from disk with %d stops (last update: %s)", 
                                len(self._stops), self._last_update)
        except Exception as err:
            _LOGGER.warning("Failed to load GTFS cache from disk: %s", err)
    
    def _save_to_disk(self) -> None:
        """Save cache to disk."""
        try:
            # Ensure directory exists
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            
            data = {
                "stops": self._stops,
                "last_update": self._last_update.isoformat() if self._last_update else None,
            }
            
            with open(self._cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f)
            
            _LOGGER.debug("Saved GTFS cache to disk")
        except Exception as err:
            _LOGGER.warning("Failed to save GTFS cache to disk: %s", err)

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
        self._save_to_disk()

    def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """Search stops by name or code."""
        query_lower = query.lower()
        results = []

        for stop_code, stop_data in self._stops.items():
            stop_name = stop_data.get("stop_name", "").lower()
            
            # Match on stop code or stop name
            if query_lower in stop_code.lower() or query_lower in stop_name:
                result = {
                    "stop_code": stop_code,
                    "stop_name": stop_data.get("stop_name", ""),
                    "stop_lat": stop_data.get("stop_lat", ""),
                    "stop_lon": stop_data.get("stop_lon", ""),
                }
                
                # Add routes/lines info if available
                routes = stop_data.get("routes", [])
                if routes:
                    result["routes"] = ", ".join(sorted(set(routes))[:5])  # Show up to 5 routes
                
                results.append(result)
                
                if len(results) >= limit:
                    break

        return results


class GTFSDataHandler:
    """Handler for GTFS data from OVAPI."""

    def __init__(self, session: aiohttp.ClientSession, cache_dir: Path) -> None:
        """Initialize the handler."""
        self._session = session
        self._cache = GTFSStopCache(cache_dir)

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
                
                # Don't try rate_limit on OVAPI server - we use GitHub fallback instead during download
                
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
                    # Handle rate limiting by trying fallback or using cached data
                    if response.status == 429:
                        _LOGGER.warning("Rate limited by GTFS server (429), trying GitHub fallback")
                        
                        # Try GitHub fallback with older but stable data
                        try:
                            async with self._session.get(GTFS_FALLBACK_URL) as fallback_response:
                                _LOGGER.debug("GitHub fallback response status: %s", fallback_response.status)
                                if fallback_response.status == 200:
                                    _LOGGER.info("Successfully using GitHub fallback GTFS file from %s", GTFS_FALLBACK_URL)
                                    zip_data = await fallback_response.read()
                                    # Continue with normal parsing below
                                else:
                                    _LOGGER.warning("GitHub fallback returned status %s", fallback_response.status)
                                    raise aiohttp.ClientError(f"GitHub fallback failed with status {fallback_response.status}")
                        except Exception as fallback_err:
                            # GitHub fallback failed, try cache
                            _LOGGER.warning("GitHub fallback failed (%s), using cached data if available", fallback_err)
                            cached_stops = self._cache.get_stops()
                            if cached_stops:
                                _LOGGER.info("Using %d cached stops", len(cached_stops))
                                return cached_stops
                            raise aiohttp.ClientResponseError(
                                request_info=response.request_info,
                                history=response.history,
                                status=response.status,
                                message="Rate limited and no cache available",
                                headers=response.headers,
                            )
                    else:
                        response.raise_for_status()
                        zip_data = await response.read()

            # Parse the ZIP file
            stops: dict[str, dict[str, Any]] = {}
            trip_routes: dict[str, str] = {}  # trip_id -> route_short_name
            
            with zipfile.ZipFile(BytesIO(zip_data)) as zip_file:
                if "stops.txt" not in zip_file.namelist():
                    raise ValueError("stops.txt not found in GTFS archive")

                # Parse stops
                with zip_file.open("stops.txt") as stops_file:
                    stops_text = stops_file.read().decode("utf-8")
                    reader = csv.DictReader(StringIO(stops_text))

                    for row in reader:
                        stop_id = row.get("stop_id", "")
                        if stop_id:
                            stops[stop_id] = {
                                "stop_name": row.get("stop_name", ""),
                                "stop_lat": row.get("stop_lat", ""),
                                "stop_lon": row.get("stop_lon", ""),
                                "routes": [],
                            }
                
                # Parse routes to get route_short_name
                routes_map: dict[str, str] = {}  # route_id -> route_short_name
                if "routes.txt" in zip_file.namelist():
                    with zip_file.open("routes.txt") as routes_file:
                        routes_text = routes_file.read().decode("utf-8")
                        reader = csv.DictReader(StringIO(routes_text))
                        for row in reader:
                            route_id = row.get("route_id", "")
                            route_short = row.get("route_short_name", "")
                            if route_id and route_short:
                                routes_map[route_id] = route_short
                
                # Parse trips to map trip_id -> route_id
                if "trips.txt" in zip_file.namelist():
                    with zip_file.open("trips.txt") as trips_file:
                        trips_text = trips_file.read().decode("utf-8")
                        reader = csv.DictReader(StringIO(trips_text))
                        for row in reader:
                            trip_id = row.get("trip_id", "")
                            route_id = row.get("route_id", "")
                            if trip_id and route_id and route_id in routes_map:
                                trip_routes[trip_id] = routes_map[route_id]
                
                # Parse stop_times to link stops with routes
                if "stop_times.txt" in zip_file.namelist():
                    with zip_file.open("stop_times.txt") as stop_times_file:
                        stop_times_text = stop_times_file.read().decode("utf-8")
                        reader = csv.DictReader(StringIO(stop_times_text))
                        
                        for row in reader:
                            trip_id = row.get("trip_id", "")
                            stop_id = row.get("stop_id", "")
                            
                            if trip_id in trip_routes and stop_id in stops:
                                route = trip_routes[trip_id]
                                if route not in stops[stop_id]["routes"]:
                                    stops[stop_id]["routes"].append(route)

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
