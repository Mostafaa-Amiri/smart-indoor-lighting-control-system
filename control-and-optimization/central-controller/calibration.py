# calibration.py
# Professional calibration runner with warnings + history fallback support.
#
# Main improvements:
# - Tracks calibration warnings in structured form
# - Detects panel applied-confirmation timeout
# - Detects missing fresh lux values
# - Can use previous calibration history for missing/risky values
# - Does not silently treat a risky calibration as fully successful
#
# Important:
# - strict_mode=True  -> stop immediately on missing confirmation / missing fresh lux
# - strict_mode=False -> continue, but mark fallback_used / warnings

import json
import time
import os
from dataclasses import dataclass, asdict, field
from typing import Dict, List, Optional, Callable, Any


class CalibrationStopRequested(Exception):
    def __init__(self, stopped_at_panel_id: Optional[str] = None):
        super().__init__("Calibration stop requested")
        self.stopped_at_panel_id = stopped_at_panel_id


@dataclass
class CalibrationWarning:
    level: str               # "warning" or "error"
    kind: str                # "panel_timeout", "sensor_timeout", "fallback_used", ...
    message: str
    device_id: Optional[str] = None
    device_label: Optional[str] = None
    step: Optional[str] = None


@dataclass
class CalibrationResult:
    panel_ids: List[str]
    sensor_ids: List[str]
    panel_labels: Dict[str, str]
    sensor_labels: Dict[str, str]
    ambient_lux: List[float]
    gain_matrix: List[List[float]]
    raw_readings: Dict[str, List[float]]
    created_at: float
    settle_seconds: float

    # New fields
    status: str = "success"          # "success", "partial", "failed"
    fallback_used: bool = False
    fallback_source: Optional[str] = None
    warnings: List[Dict[str, Any]] = field(default_factory=list)
    completed_panel_ids: List[str] = field(default_factory=list)
    stopped_at_panel_id: Optional[str] = None
    ambient_completed: bool = True


