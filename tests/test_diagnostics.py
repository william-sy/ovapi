"""Test OVAPI diagnostics."""
from homeassistant.core import HomeAssistant

from custom_components.ovapi.diagnostics import async_get_config_entry_diagnostics


async def test_diagnostics(hass: HomeAssistant, mock_ovapi_client) -> None:
    """Test diagnostics."""
    entry = MockConfigEntry(
        domain="ovapi",
        data={"stop_code": "31000495"},
    )

    # Mock coordinator
    entry.runtime_data = MockCoordinator()

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["entry"]["data"]["stop_code"] == "31000495"
    assert diagnostics["coordinator"]["stop_code"] == "31000495"
    assert "passes_count" in diagnostics["data"]


class MockConfigEntry:
    """Mock config entry."""

    def __init__(self, **kwargs):
        """Initialize."""
        self.domain = kwargs.get("domain")
        self.data = kwargs.get("data", {})
        self.title = "Test Stop"
        self.runtime_data = None


class MockCoordinator:
    """Mock coordinator."""

    def __init__(self):
        """Initialize."""
        self.stop_code = "31000495"
        self.line_number = None
        self.destination = None
        self.last_update_success = True
        self.update_interval = "0:00:30"
        self.data = []
