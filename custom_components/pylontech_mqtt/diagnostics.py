"""Diagnostics support for the Pylontech MQTT integration."""

from typing import Any

# async_redact_data's own overloaded signature resolves to a partially
# unknown type in this HA version's stubs (a gap upstream, not here).
from homeassistant.components.diagnostics import (
    async_redact_data,  # pyright: ignore[reportUnknownVariableType]
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import PylontechCoordinator

# Values that are secrets or identify a specific physical device — redacted
# so diagnostics can be shared publicly (e.g. bug reports).
TO_REDACT = {"mqtt_pass", "barcode"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator: PylontechCoordinator = hass.data[DOMAIN][entry.entry_id]

    return {
        "entry_data": async_redact_data(dict(entry.data), TO_REDACT),
        "entry_options": async_redact_data(dict(entry.options), TO_REDACT),
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "default_capacity": coordinator.default_capacity,
            "battery_capacities": coordinator.battery_capacities,
            "data": async_redact_data(coordinator.data, TO_REDACT)
            if coordinator.data
            else None,
        },
    }
