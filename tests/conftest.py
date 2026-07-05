"""Common fixtures for OVAPI tests."""
from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.core import HomeAssistant

from custom_components.ovapi.const import CONF_STOP_CODE, DOMAIN


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations."""
    yield


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Override async_setup_entry."""
    with patch(
        "custom_components.ovapi.async_setup_entry", return_value=True
    ) as mock_setup_entry:
        yield mock_setup_entry


@pytest.fixture
def mock_ovapi_client():
    """Mock OVAPIClient."""
    with patch(
        "custom_components.ovapi.api.OVAPIClient", autospec=True
    ) as mock_client:
        client = mock_client.return_value
        client.get_stop_info = AsyncMock(return_value={
            "31000495": {
                "BUS": {
                    "GVB": {
                        "22": {
                            "Passes": {
                                "0": {
                                    "LinePublicNumber": "22",
                                    "DestinationName50": "Centraal Station",
                                    "ExpectedArrivalTime": "2025-12-01T14:30:00",
                                    "TargetArrivalTime": "2025-12-01T14:28:00",
                                    "TransportType": "BUS",
                                }
                            }
                        }
                    }
                }
            }
        })
        client.filter_passes = lambda data, **kwargs: [
            {
                "line_number": "22",
                "destination": "Centraal Station",
                "expected_arrival": "2025-12-01T14:30:00",
                "target_arrival": "2025-12-01T14:28:00",
                "delay": 2,
                "transport_type": "BUS",
                "data_owner_code": "GVB",
                "line_planning_number": "22",
                "journey_number": "12345",
                "operation_date": "2025-12-01",
            }
        ]
        client.get_time_until_departure = lambda dt: 10 if dt else None
        yield client


@pytest.fixture
def mock_kv6_manager():
    """Mock KV6LiveTracker.

    Patched at its definition site (custom_components.ovapi.kv6), matching
    the mock_gtfs_handler pattern above — both classes are lazily imported
    inside functions rather than at module load time, so patching
    "custom_components.ovapi.kv6.KV6LiveTracker" is what actually intercepts
    the `from .kv6 import KV6LiveTracker` call in async_setup_entry.
    """
    with patch(
        "custom_components.ovapi.kv6.KV6LiveTracker", autospec=True
    ) as mock_tracker_cls:
        tracker = mock_tracker_cls.return_value
        tracker.async_stop = AsyncMock(return_value=None)
        tracker.get_position.return_value = None
        yield tracker


@pytest.fixture
def mock_gtfs_handler():
    """Mock GTFSDataHandler."""
    with patch(
        "custom_components.ovapi.gtfs.GTFSDataHandler", autospec=True
    ) as mock_handler:
        handler = mock_handler.return_value
        # Return grouped format (new behavior)
        handler.search_stops = AsyncMock(return_value=[
            {
                "stop_name": "Amsterdam, Centraal Station",
                "stop_codes": ["31000495"],
                "stop_lat": "52.378624",
                "stop_lon": "4.900272",
                "direction_count": 1,
            }
        ])
        handler.get_stop_name = AsyncMock(return_value="Amsterdam, Centraal Station")
        yield handler
