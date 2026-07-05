"""Test the OVAPI integration init."""
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ovapi.const import CONF_ENABLE_LIVE_TRACKING, CONF_STOP_CODE, DOMAIN


async def test_setup_entry(
    hass: HomeAssistant, mock_ovapi_client
) -> None:
    """Test setting up integration."""
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

    assert entry.state == ConfigEntryState.LOADED
    assert entry.runtime_data is not None


async def test_unload_entry(
    hass: HomeAssistant, mock_ovapi_client
) -> None:
    """Test unloading integration."""
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

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state == ConfigEntryState.NOT_LOADED


async def test_setup_entry_without_live_tracking_only_forwards_sensor(
    hass: HomeAssistant, mock_ovapi_client
) -> None:
    """Live tracking off (the default) forwards only the sensor platform."""
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

    assert entry.runtime_data.kv6_manager is None
    assert entry.runtime_data.platforms == [Platform.SENSOR]

    # Unload must not choke on kv6_manager being None.
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state == ConfigEntryState.NOT_LOADED


async def test_setup_entry_with_live_tracking_starts_and_stops_kv6_manager(
    hass: HomeAssistant, mock_ovapi_client, mock_kv6_manager
) -> None:
    """Live tracking on starts the KV6 manager at setup, stops it at unload."""
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

    assert entry.runtime_data.kv6_manager is mock_kv6_manager
    assert entry.runtime_data.platforms == [Platform.SENSOR, Platform.DEVICE_TRACKER]
    mock_kv6_manager.start.assert_called_once()
    # The coordinator's first refresh already happened during setup, so the
    # subscription feed (DataOwnerCode from the mocked passes) should have run.
    mock_kv6_manager.update_subscriptions.assert_called_with({"GVB"})

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    mock_kv6_manager.async_stop.assert_awaited_once()
