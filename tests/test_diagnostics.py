"""Tests for the Pylontech MQTT diagnostics platform."""

import pytest
from conftest import make_coordinator
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pylontech_mqtt.const import DOMAIN
from custom_components.pylontech_mqtt.coordinator import PylontechCoordinator
from custom_components.pylontech_mqtt.diagnostics import (
    async_get_config_entry_diagnostics,
)

_PAYLOAD: dict = {
    "voltage": 51.2,
    "current": 10.0,
    "soc": 80.0,
    "power": 512.0,
    "energy_in": 10.5,
    "energy_out": 5.2,
    "spec": "48V/100AH",
    "manufacturer": "Pylon",
    "model": "US5KBPL",
    "barcode": "PPTBH02400710243",
    "batteries": [],
}


_ENTRY_DATA: dict = {
    "mqtt_host": "localhost",
    "mqtt_port": 1883,
    "mqtt_user": "",
    "mqtt_pass": "super-secret",
    "mqtt_topic": "pylontech/stack",
}


@pytest.fixture
def entry(hass: HomeAssistant, coordinator: PylontechCoordinator) -> MockConfigEntry:
    mock_entry = MockConfigEntry(domain=DOMAIN, data=_ENTRY_DATA)
    mock_entry.add_to_hass(hass)
    hass.data.setdefault(DOMAIN, {})[mock_entry.entry_id] = coordinator
    return mock_entry


@pytest.fixture
async def coordinator(hass: HomeAssistant) -> PylontechCoordinator:
    return make_coordinator(hass)


class TestDiagnostics:
    async def test_includes_entry_data(
        self, hass: HomeAssistant, entry: MockConfigEntry
    ) -> None:
        diag = await async_get_config_entry_diagnostics(hass, entry)
        assert diag["entry_data"]["mqtt_host"] == "localhost"
        assert diag["entry_data"]["mqtt_topic"] == "pylontech/stack"

    async def test_password_redacted(
        self, hass: HomeAssistant, entry: MockConfigEntry
    ) -> None:
        diag = await async_get_config_entry_diagnostics(hass, entry)
        assert diag["entry_data"]["mqtt_pass"] == "**REDACTED**"

    async def test_coordinator_data_none_before_first_payload(
        self, hass: HomeAssistant, entry: MockConfigEntry
    ) -> None:
        diag = await async_get_config_entry_diagnostics(hass, entry)
        assert diag["coordinator"]["data"] is None
        assert diag["coordinator"]["last_update_success"] is False

    async def test_barcode_redacted_after_payload(
        self,
        hass: HomeAssistant,
        entry: MockConfigEntry,
        coordinator: PylontechCoordinator,
    ) -> None:
        coordinator._process_payload(_PAYLOAD)
        diag = await async_get_config_entry_diagnostics(hass, entry)
        assert diag["coordinator"]["data"]["barcode"] == "**REDACTED**"
        assert diag["coordinator"]["data"]["manufacturer"] == "Pylon"

    async def test_battery_capacities_included(
        self,
        hass: HomeAssistant,
        entry: MockConfigEntry,
        coordinator: PylontechCoordinator,
    ) -> None:
        coordinator.set_battery_capacity(1, 4.8)
        diag = await async_get_config_entry_diagnostics(hass, entry)
        assert diag["coordinator"]["battery_capacities"] == {1: 4.8}
