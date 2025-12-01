"""Config flow for OVAPI integration."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import OVAPIClient
from .gtfs import GTFSDataHandler
from .const import (
    CONF_DESTINATION,
    CONF_LINE_NUMBER,
    CONF_SCAN_INTERVAL,
    CONF_STOP_CODE,
    CONF_WALKING_TIME,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_WALKING_TIME,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
    session = async_get_clientsession(hass)
    client = OVAPIClient(session)
    gtfs_handler = GTFSDataHandler(session)

    # Try to fetch data for the stop code
    stop_data = await client.get_stop_info(data[CONF_STOP_CODE])
    
    if not stop_data:
        raise ValueError("Could not fetch data for stop code")
    
    # Check if we got valid data
    has_data = False
    for key, value in stop_data.items():
        if key != "stopareacode" and isinstance(value, dict):
            has_data = True
            break
    
    if not has_data:
        raise ValueError("No transit data found for this stop code")

    # Try to get the stop name from GTFS data
    stop_name = None
    try:
        stop_name = await gtfs_handler.get_stop_name(data[CONF_STOP_CODE])
    except Exception:
        _LOGGER.debug("Could not fetch stop name from GTFS data")
    
    title = f"{stop_name}" if stop_name else f"Bus Stop {data[CONF_STOP_CODE]}"
    return {"title": title}


class OVAPIConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for OVAPI."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step - choose between search or manual entry."""
        if user_input is not None:
            if user_input.get("method") == "search":
                return await self.async_step_search()
            return await self.async_step_manual()

        return self.async_show_menu(
            step_id="user",
            menu_options=["search", "manual"],
        )

    async def async_step_search(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the search step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                session = async_get_clientsession(self.hass)
                gtfs_handler = GTFSDataHandler(session)
                
                results = await gtfs_handler.search_stops(
                    user_input["search_query"], limit=20
                )
                
                if not results:
                    errors["base"] = "no_stops_found"
                else:
                    # Store search results for the next step
                    self.context["search_results"] = results
                    return await self.async_step_select_stop()
                    
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception during search")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="search",
            data_schema=vol.Schema(
                {
                    vol.Required("search_query"): str,
                }
            ),
            errors=errors,
        )

    async def async_step_select_stop(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle stop selection from search results."""
        if user_input is not None:
            # Extract stop code from selection
            selected = user_input["stop"]
            stop_code = selected.split(" - ")[0]
            
            # Store the selected stop code and move to configuration
            self.context["stop_code"] = stop_code
            return await self.async_step_configure()

        # Build options from search results
        results = self.context.get("search_results", [])
        options = {
            f"{stop['stop_code']} - {stop['stop_name']}": f"{stop['stop_code']} - {stop['stop_name']}"
            for stop in results
        }

        return self.async_show_form(
            step_id="select_stop",
            data_schema=vol.Schema(
                {
                    vol.Required("stop"): vol.In(options),
                }
            ),
        )

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle manual entry step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self.context["stop_code"] = user_input[CONF_STOP_CODE]
            self.context["manual_config"] = user_input
            return await self.async_step_configure(user_input)

        data_schema = vol.Schema(
            {
                vol.Required(CONF_STOP_CODE): str,
            }
        )

        return self.async_show_form(
            step_id="manual",
            data_schema=data_schema,
            errors=errors,
        )

    async def async_step_configure(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the configuration step."""
        errors: dict[str, str] = {}
        stop_code = self.context.get("stop_code")

        if user_input is not None:
            # Merge stop code with configuration
            full_config = {CONF_STOP_CODE: stop_code, **user_input}
            
            try:
                info = await validate_input(self.hass, full_config)
            except ValueError:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                # Create a unique ID based on stop code and line number
                unique_id = f"{stop_code}_{user_input.get(CONF_LINE_NUMBER, 'all')}"
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=info["title"],
                    data=full_config,
                )

        data_schema = vol.Schema(
            {
                vol.Optional(CONF_LINE_NUMBER): str,
                vol.Optional(CONF_DESTINATION): str,
                vol.Optional(CONF_WALKING_TIME, default=DEFAULT_WALKING_TIME): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=60)
                ),
                vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
                    vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL)
                ),
            }
        )

        return self.async_show_form(
            step_id="configure",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={"stop_code": stop_code},
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle reconfiguration of the integration."""
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        assert entry is not None

        if user_input is not None:
            # Merge with existing data
            new_data = {**entry.data, **user_input}
            
            try:
                await validate_input(self.hass, new_data)
            except ValueError:
                return self.async_abort(reason="cannot_connect")
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception during reconfigure")
                return self.async_abort(reason="unknown")

            return self.async_update_reload_and_abort(
                entry,
                data=new_data,
            )

        stop_code = entry.data[CONF_STOP_CODE]
        
        data_schema = vol.Schema(
            {
                vol.Optional(
                    CONF_LINE_NUMBER,
                    default=entry.data.get(CONF_LINE_NUMBER, "")
                ): str,
                vol.Optional(
                    CONF_DESTINATION,
                    default=entry.data.get(CONF_DESTINATION, "")
                ): str,
                vol.Optional(
                    CONF_WALKING_TIME,
                    default=entry.data.get(CONF_WALKING_TIME, DEFAULT_WALKING_TIME)
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=60)),
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
                ): vol.All(vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL)),
            }
        )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=data_schema,
            description_placeholders={"stop_code": stop_code},
        )

    async def async_step_import(self, import_data: dict[str, Any]) -> FlowResult:
        """Handle import from configuration.yaml."""
        self.context["stop_code"] = import_data[CONF_STOP_CODE]
        return await self.async_step_configure(import_data)
