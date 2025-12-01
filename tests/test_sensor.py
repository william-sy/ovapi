"""Test OVAPI sensors."""
from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.ovapi.const import CONF_STOP_CODE, DOMAIN


async def test_sensors(
    hass: HomeAssistant, mock_ovapi_client
) -> None:
    """Test sensor creation."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_STOP_CODE: "31000495",
            "walking_time": 5,
        },
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.ovapi.OVAPIClient",
        return_value=mock_ovapi_client,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    # Check that sensors are created
    state = hass.states.get("sensor.bus_stop_31000495_current_bus")
    assert state is not None
    assert state.state == "22 → Centraal Station"

    state = hass.states.get("sensor.bus_stop_31000495_current_departure")
    assert state is not None

    state = hass.states.get("sensor.bus_stop_31000495_time_to_leave")
    assert state is not None


async def test_sensor_unavailable(
    hass: HomeAssistant, mock_ovapi_client
) -> None:
    """Test sensor unavailable state."""
    mock_ovapi_client.get_stop_info.side_effect = Exception("Connection error")

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_STOP_CODE: "31000495"},
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.ovapi.OVAPIClient",
        return_value=mock_ovapi_client,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    state = hass.states.get("sensor.bus_stop_31000495_current_bus")
    assert state is None or state.state == "unavailable"


class MockConfigEntry:
    """Mock config entry."""

    def __init__(self, **kwargs):
        """Initialize."""
        self.domain = kwargs.get("domain")
        self.data = kwargs.get("data", {})
        self.options = kwargs.get("options", {})
        self.entry_id = "test"

    def add_to_hass(self, hass):
        """Add to hass."""
        pass
