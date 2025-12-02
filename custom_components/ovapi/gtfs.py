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

# Bundled GTFS file (shipped with integration)
# Uses gtfs-kv7 which contains only stops with confirmed real-time data (8-digit codes)
# Note: Some stops work via manual entry but aren't in GTFS (e.g., Rotterdam Huslystraat: 31002742)
BUNDLED_GTFS_FILE = Path(__file__).parent.parent.parent / "gtfs" / "gtfs-kv7.zip"

GTFS_CACHE_DURATION = timedelta(days=1)  # Cache GTFS data for 1 day
GTFS_CACHE_FILE = "ovapi_gtfs_cache.json"
GTFS_CACHE_VERSION = 7  # Increment when cache format changes


class GTFSStopCache:
    """Cache for GTFS stop data."""

    def __init__(self, cache_dir: Path) -> None:
        """Initialize the cache."""
        self._stops: dict[str, dict[str, str]] = {}
        self._last_update: datetime | None = None
        self._cache_dir = cache_dir
        self._cache_file = cache_dir / GTFS_CACHE_FILE

    async def _load_from_disk(self) -> None:
        """Load cache from disk (async)."""
        if not self._cache_file.exists():
            return
        
        try:
            content = await asyncio.to_thread(self._cache_file.read_text, encoding="utf-8")
            data = json.loads(content)
            
            # Check cache version - invalidate if mismatch
            cache_version = data.get("version", 1)
            if cache_version != GTFS_CACHE_VERSION:
                _LOGGER.info("GTFS cache version mismatch (cached: %s, current: %s), invalidating cache", 
                            cache_version, GTFS_CACHE_VERSION)
                return
            
            self._stops = data.get("stops", {})
            last_update_str = data.get("last_update")
            if last_update_str:
                self._last_update = datetime.fromisoformat(last_update_str)
                _LOGGER.info("Loaded GTFS cache from disk with %d stops (last update: %s)", 
                            len(self._stops), self._last_update)
        except Exception as err:
            _LOGGER.warning("Failed to load GTFS cache from disk: %s", err)
    
    async def _save_to_disk(self) -> None:
        """Save cache to disk (async)."""
        try:
            # Ensure directory exists
            await asyncio.to_thread(self._cache_dir.mkdir, parents=True, exist_ok=True)
            
            data = {
                "version": GTFS_CACHE_VERSION,
                "stops": self._stops,
                "last_update": self._last_update.isoformat() if self._last_update else None,
            }
            
            content = json.dumps(data)
            await asyncio.to_thread(self._cache_file.write_text, content, "utf-8")
            
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

    async def update_stops(self, stops: dict[str, dict[str, str]]) -> None:
        """Update cached stops."""
        self._stops = stops
        self._last_update = datetime.now()
        await self._save_to_disk()

    def search(self, query: str, limit: int = 10, group_by_name: bool = True) -> list[dict[str, Any]]:
        """Search stops by name or code.
        
        Args:
            query: Search query (stop name or code)
            limit: Maximum number of results
            group_by_name: If True, group stops with the same name together
        """
        query_lower = query.lower()
        results = []
        grouped_stops = {}  # Map stop_name -> list of stops
        
        _LOGGER.debug("Searching %d stops for query: '%s'", len(self._stops), query_lower)

        for stop_id, stop_data in self._stops.items():
            stop_name = stop_data.get("stop_name", "").lower()
            
            # Match on stop_id or stop name
            if query_lower in stop_id.lower() or query_lower in stop_name:
                # Get the actual stop_code (timing point code) for API calls
                api_stop_code = stop_data.get("stop_code", stop_id)
                
                result = {
                    "stop_code": api_stop_code,  # Use timing point code for API
                    "stop_id": stop_id,  # Keep original ID for reference
                    "stop_name": stop_data.get("stop_name", ""),
                    "stop_lat": stop_data.get("stop_lat", ""),
                    "stop_lon": stop_data.get("stop_lon", ""),
                }
                
                # Add routes/lines info if available
                routes = stop_data.get("routes", [])
                if routes:
                    result["routes"] = routes
                
                if group_by_name:
                    # Group by stop name
                    original_name = stop_data.get("stop_name", "")
                    if original_name not in grouped_stops:
                        grouped_stops[original_name] = []
                    grouped_stops[original_name].append(result)
                else:
                    results.append(result)
                    if len(results) >= limit:
                        break

        # Convert grouped stops to result list
        if group_by_name:
            _LOGGER.debug("Found %d matching stop groups for query '%s'", len(grouped_stops), query_lower)
            for stop_name, stops in grouped_stops.items():
                # Prefer 8-digit stop codes (main stops with real-time data)
                # Sort: 8-digit codes first, then by stop_code
                stops_sorted = sorted(
                    stops, 
                    key=lambda s: (len(s["stop_code"]) != 8, s["stop_code"])
                )
                
                # Combine all routes from all stops
                all_routes = []
                for stop in stops_sorted:
                    all_routes.extend(stop.get("routes", []))
                
                result = {
                    "stop_name": stop_name,
                    "stop_codes": [s["stop_code"] for s in stops_sorted],
                    "stop_lat": stops_sorted[0].get("stop_lat", ""),
                    "stop_lon": stops_sorted[0].get("stop_lon", ""),
                    "direction_count": len(stops_sorted),
                }
                
                if all_routes:
                    result["routes"] = ", ".join(sorted(set(all_routes))[:5])  # Show up to 5 unique routes
                
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
        self._cache_loaded = False

    async def download_and_parse_stops(self) -> dict[str, dict[str, str]]:
        """Load and parse stops.txt from bundled GTFS zip file."""
        _LOGGER.info("Loading GTFS data (cache version %d)", GTFS_CACHE_VERSION)
        
        # Use bundled gtfs-kv7.zip file
        gtfs_file = BUNDLED_GTFS_FILE
        
        if not gtfs_file.exists():
            raise ValueError(f"Bundled GTFS file not found at {gtfs_file}")
        
        _LOGGER.info("Parsing stops from %s", gtfs_file)

        try:
            # Read the zip file
            zip_data = await asyncio.to_thread(gtfs_file.read_bytes)
            
            # Parse the ZIP file
            stops: dict[str, dict[str, Any]] = {}
            
            with zipfile.ZipFile(BytesIO(zip_data)) as zip_file:
                if "stops.txt" not in zip_file.namelist():
                    raise ValueError("stops.txt not found in GTFS archive")
                
                # Parse stops
                with zip_file.open("stops.txt") as stops_file:
                    stops_text = stops_file.read().decode("utf-8")
                    reader = csv.DictReader(StringIO(stops_text))
            
            row_count = 0
            for row in reader:
                stop_id = row.get("stop_id", "")
                if stop_id:
                    # Debug: Log first row to see what data we have
                    if row_count == 0:
                        _LOGGER.info("GTFS stops.txt columns: %s", list(row.keys()))
                        _LOGGER.debug("First stop: stop_id=%s, stop_code='%s', stop_name=%s", 
                                      stop_id, row.get("stop_code", ""), row.get("stop_name", ""))
                    row_count += 1
                    
                    # Store both stop_id (for search) and stop_code (for API calls)
                    # Fallback to stop_id if stop_code is empty
                    api_code = row.get("stop_code", "").strip() or stop_id
                    stops[stop_id] = {
                        "stop_name": row.get("stop_name", ""),
                        "stop_lat": row.get("stop_lat", ""),
                        "stop_lon": row.get("stop_lon", ""),
                        "stop_code": api_code,  # Timing point code for v0 API
                        "routes": [],  # Routes not used currently
                    }
            
            _LOGGER.info("Parsed %d stops from GTFS stops.txt", len(stops))
            return stops

        except Exception as err:
            _LOGGER.error("Error loading/parsing GTFS stops.txt: %s", err)
            # Try to use cached data as fallback
            cached_stops = self._cache.get_stops()
            if cached_stops:
                _LOGGER.warning("Using %d cached stops after error", len(cached_stops))
                return cached_stops
            raise

    async def ensure_cache(self) -> None:
        """Ensure cache is populated and not expired."""
        # Load cache from disk on first access
        if not self._cache_loaded:
            await self._cache._load_from_disk()
            self._cache_loaded = True
        
        if self._cache.is_expired():
            stops = await self.download_and_parse_stops()
            await self._cache.update_stops(stops)

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
