"""Test OVAPI diagnostics."""
from datetime import timedelta
from unittest.mock import Mock

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ovapi.diagnostics import async_get_config_entry_diagnostics


async def test_diagnostics(hass: HomeAssistant, mock_ovapi_client) -> None:
    """Test diagnostics."""
    entry = MockConfigEntry(
        domain="ovapi",
        data={"stop_code": "31000495"},
    )

    # Mock coordinator
    mock_coordinator = Mock()
    mock_coordinator.stop_code = "31000495"
    mock_coordinator.line_number = None
    mock_coordinator.destination = None
    mock_coordinator.last_update_success = True
    mock_coordinator.update_interval = timedelta(seconds=30)
    mock_coordinator.data = []
    
    entry.runtime_data = mock_coordinator

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["entry"]["data"]["stop_code"] == "31000495"
    assert diagnostics["coordinator"]["stop_code"] == "31000495"
    assert "passes_count" in diagnostics["data"]
