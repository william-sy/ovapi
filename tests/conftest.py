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
            }
        ]
        client.get_time_until_departure = lambda dt: 10 if dt else None
        yield client


@pytest.fixture
def mock_gtfs_handler():
    """Mock GTFSDataHandler."""
    with patch(
        "custom_components.ovapi.gtfs.GTFSDataHandler", autospec=True
    ) as mock_handler:
        handler = mock_handler.return_value
        handler.search_stops = AsyncMock(return_value=[
            {
                "stop_code": "31000495",
                "stop_name": "Amsterdam, Centraal Station",
                "stop_lat": "52.378624",
                "stop_lon": "4.900272",
            }
        ])
        handler.get_stop_name = AsyncMock(return_value="Amsterdam, Centraal Station")
        yield handler
