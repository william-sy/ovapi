"""Test OVAPI sensors."""
from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

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
    state = hass.states.get("sensor.bus_stop_31000495_current_vehicle")
    assert state is not None
    assert state.state == "22 → Centraal Station"

    state = hass.states.get("sensor.bus_stop_31000495_current_vehicle_departure")
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
        # Setup should fail and retry
        assert not await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    # No sensors should be created when setup fails
    state = hass.states.get("sensor.bus_stop_31000495_current_vehicle")
    assert state is None
