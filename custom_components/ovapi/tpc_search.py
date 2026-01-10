"""TPC Finder search using GitHub-hosted JSON data."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp

from .const import (
    TPC_FINDER_CITIES_URL,
    TPC_FINDER_STOPS_URL,
    TPC_FINDER_LINES_URL,
)

_LOGGER = logging.getLogger(__name__)


class TPCSearchHandler:
    """Handle searches using TPC Finder JSON data."""

    def __init__(self, session: aiohttp.ClientSession):
        """Initialize the search handler."""
        self.session = session
        self._cities = None
        self._stops_by_city = None
        self._lines_by_stop = None

    async def _load_data(self) -> None:
        """Load JSON data from GitHub if not already loaded."""
        if self._cities is not None:
            return

        try:
            # Load cities
            async with self.session.get(TPC_FINDER_CITIES_URL, timeout=10) as response:
                if response.status == 200:
                    self._cities = await response.json()
                else:
                    raise Exception(f"Failed to load cities: {response.status}")

            # Load stops by city
            async with self.session.get(TPC_FINDER_STOPS_URL, timeout=10) as response:
                if response.status == 200:
                    self._stops_by_city = await response.json()
                else:
                    raise Exception(f"Failed to load stops: {response.status}")

            # Load lines by stop
            async with self.session.get(TPC_FINDER_LINES_URL, timeout=10) as response:
                if response.status == 200:
                    self._lines_by_stop = await response.json()
                else:
                    raise Exception(f"Failed to load lines: {response.status}")

            _LOGGER.info("Successfully loaded TPC Finder data")

        except Exception as err:
            _LOGGER.error("Failed to load TPC Finder data: %s", err)
            raise

    async def get_cities(self) -> list[dict[str, Any]]:
        """Get list of all cities."""
        await self._load_data()
        return self._cities or []

    async def search_stops(
        self, query: str, city: str | None = None, realtime_only: bool = True, limit: int = 20
    ) -> list[dict[str, Any]]:
        """
        Search for stops by name or TPC code.

        Args:
            query: Search query (stop name or TPC code)
            city: Optional city name to filter by
            realtime_only: Only return stops with real-time data
            limit: Maximum number of results to return

        Returns:
            List of stop dictionaries with stop_codes, stop_name, city, etc.
            Stops with the same name are grouped together with multiple stop_codes.
        """
        await self._load_data()

        if not self._stops_by_city:
            return []

        query_lower = query.lower().strip()
        grouped_stops = {}  # Map (city, stop_name) -> list of stop data

        # Determine which cities to search
        cities_to_search = [city] if city else list(self._stops_by_city.keys())

        for city_name in cities_to_search:
            stops = self._stops_by_city.get(city_name, [])

            for stop in stops:
                # Filter by real-time availability if requested
                if realtime_only and not stop.get("hasRealtime", False):
                    continue

                # Match by stop name or TPC code
                stop_name = stop.get("name", "")
                stop_name_lower = stop_name.lower()
                stop_tpc = stop.get("tpc", "")

                if query_lower in stop_name_lower or query_lower in stop_tpc:
                    # Group by city and stop name
                    key = (city_name, stop_name)
                    if key not in grouped_stops:
                        grouped_stops[key] = []
                    
                    grouped_stops[key].append(stop)

        # Convert grouped stops to results
        results = []
        for (city_name, stop_name), stops in grouped_stops.items():
            # Collect all stop codes and lines for this location
            stop_codes = []
            all_lines = set()
            
            for stop in stops:
                stop_tpc = stop.get("tpc", "")
                stop_codes.append(stop_tpc)
                
                # Get lines for this stop code
                lines = self._lines_by_stop.get(stop_tpc, [])
                for line in lines:
                    all_lines.add(str(line.get("number", "?")))
            
            # Use coordinates from first stop (they should be similar)
            first_stop = stops[0]
            
            results.append({
                "stop_codes": stop_codes,
                "stop_name": stop_name,
                "city": city_name,
                "area": first_stop.get("area"),
                "hasRealtime": first_stop.get("hasRealtime", False),
                "routes": ", ".join(sorted(all_lines)[:5]),  # Show first 5 lines
                "direction_count": len(stop_codes),
                "lat": first_stop.get("lat"),
                "lon": first_stop.get("lon"),
            })
            
            if len(results) >= limit:
                break

        return results

    async def search_by_city(self, city_name: str, realtime_only: bool = True) -> list[dict[str, Any]]:
        """
        Get all stops in a specific city.

        Args:
            city_name: Name of the city
            realtime_only: Only return stops with real-time data

        Returns:
            List of stop dictionaries grouped by location (stop name)
        """
        await self._load_data()

        if not self._stops_by_city:
            return []

        stops = self._stops_by_city.get(city_name, [])
        grouped_stops = {}  # Map stop_name -> list of stop data

        for stop in stops:
            # Filter by real-time availability if requested
            if realtime_only and not stop.get("hasRealtime", False):
                continue

            stop_name = stop.get("name", "")
            if stop_name not in grouped_stops:
                grouped_stops[stop_name] = []
            
            grouped_stops[stop_name].append(stop)

        # Convert grouped stops to results
        results = []
        for stop_name, stops in grouped_stops.items():
            # Collect all stop codes and lines for this location
            stop_codes = []
            all_lines = set()
            
            for stop in stops:
                stop_tpc = stop.get("tpc", "")
                stop_codes.append(stop_tpc)
                
                # Get lines for this stop code
                lines = self._lines_by_stop.get(stop_tpc, [])
                for line in lines:
                    all_lines.add(str(line.get("number", "?")))
            
            # Use coordinates from first stop
            first_stop = stops[0]
            
            results.append({
                "stop_codes": stop_codes,
                "stop_name": stop_name,
                "city": city_name,
                "area": first_stop.get("area"),
                "hasRealtime": first_stop.get("hasRealtime", False),
                "routes": ", ".join(sorted(all_lines)[:5]),  # Show first 5 lines
                "direction_count": len(stop_codes),
                "lat": first_stop.get("lat"),
                "lon": first_stop.get("lon"),
            })

        return sorted(results, key=lambda x: x["stop_name"])