class CalibrationRunner:
    def __init__(
        self,
        backend,
        panel_ids: List[str],
        sensor_ids: List[str],
        panel_labels: Optional[Dict[str, str]] = None,
        sensor_labels: Optional[Dict[str, str]] = None,
        settle_seconds: float = 3.0,
        sensor_timeout_seconds: float = 5.0,
        applied_timeout_seconds: float = 5.0,
        strict_mode: bool = False,
        log_callback: Optional[Callable[[str], None]] = None,
        history_path: Optional[str] = None,
        use_history_fallback: bool = True,
        stop_event: Optional[Any] = None,
    ):
        self.backend = backend
        self.panel_ids = panel_ids
        self.sensor_ids = sensor_ids
        self.panel_labels = panel_labels or {}
        self.sensor_labels = sensor_labels or {}
        self.settle_seconds = settle_seconds
        self.sensor_timeout_seconds = sensor_timeout_seconds
        self.applied_timeout_seconds = applied_timeout_seconds
        self.strict_mode = strict_mode
        self.log_callback = log_callback
        self.stop_event = stop_event

        # New
        self.history_path = history_path
        self.use_history_fallback = use_history_fallback
        self.warnings: List[CalibrationWarning] = []
        self.fallback_used = False
        self.previous_result: Optional[CalibrationResult] = None
        self.completed_panel_ids: List[str] = []
        self.current_panel_id: Optional[str] = None
        self.latest_ambient_lux: Optional[List[float]] = None
        self.latest_panel_readings: Dict[str, List[float]] = {}

        if self.history_path and os.path.exists(self.history_path):
            try:
                self.previous_result = self.load_result(self.history_path)
            except Exception as e:
                self._add_warning(
                    kind="history_load_failed",
                    message=f"Previous calibration exists but could not be loaded: {e}",
                    level="warning",
                )

    # =========================
    # Label helpers
    # =========================

    def _panel_label(self, panel_id: str) -> str:
        return self.panel_labels.get(panel_id, panel_id)

    def _sensor_label(self, sensor_id: str) -> str:
        return self.sensor_labels.get(sensor_id, sensor_id)

    # =========================
    # Warning helpers
    # =========================

    def _add_warning(
        self,
        kind: str,
        message: str,
        level: str = "warning",
        device_id: Optional[str] = None,
        device_label: Optional[str] = None,
        step: Optional[str] = None,
    ) -> None:
        warning = CalibrationWarning(
            level=level,
            kind=kind,
            message=message,
            device_id=device_id,
            device_label=device_label,
            step=step,
        )
        self.warnings.append(warning)
        self._log(f"{level.upper()}: {message}")

    def _warnings_as_dicts(self) -> List[Dict[str, Any]]:
        return [asdict(w) for w in self.warnings]

    def _has_warnings(self) -> bool:
        return len(self.warnings) > 0

    # =========================
    # History helpers
    # =========================

    def _previous_sensor_index(self, sensor_id: str) -> Optional[int]:
        if not self.previous_result:
            return None

        if sensor_id not in self.previous_result.sensor_ids:
            return None

        return self.previous_result.sensor_ids.index(sensor_id)

    def _previous_panel_index(self, panel_id: str) -> Optional[int]:
        if not self.previous_result:
            return None

        if panel_id not in self.previous_result.panel_ids:
            return None

        return self.previous_result.panel_ids.index(panel_id)

    def _previous_ambient_value(self, sensor_id: str) -> Optional[float]:
        sensor_index = self._previous_sensor_index(sensor_id)

        if sensor_index is None:
            return None

        try:
            return float(self.previous_result.ambient_lux[sensor_index])
        except Exception:
            return None

    def _previous_gain_value(self, sensor_id: str, panel_id: str) -> Optional[float]:
        sensor_index = self._previous_sensor_index(sensor_id)
        panel_index = self._previous_panel_index(panel_id)

        if sensor_index is None or panel_index is None:
            return None

        try:
            return float(self.previous_result.gain_matrix[sensor_index][panel_index])
        except Exception:
            return None

    def _can_use_history(self) -> bool:
        return self.use_history_fallback and self.previous_result is not None

    # =========================
    # Main calibration
    # =========================

    def run_full_calibration(self) -> CalibrationResult:
        if not self.panel_ids:
            raise ValueError("No panel IDs provided for calibration.")

        if not self.sensor_ids:
            raise ValueError("No sensor IDs provided for calibration.")

        self._log("Starting full calibration")
        self._log(f"Panels: {[self._panel_label(pid) for pid in self.panel_ids]}")
        self._log(f"Sensors: {[self._sensor_label(sid) for sid in self.sensor_ids]}")

        if self.previous_result:
            self._log("Previous calibration history loaded and available for fallback.")
        else:
            self._log("No previous calibration history available.")

        raw_readings: Dict[str, List[float]] = {}

        try:
            # ---------- Step 0: ambient ----------
            self._check_stop()
            self._log("Step 0: switching all panels OFF")
            self._set_all_panels(0)

            self._wait_for_panels_applied(
                expected_duties={pid: [0, 0, 0, 0] for pid in self.panel_ids},
                step="ambient_all_off",
            )

            self._log(f"Waiting {self.settle_seconds} seconds for panels/light to settle")
            self._sleep_interruptible(self.settle_seconds)

            self._log("Requesting ambient lux from all sensors")
            ambient_lux = self._request_and_collect_lux(step="ambient")
            self.latest_ambient_lux = list(ambient_lux)
            raw_readings["ambient"] = ambient_lux

            self._log(f"Ambient lux: {self._format_sensor_values(ambient_lux)}")

            # ---------- Step 1..N: one panel at 100 ----------
            panel_readings: Dict[str, List[float]] = {}

            for active_panel_id in self.panel_ids:
                self._check_stop(active_panel_id)
                self.current_panel_id = active_panel_id
                active_label = self._panel_label(active_panel_id)

                self._log(f"Calibrating {active_label}: 100%, all other panels 0%")

                duty_map = {
                    panel_id: 100 if panel_id == active_panel_id else 0
                    for panel_id in self.panel_ids
                }

                self._set_panel_duties(duty_map)

                expected = {
                    panel_id: [duty_map[panel_id]] * 4
                    for panel_id in self.panel_ids
                }

                self._wait_for_panels_applied(
                    expected_duties=expected,
                    step=f"panel_{active_label}_on",
                )

                self._log(f"Waiting {self.settle_seconds} seconds for light to settle")
                self._sleep_interruptible(self.settle_seconds, active_panel_id)

                self._log("Requesting lux from all sensors")
                readings = self._request_and_collect_lux(step=f"reading_{active_panel_id}")

                panel_readings[active_panel_id] = readings
                self.latest_panel_readings[active_panel_id] = list(readings)
                self.completed_panel_ids.append(active_panel_id)
                raw_readings[active_label] = readings

                self._log(f"Reading for {active_label}: {self._format_sensor_values(readings)}")
                self._log(f"{active_label} calibration measurement completed.")

            # ---------- Final: switch all panels off ----------
            self.current_panel_id = None
            self._log("Calibration measurement done. Switching all panels OFF")
            self._set_all_panels(0)

            self._wait_for_panels_applied(
                expected_duties={pid: [0, 0, 0, 0] for pid in self.panel_ids},
                step="final_all_off",
            )

            # ---------- Build gain matrix ----------
            gain_matrix = self._build_gain_matrix(
                ambient_lux=ambient_lux,
                panel_readings=panel_readings,
            )

            status = "partial" if self._has_warnings() or self.fallback_used else "success"

            self._log("Calibration complete")
            self._log(f"Calibration status: {status}")
            self._log("Gain matrix:")
            self._log(str(self._gain_matrix_as_labels(gain_matrix)))

            return CalibrationResult(
                panel_ids=self.panel_ids,
                sensor_ids=self.sensor_ids,
                panel_labels=self.panel_labels,
                sensor_labels=self.sensor_labels,
                ambient_lux=ambient_lux,
                gain_matrix=gain_matrix,
                raw_readings=raw_readings,
                created_at=time.time(),
                settle_seconds=self.settle_seconds,
                status=status,
                fallback_used=self.fallback_used,
                fallback_source=self.history_path if self.fallback_used else None,
                warnings=self._warnings_as_dicts(),
                completed_panel_ids=list(self.completed_panel_ids),
                ambient_completed=True,
            )

        except CalibrationStopRequested as stop:
            stopped_at = stop.stopped_at_panel_id or self.current_panel_id
            self._log("Stop requested. Switching all panels OFF before saving partial calibration.")
            try:
                self._set_all_panels(0, ignore_stop=True)
            except Exception as exc:
                self._log(f"WARNING: could not switch panels off after stop request: {exc}")

            return self._build_partial_result(stopped_at_panel_id=stopped_at)

    # =========================
    # Panel control
    # =========================

    def _set_all_panels(self, duty: int, ignore_stop: bool = False) -> None:
        duty_map = {panel_id: duty for panel_id in self.panel_ids}
        self._set_panel_duties(duty_map, ignore_stop=ignore_stop)

    def _set_panel_duties(
        self,
        duty_map: Dict[str, int],
        ignore_stop: bool = False,
    ) -> None:
        for panel_id, duty in duty_map.items():
            if not ignore_stop:
                self._check_stop(self.current_panel_id)
            duty = int(max(0, min(100, duty)))
            self.backend.send_panel_duty(
                panel_id,
                duty,
                transition="immediate",
            )
            self._log(f"Sent duty {duty}% to {self._panel_label(panel_id)}")

    def _wait_for_panels_applied(
        self,
        expected_duties: Dict[str, List[int]],
        step: str,
    ) -> None:
        start = time.time()
        pending = set(expected_duties.keys())

        while pending and (time.time() - start) < self.applied_timeout_seconds:
            self._check_stop(self.current_panel_id)
            panels = self.backend.get_panels()

            for panel_id in list(pending):
                panel = panels.get(panel_id)
                if panel is None:
                    continue

                expected = expected_duties[panel_id]

                if not panel.duty:
                    continue

                actual = [int(round(x)) for x in panel.duty]

                if actual == expected:
                    pending.remove(panel_id)

            if pending:
                self._sleep_interruptible(0.1, self.current_panel_id)

        if pending:
            pending_labels = [self._panel_label(pid) for pid in sorted(pending)]
            msg = f"Applied confirmation timeout for panels: {pending_labels}"

            if self.strict_mode:
                raise RuntimeError(msg)

            for panel_id in sorted(pending):
                self._add_warning(
                    kind="panel_timeout",
                    message=f"{self._panel_label(panel_id)} did not confirm the expected duty in step '{step}'.",
                    device_id=panel_id,
                    device_label=self._panel_label(panel_id),
                    step=step,
                )
        else:
            self._log("All panels confirmed applied duty")

    # =========================
    # Sensor handling
    # =========================

    def _request_and_collect_lux(self, step: str) -> List[float]:
        request_time = time.time()

        for sensor_id in self.sensor_ids:
            self.backend.request_sensor_lux(sensor_id)
            self._log(f"Requested lux from {self._sensor_label(sensor_id)}")

        start = time.time()
        values: Dict[str, float] = {}

        while (time.time() - start) < self.sensor_timeout_seconds:
            self._check_stop(self.current_panel_id)
            sensors = self.backend.get_sensors()

            for sensor_id in self.sensor_ids:
                sensor = sensors.get(sensor_id)

                if sensor is None:
                    continue

                if sensor.lux is None:
                    continue

                if sensor.last_lux >= request_time:
                    values[sensor_id] = float(sensor.lux)

            if len(values) == len(self.sensor_ids):
                break

            self._sleep_interruptible(0.1, self.current_panel_id)

        missing = [sid for sid in self.sensor_ids if sid not in values]

        if missing:
            missing_labels = [self._sensor_label(sid) for sid in missing]
            msg = f"Missing fresh lux values from sensors: {missing_labels} during step '{step}'"

            if self.strict_mode:
                raise RuntimeError(msg)

            for sensor_id in missing:
                sensor_label = self._sensor_label(sensor_id)

                fallback_value = None

                # For ambient step, previous ambient is the safest history fallback.
                if step == "ambient" and self._can_use_history():
                    fallback_value = self._previous_ambient_value(sensor_id)

                # If no previous ambient exists, use latest available live value.
                if fallback_value is None:
                    sensors = self.backend.get_sensors()
                    sensor = sensors.get(sensor_id)
                    if sensor is not None and sensor.lux is not None:
                        fallback_value = float(sensor.lux)

                # Last fallback: 0.0, but mark strongly as warning.
                if fallback_value is None:
                    fallback_value = 0.0
                    self._add_warning(
                        kind="sensor_timeout_zero_fallback",
                        message=f"{sensor_label} did not return fresh lux in step '{step}'. No history/live value available, using 0.0 lux.",
                        device_id=sensor_id,
                        device_label=sensor_label,
                        step=step,
                    )
                else:
                    self._add_warning(
                        kind="sensor_timeout_fallback",
                        message=f"{sensor_label} did not return fresh lux in step '{step}'. Using fallback value {round(fallback_value, 2)} lux.",
                        device_id=sensor_id,
                        device_label=sensor_label,
                        step=step,
                    )

                self.fallback_used = True
                values[sensor_id] = float(fallback_value)

        return [round(values[sensor_id], 2) for sensor_id in self.sensor_ids]

    # =========================
    # Matrix calculation
    # =========================

    def _build_gain_matrix(
        self,
        ambient_lux: List[float],
        panel_readings: Dict[str, List[float]],
    ) -> List[List[float]]:

        gain_matrix = []

        for sensor_index, sensor_id in enumerate(self.sensor_ids):
            row = []

            for panel_id in self.panel_ids:
                reading = panel_readings[panel_id][sensor_index]
                ambient = ambient_lux[sensor_index]

                gain = reading - ambient
                gain = max(0.0, gain)
                gain = round(gain, 2)

                # If this sensor or panel had problems, previous gain is safer.
                should_try_history = False

                for warning in self.warnings:
                    if warning.device_id == sensor_id:
                        should_try_history = True
                    if warning.device_id == panel_id:
                        should_try_history = True

                if should_try_history and self._can_use_history():
                    previous_gain = self._previous_gain_value(sensor_id, panel_id)

                    if previous_gain is not None:
                        self.fallback_used = True
                        self._add_warning(
                            kind="gain_history_fallback",
                            message=f"Using previous gain for {self._sensor_label(sensor_id)} / {self._panel_label(panel_id)}: {round(previous_gain, 2)}",
                            device_id=sensor_id,
                            device_label=self._sensor_label(sensor_id),
                            step="gain_matrix",
                        )
                        gain = round(previous_gain, 2)

                row.append(gain)

            gain_matrix.append(row)

        return gain_matrix

    def _build_partial_result(self, stopped_at_panel_id: Optional[str]) -> CalibrationResult:
        stopped_label = self._panel_label(stopped_at_panel_id) if stopped_at_panel_id else "the next panel"

        self._add_warning(
            kind="calibration_stopped",
            message=f"Calibration was stopped at {stopped_label}. Completed panels were saved; unfinished panels kept previous gain values where available.",
            device_id=stopped_at_panel_id,
            device_label=stopped_label,
            step="stop",
        )

        ambient_lux = self.latest_ambient_lux or self._ambient_from_history()
        raw_readings = {"ambient": ambient_lux}

        for panel_id in self.completed_panel_ids:
            if panel_id in self.latest_panel_readings:
                raw_readings[self._panel_label(panel_id)] = self.latest_panel_readings[panel_id]

        gain_matrix = self._build_gain_matrix_preserving_history(
            ambient_lux=ambient_lux,
            panel_readings=self.latest_panel_readings,
        )

        completed_labels = [self._panel_label(pid) for pid in self.completed_panel_ids]
        self._log(f"Partial calibration saved. Completed panels: {completed_labels}")

        return CalibrationResult(
            panel_ids=self.panel_ids,
            sensor_ids=self.sensor_ids,
            panel_labels=self.panel_labels,
            sensor_labels=self.sensor_labels,
            ambient_lux=ambient_lux,
            gain_matrix=gain_matrix,
            raw_readings=raw_readings,
            created_at=time.time(),
            settle_seconds=self.settle_seconds,
            status="partial",
            fallback_used=True,
            fallback_source=self.history_path if self.previous_result else None,
            warnings=self._warnings_as_dicts(),
            completed_panel_ids=list(self.completed_panel_ids),
            stopped_at_panel_id=stopped_at_panel_id,
            ambient_completed=self.latest_ambient_lux is not None,
        )

    def _ambient_from_history(self) -> List[float]:
        values = []

        for sensor_id in self.sensor_ids:
            fallback = self._previous_ambient_value(sensor_id)

            if fallback is None:
                fallback = 0.0
                self._add_warning(
                    kind="ambient_history_missing",
                    message=f"No previous ambient value for {self._sensor_label(sensor_id)}; using 0.0 lux.",
                    device_id=sensor_id,
                    device_label=self._sensor_label(sensor_id),
                    step="partial_ambient",
                )

            values.append(round(float(fallback), 2))

        return values

    def _build_gain_matrix_preserving_history(
        self,
        ambient_lux: List[float],
        panel_readings: Dict[str, List[float]],
    ) -> List[List[float]]:
        gain_matrix = []

        for sensor_index, sensor_id in enumerate(self.sensor_ids):
            row = []

            for panel_id in self.panel_ids:
                if panel_id in panel_readings:
                    reading = panel_readings[panel_id][sensor_index]
                    ambient = ambient_lux[sensor_index]
                    gain = round(max(0.0, reading - ambient), 2)
                else:
                    previous_gain = self._previous_gain_value(sensor_id, panel_id)

                    if previous_gain is None:
                        previous_gain = 0.0
                        self._add_warning(
                            kind="gain_history_missing",
                            message=f"No previous gain for {self._sensor_label(sensor_id)} / {self._panel_label(panel_id)}; using 0.0.",
                            device_id=panel_id,
                            device_label=self._panel_label(panel_id),
                            step="partial_gain_matrix",
                        )

                    gain = round(float(previous_gain), 2)

                row.append(gain)

            gain_matrix.append(row)

        return gain_matrix

    def _stop_requested(self) -> bool:
        return bool(self.stop_event is not None and self.stop_event.is_set())

    def _check_stop(self, stopped_at_panel_id: Optional[str] = None) -> None:
        if self._stop_requested():
            raise CalibrationStopRequested(stopped_at_panel_id)

    def _sleep_interruptible(
        self,
        seconds: float,
        stopped_at_panel_id: Optional[str] = None,
    ) -> None:
        deadline = time.time() + seconds

        while time.time() < deadline:
            self._check_stop(stopped_at_panel_id)
            time.sleep(min(0.1, max(0.0, deadline - time.time())))

    def _format_sensor_values(self, values: List[float]) -> Dict[str, float]:
        return {
            self._sensor_label(self.sensor_ids[i]): values[i]
            for i in range(len(self.sensor_ids))
        }

    def _gain_matrix_as_labels(self, gain_matrix: List[List[float]]) -> Dict[str, Dict[str, float]]:
        result = {}

        for sensor_index, sensor_id in enumerate(self.sensor_ids):
            sensor_label = self._sensor_label(sensor_id)
            result[sensor_label] = {}

            for panel_index, panel_id in enumerate(self.panel_ids):
                panel_label = self._panel_label(panel_id)
                result[sensor_label][panel_label] = gain_matrix[sensor_index][panel_index]

        return result

    # =========================
    # Save / load
    # =========================

    @staticmethod
    def save_result(result: CalibrationResult, path: str = "calibration.json") -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(result), f, indent=2)

    @staticmethod
    def load_result(path: str = "calibration.json") -> CalibrationResult:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Backward compatibility with old calibration.json files
        data.setdefault("status", "success")
        data.setdefault("fallback_used", False)
        data.setdefault("fallback_source", None)
        data.setdefault("warnings", [])
        data.setdefault("completed_panel_ids", list(data.get("panel_ids", [])))
        data.setdefault("stopped_at_panel_id", None)
        data.setdefault("ambient_completed", True)

        return CalibrationResult(**data)

    # =========================
    # Logging
    # =========================

    def _log(self, message: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        line = f"[{timestamp}] {message}"

        if self.log_callback:
            self.log_callback(line)
