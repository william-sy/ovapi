"""Test the OVAPI config flow."""
from unittest.mock import AsyncMock

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ovapi.const import (
    CONF_DESTINATION,
    CONF_LINE_NUMBER,
    CONF_SCAN_INTERVAL,
    CONF_STOP_CODE,
    CONF_WALKING_TIME,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_WALKING_TIME,
    DOMAIN,
)


async def test_form_manual_entry(
    hass: HomeAssistant, mock_ovapi_client, mock_gtfs_handler
) -> None:
    """Test we get the form for manual entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.MENU
    assert result["step_id"] == "user"

    # Select manual entry
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"next_step_id": "manual"},
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "manual"

    # Enter stop code
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_STOP_CODE: "31000495"},
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "configure"

    # Configure line number
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_LINE_NUMBER: "All lines"},
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "filter"

    # Configure destination, walking time and scan interval
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_DESTINATION: "All destinations",
            CONF_WALKING_TIME: 5,
            CONF_SCAN_INTERVAL: 60,
        },
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Amsterdam, Centraal Station"
    assert result["data"][CONF_STOP_CODE] == "31000495"
    assert result["data"][CONF_WALKING_TIME] == 5
    assert result["data"][CONF_SCAN_INTERVAL] == 60


async def test_form_search(
    hass: HomeAssistant, mock_ovapi_client, mock_gtfs_handler
) -> None:
    """Test search flow."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    # Select search
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"next_step_id": "search"},
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "search"

    # Search for stop
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"search_query": "Amsterdam"},
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "select_stop"

    # Select stop
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"stop": "31000495 - Amsterdam, Centraal Station"},
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "configure"


async def test_form_cannot_connect(
    hass: HomeAssistant, mock_ovapi_client, mock_gtfs_handler
) -> None:
    """Test we handle cannot connect error."""
    from unittest.mock import patch
    
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"next_step_id": "manual"},
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_STOP_CODE: "31000495"},
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "configure"
    
    # Select line
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_LINE_NUMBER: "All lines"},
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "filter"
    
    # Patch to return empty data which should trigger validation error
    with patch("custom_components.ovapi.config_flow.OVAPIClient") as mock_client:
        mock_instance = mock_client.return_value
        mock_instance.get_stop_info = AsyncMock(return_value={})
        
        # Error should appear at filter step when trying to create entry
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_WALKING_TIME: 5},
        )
        assert result["type"] == FlowResultType.FORM
        assert result["errors"] == {"base": "cannot_connect"}


async def test_form_no_stops_found(
    hass: HomeAssistant, mock_ovapi_client, mock_gtfs_handler
) -> None:
    """Test no stops found in search."""
    mock_gtfs_handler.search_stops = AsyncMock(return_value=[])

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"next_step_id": "search"},
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"search_query": "Nonexistent"},
    )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "no_stops_found"}


async def test_reconfigure(
    hass: HomeAssistant, mock_ovapi_client, mock_gtfs_handler
) -> None:
    """Test reconfiguration flow."""
    # Create entry first
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_STOP_CODE: "31000495",
            CONF_WALKING_TIME: 5,
            CONF_SCAN_INTERVAL: 60,
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "reconfigure", "entry_id": entry.entry_id},
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_LINE_NUMBER: "22",
            CONF_WALKING_TIME: 10,
            CONF_SCAN_INTERVAL: 60,
        },
    )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
