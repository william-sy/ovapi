"""Test OVAPI device trackers (live vehicle GPS, opt-in)."""
from unittest.mock import patch

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ovapi.const import CONF_ENABLE_LIVE_TRACKING, CONF_STOP_CODE, DOMAIN
from custom_components.ovapi.kv6 import KV6VehiclePosition

_CURRENT_TRACKER = "device_tracker.bus_stop_31000495_current_vehicle_location"


async def test_no_trackers_when_live_tracking_disabled(
    hass: HomeAssistant, mock_ovapi_client
) -> None:
    """Live tracking off (the default) means no device_tracker entities at all."""
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

    assert hass.states.get(_CURRENT_TRACKER) is None


async def test_tracker_state_unknown_without_gps_fix(
    hass: HomeAssistant, mock_ovapi_client, mock_kv6_manager
) -> None:
    """No live GPS match yet is a normal 'unknown' state, not 'unavailable'."""
    mock_kv6_manager.get_position.return_value = None

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_STOP_CODE: "31000495", CONF_ENABLE_LIVE_TRACKING: True},
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.ovapi.OVAPIClient",
        return_value=mock_ovapi_client,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    state = hass.states.get(_CURRENT_TRACKER)
    assert state is not None
    assert state.state == "unknown"
    assert state.attributes.get("latitude") is None


async def test_tracker_reports_position_when_gps_fix_available(
    hass: HomeAssistant, mock_ovapi_client, mock_kv6_manager
) -> None:
    """A matched live GPS fix surfaces as the tracker's lat/lon and attributes."""
    mock_kv6_manager.get_position.return_value = KV6VehiclePosition(
        data_owner_code="GVB",
        line_planning_number="22",
        journey_number="12345",
        operation_date="2025-12-01",
        latitude=52.378624,
        longitude=4.900272,
        punctuality=42,
        vehicle_number="1234",
        omloop_number="56",
        message_type="ONROUTE",
        timestamp=0.0,
    )

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_STOP_CODE: "31000495", CONF_ENABLE_LIVE_TRACKING: True},
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.ovapi.OVAPIClient",
        return_value=mock_ovapi_client,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    state = hass.states.get(_CURRENT_TRACKER)
    assert state is not None
    assert state.attributes["latitude"] == 52.378624
    assert state.attributes["longitude"] == 4.900272
    assert state.attributes["vehicle_number"] == "1234"
    assert state.attributes["omloop_number"] == "56"
    assert state.attributes["punctuality_seconds"] == 42
