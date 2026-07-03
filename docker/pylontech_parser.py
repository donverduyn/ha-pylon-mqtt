import logging
import re
from datetime import datetime

from structs import PylontechBattery, PylontechCell, PylontechSystem

_LOGGER = logging.getLogger(__name__)


class PylontechParser:
    """Parser for Pylontech BMS serial data."""

    @staticmethod
    def parse_pwr(
        raw_text: str, current_system: PylontechSystem | None = None
    ) -> PylontechSystem:
        """Parses 'pwr' command output. Returns updated system object."""
        if current_system is None:
            current_system = PylontechSystem(0, 0, 0, 0, 0, 0, 0)

        batteries = []
        lines = raw_text.splitlines()

        # Detect column positions from the header line so the parser is robust
        # against firmware variations (e.g. US5000 vs US2000/US3000) that may
        # add, remove, or reorder columns.  Fall back to the known-good defaults
        # if no header is found (matches original behaviour).
        #
        # NOTE: "Time" in the header splits into two tokens (date + time) in
        # data rows.  Only columns that appear *before* Time are safe to look
        # up by header index; B.V.St / B.T.St are intentionally skipped here.
        volt_idx = 1
        curr_idx = 2
        temp_idx = 3
        temp_low_idx = 4
        temp_high_idx = 5
        volt_low_idx = 6
        volt_high_idx = 7
        status_idx = 8
        volt_st_idx = 9
        curr_st_idx = 10
        temp_st_idx = 11
        soc_idx = 12
        # B.V.St / B.T.St appear after the Time column; Time takes two tokens in
        # data rows (date + clock), so their data index = header index + 1.
        bvst_data_idx = 15
        btst_data_idx = 16

        for line in lines:
            parts = line.split()
            # Header line starts with "Power" and always contains "Coulomb"
            if parts and parts[0] == "Power" and "Coulomb" in parts:
                volt_idx = parts.index("Volt") if "Volt" in parts else volt_idx
                curr_idx = parts.index("Curr") if "Curr" in parts else curr_idx
                temp_idx = parts.index("Tempr") if "Tempr" in parts else temp_idx
                temp_low_idx = parts.index("Tlow") if "Tlow" in parts else temp_low_idx
                temp_high_idx = (
                    parts.index("Thigh") if "Thigh" in parts else temp_high_idx
                )
                volt_low_idx = parts.index("Vlow") if "Vlow" in parts else volt_low_idx
                volt_high_idx = (
                    parts.index("Vhigh") if "Vhigh" in parts else volt_high_idx
                )
                status_idx = (
                    parts.index("Base.St") if "Base.St" in parts else status_idx
                )
                volt_st_idx = (
                    parts.index("Volt.St") if "Volt.St" in parts else volt_st_idx
                )
                curr_st_idx = (
                    parts.index("Curr.St") if "Curr.St" in parts else curr_st_idx
                )
                temp_st_idx = (
                    parts.index("Temp.St") if "Temp.St" in parts else temp_st_idx
                )
                soc_idx = parts.index("Coulomb") if "Coulomb" in parts else soc_idx
                if "B.V.St" in parts:
                    hdr_i = parts.index("B.V.St")
                    # Each "Time" header column expands to two data tokens
                    # (date + clock); count occurrences before B.V.St to
                    # compute the correct data-row offset.
                    extra = sum(1 for tok in parts[:hdr_i] if tok == "Time")
                    bvst_data_idx = hdr_i + extra
                if "B.T.St" in parts:
                    hdr_i = parts.index("B.T.St")
                    extra = sum(1 for tok in parts[:hdr_i] if tok == "Time")
                    btst_data_idx = hdr_i + extra
                _LOGGER.debug(
                    "pwr header detected — volt=%d curr=%d temp=%d "
                    "tlow=%d thigh=%d vlow=%d vhigh=%d "
                    "status=%d volt_st=%d curr_st=%d temp_st=%d soc=%d",
                    volt_idx,
                    curr_idx,
                    temp_idx,
                    temp_low_idx,
                    temp_high_idx,
                    volt_low_idx,
                    volt_high_idx,
                    status_idx,
                    volt_st_idx,
                    curr_st_idx,
                    temp_st_idx,
                    soc_idx,
                )
                break

        # Helpers for parsing extended columns — defined once, used per row.
        def _milli(p: list, idx: int) -> float | None:
            """Return a milli-unit column as its base unit, or None if absent or '-'."""
            if len(p) <= idx or p[idx] == "-":
                return None
            return int(p[idx]) / 1000.0

        def _st(p: list, idx: int) -> str | None:
            """Return status string column, or None if absent / placeholder '-'."""
            if len(p) <= idx:
                return None
            v = p[idx].strip()
            return v if v != "-" else None

        valid_lines = 0
        total_voltage = 0.0
        total_current = 0.0
        total_soc = 0.0

        for line in lines:
            parts = line.split()
            if len(parts) > 10 and parts[0].isdigit():
                if "Absent" in line:
                    continue
                try:
                    bat_id = int(parts[0])
                    voltage = int(parts[volt_idx]) / 1000.0
                    current = int(parts[curr_idx]) / 1000.0
                    temp = int(parts[temp_idx]) / 1000.0
                    status = parts[status_idx]
                    soc = int(parts[soc_idx].replace("%", ""))

                    # Extended fields — gracefully absent on older firmware
                    temp_low = _milli(parts, temp_low_idx)
                    temp_high = _milli(parts, temp_high_idx)
                    volt_low = _milli(parts, volt_low_idx)
                    volt_high = _milli(parts, volt_high_idx)
                    volt_st = _st(parts, volt_st_idx)
                    curr_st = _st(parts, curr_st_idx)
                    temp_st = _st(parts, temp_st_idx)
                    bvst = _st(parts, bvst_data_idx)
                    btst = _st(parts, btst_data_idx)

                    power = round(voltage * current, 2)

                    bat = PylontechBattery(
                        sys_id=bat_id,
                        voltage=voltage,
                        current=current,
                        temperature=temp,
                        soc=soc,
                        status=status,
                        power=power,
                        raw=line.strip(),
                        energy_stored=0.0,
                        temp_low=temp_low,
                        temp_high=temp_high,
                        volt_low=volt_low,
                        volt_high=volt_high,
                        volt_status=volt_st,
                        curr_status=curr_st,
                        temp_status=temp_st,
                        batt_volt_status=bvst,
                        batt_temp_status=btst,
                    )
                    batteries.append(bat)

                    total_voltage += voltage
                    total_current += current
                    total_soc += soc
                    valid_lines += 1

                except (ValueError, IndexError) as error:
                    _LOGGER.error("Error parsing pwr line '%s': %s", line, error)
                    continue

        current_system.batteries = batteries
        current_system.raw = raw_text

        if valid_lines > 0:
            current_system.voltage = round(total_voltage / valid_lines, 2)
            current_system.current = round(total_current, 2)
            current_system.soc = round(total_soc / valid_lines, 1)
            # Sum per-battery powers for accuracy; V̄ × ΣI can diverge from
            # Σ(V_i × I_i) when module voltages are not perfectly balanced.
            current_system.power = round(sum(b.power for b in batteries), 1)
        else:
            # No valid battery rows — reset system totals so we never publish
            # stale readings alongside an empty battery list.
            current_system.voltage = 0.0
            current_system.current = 0.0
            current_system.soc = 0.0
            current_system.power = 0.0

        return current_system

    @staticmethod
    def parse_info(raw_text: str, system: PylontechSystem) -> PylontechSystem:
        """Parses 'info' command output."""
        lines = raw_text.splitlines()
        for line in lines:
            if ":" not in line:
                continue
            parts = line.split(":", 1)
            # Normalise internal whitespace so "Soft  version" → "soft version"
            key = re.sub(r"\s+", " ", parts[0].strip().lower())
            val = parts[1].strip()

            if "manufacturer" in key:
                system.manufacturer = val
            elif "device name" in key:
                system.model = val
            elif "main soft" in key:
                system.fw_version = val
            elif "board version" in key:
                system.board_version = val
            elif key == "soft version":
                system.soft_version = val
            elif key == "boot version":
                system.boot_version = val
            elif "comm version" in key:
                system.comm_version = val
            elif "release date" in key:
                system.release_date = val
            elif "barcode" in key:
                system.barcode = val
            elif "specification" in key:
                system.spec = val
            elif "cell number" in key:
                try:
                    system.cell_count = int(val)
                except (ValueError, AttributeError):
                    _LOGGER.warning(
                        "Could not parse cell number from info line: %r", val
                    )
            elif "max dischg curr" in key:
                try:
                    system.max_dischg_curr = (
                        abs(int(re.sub(r"[^\d-]", "", val))) / 1000.0
                    )
                except (ValueError, AttributeError):
                    _LOGGER.warning(
                        "Could not parse max discharge current from info line: %r", val
                    )
            elif "max charge curr" in key:
                try:
                    system.max_charge_curr = int(re.sub(r"\D", "", val)) / 1000.0
                except (ValueError, AttributeError):
                    _LOGGER.warning(
                        "Could not parse max charge current from info line: %r", val
                    )

        return system

    @staticmethod
    def parse_stat(raw_text: str, system: PylontechSystem) -> PylontechSystem:
        """Parses 'stat' command output."""

        def _int(pattern: str) -> int | None:
            m = re.search(pattern, raw_text, re.IGNORECASE)
            return int(m.group(1)) if m else None

        system.soh = _int(r"Sys SOH\s*:\s*(\d+)")
        system.cycles = _int(r"CYCLE Times\s*:\s*(\d+)")
        system.charge_times = _int(r"Charge Times\s*:\s*(\d+)")
        system.discharge_cnt = _int(r"Discharge Cnt\.\s*:\s*(\d+)")
        system.idle_times = _int(r"Idle Times\s*:\s*(\d+)")
        system.shut_times = _int(r"Shut Times\s*:\s*(\d+)")
        system.reset_times = _int(r"Reset Times\s*:\s*(\d+)")
        system.sc_times = _int(r"SC Times\s*:\s*(\d+)")
        system.bat_ov_times = _int(r"Bat OV Times\s*:\s*(\d+)")
        system.bat_hv_times = _int(r"Bat HV Times\s*:\s*(\d+)")
        system.bat_lv_times = _int(r"Bat LV Times\s*:\s*(\d+)")
        system.bat_uv_times = _int(r"Bat UV Times\s*:\s*(\d+)")
        system.pwr_ov_times = _int(r"Pwr OV Times\s*:\s*(\d+)")
        system.pwr_hv_times = _int(r"Pwr HV Times\s*:\s*(\d+)")
        system.life_warn_times = _int(r"LifeWarn Times\s*:\s*(\d+)")
        system.life_alarm_times = _int(r"LifeAlarm Times\s*:\s*(\d+)")
        system.pwr_coulomb = _int(r"Pwr Coulomb\s*:\s*(\d+)")
        system.dsg_cap = _int(r"Dsg Cap\s*:\s*(\d+)")

        return system

    @staticmethod
    def parse_time(raw_text: str, system: PylontechSystem) -> PylontechSystem:
        """Parses 'time' command output.
        Example: Ds3231 2025-12-21 21:14:53
        """
        # Look for YYYY-MM-DD HH:MM:SS pattern
        match = re.search(r"(\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2})", raw_text)
        if match:
            system.bms_time = match.group(1)
        return system

    @staticmethod
    def generate_time_command(timestamp: datetime) -> str:
        """Generates the 'time' command for specific datetime."""
        # time [year] [month] [day] [hour] [minute] [second]
        # Example: time 25 12 21 13 00 00
        return timestamp.strftime("time %y %m %d %H %M %S")

    @staticmethod
    def parse_bat(raw_text: str, battery: PylontechBattery) -> PylontechBattery:
        """Parses 'bat N' command output, populating battery.cells.

        Detects column positions from the header line so the parser is robust
        against firmware variations that add, remove, or reorder columns.
        Falls back to the original known-good defaults when no header is found.

        Header example (two-word compound columns each map to one data token):
          Battery  Volt  Curr  Tempr  Base State  Volt. State  Curr. State  Temp. State  SOC  Coulomb
          0        3378  3806  17000  Charge      Normal       Normal       Normal       85%  3333 mAH
        """
        # Default column indices — match the original hard-coded positions so
        # firmware that omits the header line still parses correctly.
        volt_idx = 1
        curr_idx = 2
        temp_idx = 3
        base_idx = 4
        volt_st_idx = 5
        curr_st_idx = 6
        temp_st_idx = 7
        soc_idx = 8
        cap_idx = 9

        cells: list[PylontechCell] = []
        for line in raw_text.splitlines():
            parts = line.split()
            if not parts:
                continue

            # Header detection: starts with "Battery" and contains "Coulomb".
            # Two-word compound column names ("X State") occupy two header
            # tokens but produce a single token in each data row, so the
            # data-row index is tracked separately from the header token index.
            if parts[0] == "Battery" and "Coulomb" in parts:
                hdr_i = 0  # header token position
                data_i = 0  # corresponding data-row column index
                while hdr_i < len(parts):
                    tok = parts[hdr_i]
                    if (
                        hdr_i + 1 < len(parts)
                        and parts[hdr_i + 1].lower() == "state"
                    ):
                        # Compound "X State" header → single data token
                        if tok == "Base":
                            base_idx = data_i
                        elif tok == "Volt.":
                            volt_st_idx = data_i
                        elif tok == "Curr.":
                            curr_st_idx = data_i
                        elif tok == "Temp.":
                            temp_st_idx = data_i
                        hdr_i += 2
                    else:
                        if tok == "Volt":
                            volt_idx = data_i
                        elif tok == "Curr":
                            curr_idx = data_i
                        elif tok == "Tempr":
                            temp_idx = data_i
                        elif tok == "SOC":
                            soc_idx = data_i
                        elif tok == "Coulomb":
                            cap_idx = data_i
                        hdr_i += 1
                    data_i += 1
                _LOGGER.debug(
                    "bat header detected — volt=%d curr=%d temp=%d "
                    "base=%d volt_st=%d curr_st=%d temp_st=%d soc=%d cap=%d",
                    volt_idx, curr_idx, temp_idx,
                    base_idx, volt_st_idx, curr_st_idx, temp_st_idx,
                    soc_idx, cap_idx,
                )
                continue

            # Data rows: first token is the cell index (non-negative integer).
            if not parts[0].isdigit():
                continue
            if len(parts) < soc_idx + 1:
                continue
            try:
                cell_id = int(parts[0])
                voltage = int(parts[volt_idx]) / 1000.0
                current = int(parts[curr_idx]) / 1000.0
                temperature = int(parts[temp_idx]) / 1000.0
                base_state = parts[base_idx]
                volt_status = parts[volt_st_idx] if len(parts) > volt_st_idx else None
                curr_status = parts[curr_st_idx] if len(parts) > curr_st_idx else None
                temp_status = parts[temp_st_idx] if len(parts) > temp_st_idx else None
                soc = int(parts[soc_idx].replace("%", "")) if len(parts) > soc_idx else 0
                capacity = int(parts[cap_idx]) if len(parts) > cap_idx else None
                cells.append(
                    PylontechCell(
                        cell_id=cell_id,
                        voltage=voltage,
                        current=current,
                        temperature=temperature,
                        base_state=base_state,
                        volt_status=volt_status,
                        curr_status=curr_status,
                        temp_status=temp_status,
                        soc=soc,
                        capacity=capacity,
                    )
                )
            except (ValueError, IndexError) as err:
                _LOGGER.error("Error parsing bat line '%s': %s", line, err)
        battery.cells = cells
        return battery
