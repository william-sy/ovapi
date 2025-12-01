"""Test the OVAPI integration init."""
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from custom_components.ovapi.const import CONF_STOP_CODE, DOMAIN


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


class MockConfigEntry:
    """Mock config entry."""

    def __init__(self, **kwargs):
        """Initialize."""
        self.domain = kwargs.get("domain")
        self.data = kwargs.get("data", {})
        self.options = kwargs.get("options", {})
        self.entry_id = "test"
        self.state = ConfigEntryState.NOT_LOADED
        self.runtime_data = None

    def add_to_hass(self, hass):
        """Add to hass."""
        pass
