"""Config flow for OVAPI integration."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import selector

from .api import OVAPIClient
from .const import (
    CONF_DESTINATION,
    CONF_LINE_NUMBER,
    CONF_SCAN_INTERVAL,
    CONF_STOP_CODE,
    CONF_STOP_CODES,
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
    from .gtfs import GTFSDataHandler  # Lazy import to avoid blocking
    
    session = async_get_clientsession(hass)
    client = OVAPIClient(session)
    cache_dir = Path(hass.config.path(DOMAIN))
    gtfs_handler = GTFSDataHandler(session, cache_dir)

    # Get stop codes to validate (could be one or multiple)
    stop_codes_to_check = data.get(CONF_STOP_CODES, [data[CONF_STOP_CODE]])
    
    # Try to fetch data for at least one stop code
    valid_stop_found = False
    last_error = None
    
    for stop_code in stop_codes_to_check:
        try:
            stop_data = await client.get_stop_info(stop_code)
            
            if stop_data:
                # Check if we got valid data
                for key, value in stop_data.items():
                    if key != "stopareacode" and isinstance(value, dict):
                        valid_stop_found = True
                        break
            
            if valid_stop_found:
                break
        except Exception as err:
            last_error = err
            _LOGGER.debug("Stop code %s validation failed: %s", stop_code, err)
            continue
    
    if not valid_stop_found:
        if len(stop_codes_to_check) > 1:
            _LOGGER.warning(
                "None of the stop codes (%s) have real-time data available", 
                ", ".join(stop_codes_to_check)
            )
            raise ValueError(
                f"None of the selected stops have real-time departure data. "
                f"Stop codes: {', '.join(stop_codes_to_check)}"
            )
        else:
            raise ValueError(f"Stop code {stop_codes_to_check[0]} has no real-time data available")

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

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return OVAPIOptionsFlow(config_entry)

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
        from .gtfs import GTFSDataHandler  # Lazy import to avoid blocking
        
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                session = async_get_clientsession(self.hass)
                cache_dir = Path(self.hass.config.path(DOMAIN))
                gtfs_handler = GTFSDataHandler(session, cache_dir)
                
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
            # Find the selected stop from results
            selected_label = user_input["stop"]
            results = self.context.get("search_results", [])
            
            for stop in results:
                label = self._build_stop_label(stop)
                if label == selected_label:
                    # Store the selected stop info
                    self.context["selected_stop"] = stop
                    
                    # If stop has multiple directions, ask which to use
                    if stop.get("direction_count", 1) > 1:
                        return await self.async_step_select_direction()
                    else:
                        # Single stop code, go straight to configure
                        self.context["stop_code"] = stop["stop_codes"][0]
                        return await self.async_step_configure()
            
            # Fallback if not found
            return self.async_abort(reason="stop_not_found")

        # Build options from search results
        results = self.context.get("search_results", [])
        options = {}
        for stop in results:
            label = self._build_stop_label(stop)
            options[label] = label

        return self.async_show_form(
            step_id="select_stop",
            data_schema=vol.Schema(
                {
                    vol.Required("stop"): vol.In(options),
                }
            ),
        )
    
    def _build_stop_label(self, stop: dict[str, Any]) -> str:
        """Build a display label for a stop."""
        if stop.get("direction_count", 1) > 1:
            label = f"{stop['stop_name']} ({stop['direction_count']} directions)"
        else:
            label = f"{stop['stop_codes'][0]} - {stop['stop_name']}"
        
        if stop.get("routes"):
            label += f" (Lines: {stop['routes']})"
        
        return label
    
    async def async_step_select_direction(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle direction selection for stops with multiple platforms."""
        if user_input is not None:
            direction_choice = user_input["direction"]
            selected_stop = self.context.get("selected_stop", {})
            stop_codes = selected_stop.get("stop_codes", [])
            
            if direction_choice == "both":
                # Use all stop codes
                self.context["stop_codes"] = stop_codes
                # Force "All destinations" when using both directions
                # since opposite directions go to different places
                self.context["force_all_destinations"] = True
            else:
                # Extract the index from "Direction 1", "Direction 2", etc.
                direction_num = int(direction_choice.split(" ")[1]) - 1
                if 0 <= direction_num < len(stop_codes):
                    self.context["stop_code"] = stop_codes[direction_num]
            
            return await self.async_step_configure()
        
        # Build direction options
        selected_stop = self.context.get("selected_stop", {})
        stop_codes = selected_stop.get("stop_codes", [])
        
        options = {"both": "Both directions (combined - shows next bus from any direction)"}
        for idx, stop_code in enumerate(stop_codes, 1):
            options[f"Direction {idx}"] = f"Direction {idx} only (Stop: {stop_code})"
        
        return self.async_show_form(
            step_id="select_direction",
            data_schema=vol.Schema(
                {
                    vol.Required("direction"): vol.In(options),
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
            return await self.async_step_configure()

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
        """Handle the configuration step - select line number."""
        errors: dict[str, str] = {}
        stop_code = self.context.get("stop_code")
        stop_codes = self.context.get("stop_codes")

        if user_input is not None:
            # Store line number selection and move to filter step
            self.context["line_number"] = user_input.get(CONF_LINE_NUMBER)
            return await self.async_step_filter()

        # Fetch available line numbers for this stop (or first stop if multiple)
        lines = await self._get_lines_for_stop(stop_code or (stop_codes[0] if stop_codes else None))
        
        # Build schema with line number dropdown if available
        schema_dict: dict[Any, Any] = {}
        
        if lines:
            # Add "All lines" option
            line_options = ["All lines"] + lines
            schema_dict[vol.Optional(CONF_LINE_NUMBER, default="All lines")] = selector.SelectSelector(
                selector.SelectSelectorConfig(options=line_options, mode=selector.SelectSelectorMode.DROPDOWN)
            )
        else:
            schema_dict[vol.Optional(CONF_LINE_NUMBER)] = str
        
        data_schema = vol.Schema(schema_dict)
        
        # Build description
        if stop_codes:
            stop_desc = f"{', '.join(stop_codes)} (both directions)"
        else:
            stop_desc = stop_code

        return self.async_show_form(
            step_id="configure",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={"stop_code": stop_desc},
        )

    async def async_step_filter(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the filter step - select destination and timing."""
        errors: dict[str, str] = {}
        stop_code = self.context.get("stop_code")
        stop_codes = self.context.get("stop_codes")
        line_number = self.context.get("line_number")
        force_all_destinations = self.context.get("force_all_destinations", False)
        
        # Convert "All lines" to None
        if line_number == "All lines":
            line_number = None

        if user_input is not None:
            # Remove walking_time if it's 0 (disabled)
            if user_input.get(CONF_WALKING_TIME, 0) == 0:
                user_input.pop(CONF_WALKING_TIME, None)
            
            # Build final configuration
            full_config = {}
            
            # Use stop_codes if available (bidirectional), otherwise single stop_code
            if stop_codes:
                full_config[CONF_STOP_CODES] = stop_codes
                full_config[CONF_STOP_CODE] = stop_codes[0]  # For backward compatibility
                # Force "All destinations" for bidirectional to show all buses
                user_input[CONF_DESTINATION] = "All destinations"
            else:
                full_config[CONF_STOP_CODE] = stop_code
                
            if line_number:
                full_config[CONF_LINE_NUMBER] = line_number
            full_config.update(user_input)
            
            try:
                info = await validate_input(self.hass, full_config)
            except ValueError as err:
                _LOGGER.error("Validation failed: %s", err)
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                # Create a unique ID based on stop code(s) and line number
                if stop_codes:
                    unique_id = f"{'_'.join(stop_codes)}_{line_number or 'all'}"
                else:
                    unique_id = f"{stop_code}_{line_number or 'all'}"
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=info["title"],
                    data=full_config,
                )

        # Build schema
        schema_dict: dict[Any, Any] = {}
        
        # Only show destination selection if NOT using both directions
        # (both directions always shows all destinations since they go opposite ways)
        if not force_all_destinations:
            # Fetch available destinations for this stop and line (use first stop if multiple)
            destinations = await self._get_destinations_for_stop(
                stop_code or (stop_codes[0] if stop_codes else None), 
                line_number
            )
            
            if destinations:
                # Add "All destinations" option
                dest_options = ["All destinations"] + destinations
                schema_dict[vol.Optional(CONF_DESTINATION, default="All destinations")] = selector.SelectSelector(
                    selector.SelectSelectorConfig(options=dest_options, mode=selector.SelectSelectorMode.DROPDOWN)
                )
            else:
                schema_dict[vol.Optional(CONF_DESTINATION)] = str
        
        schema_dict.update({
            vol.Optional(CONF_WALKING_TIME, default=0): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=60, step=1, mode=selector.NumberSelectorMode.BOX,
                    unit_of_measurement="minutes"
                )
            ),
            vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL, step=1,
                    mode=selector.NumberSelectorMode.BOX, unit_of_measurement="seconds"
                )
            ),
        })
        
        data_schema = vol.Schema(schema_dict)
        
        # Build description for placeholders
        if stop_codes:
            stop_desc = f"{', '.join(stop_codes)} (both directions)"
        else:
            stop_desc = stop_code
        
        placeholders = {"stop_code": stop_desc}
        if line_number:
            placeholders["line_number"] = line_number

        return self.async_show_form(
            step_id="filter",
            data_schema=data_schema,
            errors=errors,
            description_placeholders=placeholders,
        )

    async def _get_lines_for_stop(self, stop_code: str) -> list[str]:
        """Get available line numbers for a stop."""
        try:
            session = async_get_clientsession(self.hass)
            client = OVAPIClient(session)
            stop_data = await client.get_stop_info(stop_code)
            
            lines = set()
            
            # Extract all unique line numbers from the stop data
            for stop_key, stop_info in stop_data.items():
                if not isinstance(stop_info, dict):
                    continue
                    
                if "Passes" in stop_info:
                    for pass_data in stop_info["Passes"].values():
                        line = pass_data.get("LinePublicNumber")
                        if line:
                            lines.add(line)
            
            return sorted(list(lines))
        except Exception as err:
            _LOGGER.debug("Could not fetch line numbers: %s", err)
            return []

    async def _get_destinations_for_stop(self, stop_code: str, line_number: str | None = None) -> list[str]:
        """Get available destinations for a stop, optionally filtered by line."""
        try:
            session = async_get_clientsession(self.hass)
            client = OVAPIClient(session)
            stop_data = await client.get_stop_info(stop_code)
            
            destinations = set()
            
            # Extract unique destinations from the stop data
            for stop_key, stop_info in stop_data.items():
                if not isinstance(stop_info, dict):
                    continue
                    
                if "Passes" in stop_info:
                    for pass_data in stop_info["Passes"].values():
                        # Filter by line if specified
                        if line_number:
                            pass_line = pass_data.get("LinePublicNumber")
                            if pass_line != line_number:
                                continue
                        
                        dest = pass_data.get("DestinationName50")
                        if dest:
                            destinations.add(dest)
            
            return sorted(list(destinations))
        except Exception as err:
            _LOGGER.debug("Could not fetch destinations: %s", err)
            return []

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
                    default=entry.data.get(CONF_WALKING_TIME, 0)
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0, max=60, step=1, mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="minutes"
                    )
                ),
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL, step=1,
                        mode=selector.NumberSelectorMode.BOX, unit_of_measurement="seconds"
                    )
                ),
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


class OVAPIOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for OVAPI."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            # Update the config entry data
            new_data = {**self.config_entry.data, **user_input}
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data=new_data,
            )
            # Reload the integration to apply changes
            await self.hass.config_entries.async_reload(self.config_entry.entry_id)
            return self.async_create_entry(title="", data={})

        data_schema = vol.Schema(
            {
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=self.config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=MIN_SCAN_INTERVAL, 
                        max=MAX_SCAN_INTERVAL, 
                        step=1,
                        mode=selector.NumberSelectorMode.BOX, 
                        unit_of_measurement="seconds"
                    )
                ),
                vol.Optional(
                    CONF_WALKING_TIME,
                    default=self.config_entry.data.get(CONF_WALKING_TIME, 0)
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0, 
                        max=60, 
                        step=1, 
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="minutes"
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=data_schema,
        )
