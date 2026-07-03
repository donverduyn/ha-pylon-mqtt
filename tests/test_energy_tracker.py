"""Unit tests for EnergyTracker (docker/main.py)."""

import json
import os
from datetime import datetime
from unittest.mock import patch

import pytest
from main import EnergyTracker


class TestEnergyTrackerInitialState:
    def test_energy_in_starts_at_zero(self):
        assert EnergyTracker().energy_in == 0.0

    def test_energy_out_starts_at_zero(self):
        assert EnergyTracker().energy_out == 0.0


class TestEnergyTrackerFirstCall:
    def test_first_call_does_not_accumulate_energy(self):
        """The first update() has no previous timestamp so nothing is counted."""
        tracker = EnergyTracker()
        with patch("main.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2024, 1, 1, 12, 0, 0)
            tracker.update(1000.0)
        assert tracker.energy_in == 0.0
        assert tracker.energy_out == 0.0


class TestEnergyTrackerCharging:
    def test_positive_power_adds_to_energy_in(self):
        """1000 W over 1 h = 1.0 kWh in."""
        tracker = EnergyTracker()
        t0 = datetime(2024, 1, 1, 12, 0, 0)
        t1 = datetime(2024, 1, 1, 13, 0, 0)
        with patch("main.datetime") as mock_dt:
            mock_dt.now.side_effect = [t0, t1]
            tracker.update(1000.0)
            tracker.update(1000.0)
        assert tracker.energy_in == pytest.approx(1.0)
        assert tracker.energy_out == 0.0

    def test_zero_power_counts_as_charging(self):
        """power == 0 satisfies `power >= 0` → goes to energy_in (adds 0 kWh)."""
        tracker = EnergyTracker()
        t0 = datetime(2024, 1, 1, 12, 0, 0)
        t1 = datetime(2024, 1, 1, 13, 0, 0)
        with patch("main.datetime") as mock_dt:
            mock_dt.now.side_effect = [t0, t1]
            tracker.update(0.0)
            tracker.update(0.0)
        assert tracker.energy_in == 0.0
        assert tracker.energy_out == 0.0


class TestEnergyTrackerDischarging:
    def test_negative_power_adds_to_energy_out(self):
        """−1000 W over 1 h = 1.0 kWh out."""
        tracker = EnergyTracker()
        t0 = datetime(2024, 1, 1, 12, 0, 0)
        t1 = datetime(2024, 1, 1, 13, 0, 0)
        with patch("main.datetime") as mock_dt:
            mock_dt.now.side_effect = [t0, t1]
            tracker.update(-1000.0)
            tracker.update(-1000.0)
        assert tracker.energy_in == 0.0
        assert tracker.energy_out == pytest.approx(1.0)


class TestEnergyTrackerCumulative:
    def test_multiple_charge_intervals(self):
        """Four calls → three 30-min intervals at 2000 W = 3.0 kWh in."""
        tracker = EnergyTracker()
        times = [
            datetime(2024, 1, 1, 12, 0, 0),
            datetime(2024, 1, 1, 12, 30, 0),
            datetime(2024, 1, 1, 13, 0, 0),
            datetime(2024, 1, 1, 13, 30, 0),
        ]
        with patch("main.datetime") as mock_dt:
            mock_dt.now.side_effect = times
            for _ in times:
                tracker.update(2000.0)
        assert tracker.energy_in == pytest.approx(3.0)

    def test_mixed_charge_then_discharge(self):
        """1 h charging then 1 h discharging at the same power level."""
        tracker = EnergyTracker()
        t0 = datetime(2024, 1, 1, 12, 0, 0)
        t1 = datetime(2024, 1, 1, 13, 0, 0)
        t2 = datetime(2024, 1, 1, 14, 0, 0)
        with patch("main.datetime") as mock_dt:
            mock_dt.now.side_effect = [t0, t1, t2]
            tracker.update(500.0)  # first call: no accumulation
            tracker.update(500.0)  # 1 h at 500 W → 0.5 kWh in
            tracker.update(-500.0)  # 1 h at -500 W → 0.5 kWh out
        assert tracker.energy_in == pytest.approx(0.5)
        assert tracker.energy_out == pytest.approx(0.5)


class TestEnergyTrackerInvalidate:
    def test_invalidate_prevents_phantom_energy_after_gap(self):
        """After a comms gap, invalidate_last_time() must prevent energy being
        attributed to the outage period.

        Without the fix, reconnecting after a 30-minute outage with 2000 W
        would falsely add 2000*0.5/1000 = 1.0 kWh.
        """
        tracker = EnergyTracker()
        t0 = datetime(2024, 1, 1, 12, 0, 0)
        t1 = datetime(2024, 1, 1, 12, 30, 0)  # 30-min gap (simulated outage)

        with patch("main.datetime") as mock_dt:
            mock_dt.now.side_effect = [t0, t1]
            tracker.update(2000.0)  # establish _last_time
            tracker.invalidate_last_time()  # simulate reconnect — drop the gap
            tracker.update(2000.0)  # must NOT count the 30-min gap

        assert tracker.energy_in == 0.0
        assert tracker.energy_out == 0.0

    def test_invalidate_does_not_reset_accumulated_totals(self):
        """Calling invalidate_last_time() must not zero energy_in / energy_out."""
        tracker = EnergyTracker()
        t0 = datetime(2024, 1, 1, 12, 0, 0)
        t1 = datetime(2024, 1, 1, 13, 0, 0)

        with patch("main.datetime") as mock_dt:
            mock_dt.now.side_effect = [t0, t1]
            tracker.update(1000.0)  # set _last_time
            tracker.update(1000.0)  # 1 h at 1000 W → 1.0 kWh

        tracker.invalidate_last_time()  # drop timestamp; totals must survive

        assert tracker.energy_in == pytest.approx(1.0)
        assert tracker.energy_out == 0.0


# ===========================================================================
# Persistence — state_file save / load
# ===========================================================================


class TestEnergyTrackerPersistence:
    def test_no_state_file_starts_at_zero(self):
        """EnergyTracker() without a state_file must start at 0 (no side-effects)."""
        tracker = EnergyTracker()
        assert tracker.energy_in == 0.0
        assert tracker.energy_out == 0.0

    def test_counters_restored_after_restart(self, tmp_path):
        """Energy accumulated in one instance must be visible in a second instance
        that reads the same state file — simulating a container restart."""
        state_file = str(tmp_path / "energy.json")

        t0 = datetime(2024, 1, 1, 12, 0, 0)
        t1 = datetime(2024, 1, 1, 13, 0, 0)

        with patch("main.datetime") as mock_dt:
            mock_dt.now.side_effect = [t0, t1]
            tracker = EnergyTracker(state_file=state_file)
            tracker.update(1000.0)   # first call: no accumulation
            tracker.update(1000.0)   # 1 h at 1000 W → 1.0 kWh in

        # Simulate restart: new instance reads the same file
        tracker2 = EnergyTracker(state_file=state_file)
        assert tracker2.energy_in == pytest.approx(1.0)
        assert tracker2.energy_out == 0.0

    def test_discharge_energy_persisted(self, tmp_path):
        state_file = str(tmp_path / "energy.json")
        t0 = datetime(2024, 1, 1, 12, 0, 0)
        t1 = datetime(2024, 1, 1, 13, 0, 0)

        with patch("main.datetime") as mock_dt:
            mock_dt.now.side_effect = [t0, t1]
            tracker = EnergyTracker(state_file=state_file)
            tracker.update(-500.0)
            tracker.update(-500.0)  # 1 h at -500 W → 0.5 kWh out

        tracker2 = EnergyTracker(state_file=state_file)
        assert tracker2.energy_in == 0.0
        assert tracker2.energy_out == pytest.approx(0.5)

    def test_missing_state_file_starts_at_zero(self, tmp_path):
        """A missing state file must silently start counters at 0."""
        state_file = str(tmp_path / "nonexistent.json")
        tracker = EnergyTracker(state_file=state_file)
        assert tracker.energy_in == 0.0
        assert tracker.energy_out == 0.0

    def test_corrupt_state_file_starts_at_zero(self, tmp_path):
        """A corrupt JSON file must be silently ignored; counters start at 0."""
        state_file = str(tmp_path / "energy.json")
        with open(state_file, "w") as f:
            f.write("not valid json{{")

        tracker = EnergyTracker(state_file=state_file)
        assert tracker.energy_in == 0.0
        assert tracker.energy_out == 0.0

    def test_partial_state_file_starts_at_zero(self, tmp_path):
        """A JSON file missing expected keys must be silently ignored."""
        state_file = str(tmp_path / "energy.json")
        with open(state_file, "w") as f:
            json.dump({"energy_in": 1.5}, f)  # missing energy_out

        tracker = EnergyTracker(state_file=state_file)
        assert tracker.energy_in == 0.0
        assert tracker.energy_out == 0.0

    def test_invalidate_does_not_clear_persisted_state(self, tmp_path):
        """invalidate_last_time() must not touch the state file."""
        state_file = str(tmp_path / "energy.json")
        t0 = datetime(2024, 1, 1, 12, 0, 0)
        t1 = datetime(2024, 1, 1, 13, 0, 0)

        with patch("main.datetime") as mock_dt:
            mock_dt.now.side_effect = [t0, t1]
            tracker = EnergyTracker(state_file=state_file)
            tracker.update(1000.0)
            tracker.update(1000.0)  # 1 kWh in

        tracker.invalidate_last_time()

        tracker2 = EnergyTracker(state_file=state_file)
        assert tracker2.energy_in == pytest.approx(1.0)
