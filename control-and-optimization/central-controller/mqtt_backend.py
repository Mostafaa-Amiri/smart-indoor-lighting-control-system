# mqtt_backend.py

import json
import time
import queue
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

import paho.mqtt.client as mqtt


PANEL_STALE_SECONDS = 30.0
SENSOR_STALE_SECONDS = 30.0


# =========================
# Data models
# =========================

@dataclass
class PanelState:
    id: str
    ip: Optional[str] = None
    chip: Optional[int] = None
    ota: Optional[str] = None
    device_type: Optional[str] = None

    temp_c: Optional[float] = None
    temp_present: Optional[bool] = None
    temp_mode: Optional[str] = None
    temp_interval_ms: Optional[int] = None
    last_temp: float = 0.0

    freq: Optional[int] = None

    # Keep list format for compatibility with main.py.
    # If ESP publishes one scalar duty, backend stores it as [d, d, d, d].
    duty: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0, 0.0])
    target_duty: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0, 0.0])

    transition: Optional[str] = None
    step_ms: Optional[int] = None
    ramping: bool = False
    target_reached: bool = True
    last_event: Optional[str] = None

    last_seen: float = 0.0
    last_applied: float = 0.0
    last_cmd_id: Optional[int] = None

    online: bool = True


@dataclass
class SensorState:
    id: str
    ip: Optional[str] = None
    chip: Optional[int] = None
    ota: Optional[str] = None
    sensor_type: Optional[str] = None

    raw_lux: Optional[float] = None
    lux: Optional[float] = None

    last_seen: float = 0.0
    last_lux: float = 0.0

    online: bool = True


# =========================
# Sensor calibration
# =========================

SENSOR_CALIBRATION = {
    "esp-6720EA": {"a": 1.040783, "b": 1.486988},
    "esp-66B5E2": {"a": 1.040783, "b": 1.486988},
    "esp-4A7D20": {"a": 1.040783, "b": 1.486988},
    "esp-680DBB": {"a": 1.040783, "b": 1.486988},
    "esp-684212": {"a": 1.040783, "b": 1.486988},
    "esp-67A642": {"a": 1.040783, "b": 1.486988},
    "esp-67D0E0": {"a": 1.040783, "b": 1.486988},
    "esp-67A5B2": {"a": 1.040783, "b": 1.486988},
}


def calibrate_lux(sensor_id: str, raw_lux: Optional[float]) -> Optional[float]:
    if raw_lux is None:
        return None

    cfg = SENSOR_CALIBRATION.get(sensor_id, {"a": 1.0, "b": 0.0})
    corrected = cfg["a"] * raw_lux + cfg["b"]
    corrected = max(0.0, corrected)

    return round(corrected, 2)


# =========================
# MQTT Backend
# =========================

class MQTTBackend:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 1883,
        client_id: Optional[str] = None,
        keepalive: int = 60,
    ):
        self.host = host
        self.port = port
        self.keepalive = keepalive

        if client_id is None:
            client_id = f"central-control-{int(time.time())}"

        self.client_id = client_id

        self.client = mqtt.Client(
            client_id=self.client_id,
            protocol=mqtt.MQTTv311,
            clean_session=True,
        )

        # Reliability improvements
        self.client.reconnect_delay_set(min_delay=1, max_delay=10)
        self.client.max_inflight_messages_set(20)
        self.client.max_queued_messages_set(200)

        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message

        self.panels: Dict[str, PanelState] = {}
        self.sensors: Dict[str, SensorState] = {}

        self.occupancy: Optional[dict] = None
        self.radar_presence: Dict[str, dict] = {}
        self.radar_presence_info: Dict[str, dict] = {}
        self._cmd_counter = 0

        # Shared by every Streamlit browser session using this cached backend.
        # Only the newest auto-control generation is allowed to publish duties.
        self._auto_control_lock = threading.Lock()
        self._auto_control_generation = 0
        self._active_auto_control_generation: Optional[int] = None

        self.event_queue: "queue.Queue[dict]" = queue.Queue(maxsize=1000)
        self.logs: List[str] = []

        self.connected = False
        self._started = False
        self._lock = threading.RLock()

    # =========================
    # Lifecycle
    # =========================

    def start(self) -> None:
        """
        Start MQTT connection once.
        Important: in Streamlit, call this from st.cache_resource.
        """
        if self._started:
            return

        self.client.connect_async(self.host, self.port, keepalive=self.keepalive)
        self.client.loop_start()

        self._started = True
        self._log(f"MQTT backend started: {self.host}:{self.port}")

    def stop(self) -> None:
        if not self._started:
            return

        self.client.loop_stop()
        self.client.disconnect()
        self._started = False
        self.connected = False
        self._log("MQTT backend stopped")

    # =========================
    # MQTT callbacks
    # =========================

    def _on_connect(self, client, userdata, flags, rc):
        self.connected = rc == 0

        if rc == 0:
            self._log("MQTT connected")

            subscriptions = [
                # Panels
                ("lights/announce", 1),
                ("lights/panel/+/status", 1),
                ("lights/panel/+/tele", 0),
                ("lights/panel/+/applied", 0),
                ("lights/panel/+/ack", 1),

                # Legacy old panel LWT support
                ("lights/offline/+", 1),

                # GY30 sensors
                ("gy30/+/announce", 1),
                ("gy30/+/status", 1),
                ("gy30/+/lux_avg", 0),

                # Occupancy
                ("occupancy/zones", 0),
                ("presence/+/state", 0),
                ("presence/+/info", 0),
            ]

            for topic, qos in subscriptions:
                client.subscribe(topic, qos)

            self._log("MQTT subscriptions registered")
        else:
            self._log(f"MQTT connection failed, rc={rc}")

    def _on_disconnect(self, client, userdata, rc):
        self.connected = False
        self._log(f"MQTT disconnected, rc={rc}")

    def _on_message(self, client, userdata, msg):
        topic = msg.topic
        payload_raw = msg.payload.decode("utf-8", errors="replace")

        event = {
            "time": time.time(),
            "topic": topic,
            "payload": payload_raw,
        }

        self._put_event_safe(event)

        try:
            self._process_message(topic, payload_raw)
        except Exception as exc:
            self._log(f"ERROR processing {topic}: {exc}")

    # =========================
    # Message processing
    # =========================

    def _process_message(self, topic: str, payload_raw: str) -> None:
        now = time.time()

        # ---------- Occupancy ----------
        if topic == "occupancy/zones":
            data = self._json_or_empty(payload_raw)
            data["_received_at"] = now

            with self._lock:
                self.occupancy = data

            self._log(f"Occupancy updated: {data}")
            return

        # ---------- Radar presence nodes ----------
        # presence/<node_id>/state = {"ip":"192.168.1.91","z1":1,"z2":0}
        if topic.startswith("presence/") and topic.endswith("/state"):
            parts = topic.split("/")
            if len(parts) < 3:
                return

            node_id = parts[1]
            data = self._json_or_empty(payload_raw)
            data["id"] = data.get("id") or node_id
            data["_received_at"] = now

            with self._lock:
                self.radar_presence[node_id] = data

            self._log(f"Radar presence updated: {node_id} {data}")
            return

        # presence/<node_id>/info = optional diagnostics/config
        if topic.startswith("presence/") and topic.endswith("/info"):
            parts = topic.split("/")
            if len(parts) < 3:
                return

            node_id = parts[1]
            data = self._json_or_empty(payload_raw)
            data["id"] = data.get("id") or node_id
            data["_received_at"] = now

            with self._lock:
                self.radar_presence_info[node_id] = data

            self._log(f"Radar presence info: {node_id} {data}")
            return

        # ---------- Panel announce ----------
        if topic == "lights/announce":
            data = self._json_or_empty(payload_raw)
            panel_id = data.get("id")

            if not panel_id:
                return

            with self._lock:
                panel = self.panels.get(panel_id, PanelState(id=panel_id))
                panel.ip = data.get("ip", panel.ip)
                panel.chip = data.get("chip", panel.chip)
                panel.ota = data.get("ota", panel.ota)
                panel.device_type = data.get("type", panel.device_type)

                if "temp" in data:
                    panel.temp_present = bool(data.get("temp"))

                panel.last_seen = now
                panel.online = True
                self.panels[panel_id] = panel

            self._log(f"Panel announced: {panel_id}")
            return

        # ---------- New panel status ----------
        # lights/panel/<id>/status = online/offline
        if topic.startswith("lights/panel/") and topic.endswith("/status"):
            panel_id = topic.split("/")[2]
            status_text = self._status_from_payload(payload_raw)
            is_online = status_text == "online"

            with self._lock:
                panel = self.panels.get(panel_id, PanelState(id=panel_id))
                panel.online = is_online
                panel.last_seen = now
                self.panels[panel_id] = panel

            self._log(f"Panel status: {panel_id} = {status_text}")
            return

        # ---------- Legacy old panel offline ----------
        # lights/offline/<id>
        if topic.startswith("lights/offline/"):
            panel_id = topic.split("/")[-1]

            with self._lock:
                panel = self.panels.get(panel_id, PanelState(id=panel_id))
                panel.online = False
                panel.last_seen = now
                self.panels[panel_id] = panel

            self._log(f"Panel offline legacy: {panel_id}")
            return

        # ---------- Panel telemetry ----------
        # lights/panel/<id>/tele
        if topic.startswith("lights/panel/") and topic.endswith("/tele"):
            panel_id = topic.split("/")[2]
            data = self._json_or_empty(payload_raw)

            with self._lock:
                panel = self.panels.get(panel_id, PanelState(id=panel_id))

                if "tC" in data:
                    panel.temp_c = self._to_float_or_none(data.get("tC"))
                    panel.last_temp = now

                if "temp_present" in data:
                    panel.temp_present = bool(data.get("temp_present"))

                if "temp_mode" in data:
                    panel.temp_mode = str(data.get("temp_mode"))

                if "temp_interval_ms" in data:
                    panel.temp_interval_ms = self._to_int_or_none(data.get("temp_interval_ms"))

                if "freq" in data:
                    panel.freq = self._to_int_or_none(data.get("freq"))

                if "duty" in data:
                    panel.duty = self._normalize_duty(data.get("duty"), panel.duty)

                if "target_duty" in data:
                    panel.target_duty = self._normalize_duty(data.get("target_duty"), panel.target_duty)

                if "event" in data:
                    panel.last_event = str(data.get("event"))

                panel.last_seen = now
                panel.online = True
                self.panels[panel_id] = panel

            self._log(
                f"Panel tele: {panel_id} "
                f"temp={data.get('tC')} mode={data.get('temp_mode')} "
                f"reason={data.get('reason')} event={data.get('event')}"
            )
            return

        # ---------- Panel applied ----------
        # lights/panel/<id>/applied
        if topic.startswith("lights/panel/") and topic.endswith("/applied"):
            panel_id = topic.split("/")[2]
            data = self._json_or_empty(payload_raw)

            with self._lock:
                panel = self.panels.get(panel_id, PanelState(id=panel_id))

                if "freq" in data:
                    panel.freq = self._to_int_or_none(data.get("freq"))

                if "duty" in data:
                    panel.duty = self._normalize_duty(data.get("duty"), panel.duty)

                if "target_duty" in data:
                    panel.target_duty = self._normalize_duty(data.get("target_duty"), panel.target_duty)

                if "transition" in data:
                    panel.transition = str(data.get("transition"))

                if "step_ms" in data:
                    panel.step_ms = self._to_int_or_none(data.get("step_ms"))

                if "ramping" in data:
                    panel.ramping = bool(data.get("ramping"))

                if "target_reached" in data:
                    panel.target_reached = bool(data.get("target_reached"))

                if "event" in data:
                    panel.last_event = str(data.get("event"))

                if "cmd_id" in data:
                    panel.last_cmd_id = self._to_int_or_none(data.get("cmd_id"))

                panel.last_seen = now
                panel.last_applied = now
                panel.online = True
                self.panels[panel_id] = panel

            self._log(
                f"Panel applied: {panel_id} event={data.get('event')} "
                f"duty={data.get('duty')} target={data.get('target_duty')} "
                f"transition={data.get('transition')} step_ms={data.get('step_ms')} "
                f"ramping={data.get('ramping')} cmd_id={data.get('cmd_id')}"
            )
            return

        # ---------- Sensor announce ----------
        # gy30/<id>/announce
        if topic.startswith("gy30/") and topic.endswith("/announce"):
            sensor_id = topic.split("/")[1]
            data = self._json_or_empty(payload_raw)

            with self._lock:
                sensor = self.sensors.get(sensor_id, SensorState(id=sensor_id))
                sensor.ip = data.get("ip", sensor.ip)
                sensor.chip = data.get("chip", sensor.chip)
                sensor.ota = data.get("ota", sensor.ota)
                sensor.sensor_type = data.get("sensor", sensor.sensor_type)
                sensor.last_seen = now
                sensor.online = True
                self.sensors[sensor_id] = sensor

            self._log(f"Sensor announced: {sensor_id}")
            return

        # ---------- Sensor status ----------
        # gy30/<id>/status
        if topic.startswith("gy30/") and topic.endswith("/status"):
            sensor_id = topic.split("/")[1]
            status_text = self._status_from_payload(payload_raw)

            with self._lock:
                sensor = self.sensors.get(sensor_id, SensorState(id=sensor_id))
                sensor.online = status_text == "online"
                sensor.last_seen = now
                self.sensors[sensor_id] = sensor

            self._log(f"Sensor status: {sensor_id} = {status_text}")
            return

        # ---------- Sensor lux ----------
        # gy30/<id>/lux_avg
        if topic.startswith("gy30/") and topic.endswith("/lux_avg"):
            sensor_id = topic.split("/")[1]

            raw_lux = self._to_float_or_none(payload_raw)
            corrected_lux = calibrate_lux(sensor_id, raw_lux)

            with self._lock:
                sensor = self.sensors.get(sensor_id, SensorState(id=sensor_id))
                sensor.raw_lux = raw_lux
                sensor.lux = corrected_lux
                sensor.last_seen = now
                sensor.last_lux = now
                sensor.online = True
                self.sensors[sensor_id] = sensor

            self._log(
                f"Sensor lux: {sensor_id} raw={raw_lux} corrected={corrected_lux}"
            )
            return

    # =========================
    # Publish commands
    # =========================

    def begin_auto_control(self) -> int:
        with self._auto_control_lock:
            self._auto_control_generation += 1
            self._active_auto_control_generation = self._auto_control_generation
            return self._auto_control_generation

    def stop_all_auto_control(self) -> None:
        with self._auto_control_lock:
            self._auto_control_generation += 1
            self._active_auto_control_generation = None

    def is_auto_control_active(self, generation: int) -> bool:
        with self._auto_control_lock:
            return self._active_auto_control_generation == generation

    def has_active_auto_control(self) -> bool:
        with self._auto_control_lock:
            return self._active_auto_control_generation is not None

    def finish_auto_control(self, generation: int) -> None:
        with self._auto_control_lock:
            if self._active_auto_control_generation == generation:
                self._active_auto_control_generation = None

    def send_panel_duty(
        self,
        panel_id: str,
        duty: Any,
        transition: str = "smooth",
        step_ms: Optional[int] = None,
    ) -> int:
        """
        Send one logical target duty to a panel.

        Normal usage:
            send_panel_duty(panel_id, 60)

        Advanced usage:
            send_panel_duty(panel_id, 60, transition="smooth", step_ms=80)
            send_panel_duty(panel_id, 0, transition="immediate")

        ESP behavior:
        - Single-channel ESP applies one duty to D5.
        - 4-channel temp ESP applies the same one duty to D5, D6, D7, D1.
        """

        cmd_id = self._new_cmd_id()

        duty_value = self._to_float_or_none(duty)

        if duty_value is None:
            duty_value = 0.0

        duty_value = self._clamp_float(duty_value, 0.0, 100.0)
        transition_value = self._normalize_transition(transition)

        payload = {
            "cmd_id": cmd_id,
            "duty": duty_value,
            "transition": transition_value,
        }

        step_ms_value = self._normalize_step_ms(step_ms)

        if step_ms_value is not None:
            payload["step_ms"] = step_ms_value

        topic = f"lights/panel/{panel_id}/set"
        self._publish_json(topic, payload, qos=1, retain=False)

        self._log(
            f"TX duty: {panel_id} duty={duty_value} "
            f"transition={transition_value} "
            f"step_ms={payload.get('step_ms', 'esp-default')} "
            f"cmd_id={cmd_id}"
        )

        return cmd_id

    def send_panel_frequency(self, panel_id: str, freq: int) -> int:
        cmd_id = self._new_cmd_id()

        freq_value = self._clamp_int(freq, 1, 5000)

        payload = {
            "cmd_id": cmd_id,
            "freq": freq_value,
        }

        topic = f"lights/panel/{panel_id}/assign"
        self._publish_json(topic, payload, qos=1, retain=False)

        self._log(f"TX freq: {panel_id} freq={freq_value} cmd_id={cmd_id}")
        return cmd_id

    def configure_panel_temperature(
        self,
        panel_id: str,
        temp_mode: str = "auto",
        temp_interval_s: Optional[int] = None,
        temp_interval_ms: Optional[int] = None,
    ) -> int:
        """
        Configure DS18B20 temperature behavior on panel ESP.

        temp_mode:
        - "auto": ESP publishes temperature automatically.
        - "manual": ESP sends one temperature reading and disables auto mode.
        - "off": ESP disables automatic temperature publishing.

        Normally you do not need to call this from main.py.
        It is here for future research / experiments.
        """

        cmd_id = self._new_cmd_id()

        mode = str(temp_mode).lower().strip()

        if mode not in ["auto", "manual", "off", "disabled"]:
            mode = "auto"

        payload = {
            "cmd_id": cmd_id,
            "temp_mode": mode,
        }

        if temp_interval_s is not None:
            interval_s = self._to_int_or_none(temp_interval_s)
            if interval_s is not None:
                payload["temp_interval_s"] = self._clamp_int(interval_s, 2, 3600)

        if temp_interval_ms is not None:
            interval_ms = self._to_int_or_none(temp_interval_ms)
            if interval_ms is not None:
                payload["temp_interval_ms"] = self._clamp_int(interval_ms, 2000, 3600000)

        topic = f"lights/panel/{panel_id}/set"
        self._publish_json(topic, payload, qos=1, retain=False)

        self._log(
            f"TX temp config: {panel_id} mode={mode} "
            f"interval_s={payload.get('temp_interval_s')} "
            f"interval_ms={payload.get('temp_interval_ms')} "
            f"cmd_id={cmd_id}"
        )

        return cmd_id

    def request_panel_temperature(self, panel_id: str) -> int:
        """
        Request one immediate DS18B20 temperature reading.
        Normally not needed because ESP publishes temp automatically.
        """

        cmd_id = self._new_cmd_id()

        payload = {
            "cmd_id": cmd_id,
            "temp_now": True,
        }

        topic = f"lights/panel/{panel_id}/set"
        self._publish_json(topic, payload, qos=1, retain=False)

        self._log(f"TX temp request: {panel_id} cmd_id={cmd_id}")
        return cmd_id

    def request_sensor_lux(self, sensor_id: str) -> None:
        """
        Ask one GY30 sensor to measure lux and publish gy30/<id>/lux_avg.
        """
        topic = f"gy30/{sensor_id}/get_lux"
        self.client.publish(topic, payload="1", qos=1, retain=False)
        self._log(f"TX lux request: {sensor_id}")

    def request_all_lux(self) -> None:
        with self._lock:
            sensor_ids = list(self.sensors.keys())

        for sensor_id in sensor_ids:
            self.request_sensor_lux(sensor_id)

    def request_occupancy(self) -> int:
        request_id = self._new_cmd_id()
        payload = {
            "request_id": request_id,
        }

        self._publish_json("occupancy/request", payload, qos=0, retain=False)
        self._log(f"TX occupancy request: request_id={request_id}")
        return request_id

    def set_radar_presence_config(self, node_id: str, payload: dict) -> None:
        topic = f"presence/{node_id}/set"
        self._publish_json(topic, payload, qos=1, retain=False)
        self._log(f"TX radar presence config: {node_id} {payload}")

    def wait_for_occupancy_response(
        self,
        request_id: int,
        timeout_seconds: float = 2.0,
        stop_event: Optional[threading.Event] = None,
    ) -> Optional[dict]:
        deadline = time.time() + max(0.0, float(timeout_seconds))

        while time.time() < deadline:
            if stop_event is not None and stop_event.is_set():
                return None

            with self._lock:
                occupancy = self.occupancy

                if occupancy is not None and occupancy.get("request_id") == request_id:
                    return dict(occupancy)

            time.sleep(0.05)

        with self._lock:
            return dict(self.occupancy) if self.occupancy is not None else None

    # =========================
    # Public read API for Streamlit
    # =========================

    def get_panels(self) -> Dict[str, PanelState]:
        with self._lock:
            self._mark_stale_panels_offline_locked(time.time())
            return dict(self.panels)

    def get_sensors(self) -> Dict[str, SensorState]:
        with self._lock:
            self._mark_stale_sensors_offline_locked(time.time())
            return dict(self.sensors)

    def get_occupancy(self) -> Optional[dict]:
        with self._lock:
            return self.occupancy

    def get_radar_presence(self) -> Dict[str, dict]:
        with self._lock:
            return {
                node_id: dict(data)
                for node_id, data in self.radar_presence.items()
            }

    def get_radar_presence_info(self) -> Dict[str, dict]:
        with self._lock:
            return {
                node_id: dict(data)
                for node_id, data in self.radar_presence_info.items()
            }

    def get_logs(self, limit: int = 100) -> List[str]:
        with self._lock:
            return self.logs[-limit:]

    def drain_events(self, limit: int = 200) -> List[dict]:
        events = []

        for _ in range(limit):
            try:
                events.append(self.event_queue.get_nowait())
            except queue.Empty:
                break

        return events

    # =========================
    # Helpers
    # =========================

    def _publish_json(self, topic: str, payload: dict, qos: int = 1, retain: bool = False) -> None:
        payload_raw = json.dumps(payload, separators=(",", ":"))
        result = self.client.publish(topic, payload_raw, qos=qos, retain=retain)

        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            self._log(f"MQTT publish failed: topic={topic} rc={result.rc}")

    def _json_or_empty(self, payload_raw: str) -> dict:
        try:
            data = json.loads(payload_raw)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _status_from_payload(self, payload_raw: str) -> str:
        data = self._json_or_empty(payload_raw)

        if data:
            status = data.get("status")
            if status is not None:
                return str(status).strip().lower()

        return payload_raw.strip().lower()

    def _mark_stale_panels_offline_locked(self, now: float) -> None:
        for panel in self.panels.values():
            if not panel.online or panel.last_seen <= 0:
                continue

            age = now - panel.last_seen

            if age > PANEL_STALE_SECONDS:
                panel.online = False
                self._log(f"Panel stale timeout: {panel.id} offline after {age:.1f}s")

    def _mark_stale_sensors_offline_locked(self, now: float) -> None:
        for sensor in self.sensors.values():
            if not sensor.online or sensor.last_seen <= 0:
                continue

            age = now - sensor.last_seen

            if age > SENSOR_STALE_SECONDS:
                sensor.online = False
                self._log(f"Sensor stale timeout: {sensor.id} offline after {age:.1f}s")

    def _normalize_duty(self, value: Any, fallback: List[float]) -> List[float]:
        if isinstance(value, list):
            values = value[:4]
            while len(values) < 4:
                values.append(values[-1] if values else 0.0)

            return [self._clamp_float(v, 0.0, 100.0) for v in values]

        number = self._to_float_or_none(value)

        if number is not None:
            number = self._clamp_float(number, 0.0, 100.0)
            return [number, number, number, number]

        return fallback

    def _normalize_transition(self, transition: Any) -> str:
        value = str(transition).lower().strip()

        if value in ["immediate", "fast", "direct", "instant"]:
            return "immediate"

        return "smooth"

    def _normalize_step_ms(self, step_ms: Optional[Any]) -> Optional[int]:
        if step_ms is None:
            return None

        value = self._to_int_or_none(step_ms)

        if value is None:
            return None

        return self._clamp_int(value, 10, 500)

    def _to_float_or_none(self, value: Any) -> Optional[float]:
        try:
            return float(value)
        except Exception:
            return None

    def _to_int_or_none(self, value: Any) -> Optional[int]:
        try:
            return int(value)
        except Exception:
            return None

    def _clamp_float(self, value: Any, low: float, high: float) -> float:
        try:
            x = float(value)
        except Exception:
            x = low

        return max(low, min(high, x))

    def _clamp_int(self, value: Any, low: int, high: int) -> int:
        try:
            x = int(value)
        except Exception:
            x = low

        return max(low, min(high, x))

    def _new_cmd_id(self) -> int:
        return int(time.time() * 1000) % 2_147_483_647

    def _put_event_safe(self, event: dict) -> None:
        try:
            self.event_queue.put_nowait(event)
        except queue.Full:
            try:
                self.event_queue.get_nowait()
                self.event_queue.put_nowait(event)
            except queue.Empty:
                pass

    def _log(self, text: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        line = f"[{stamp}] {text}"

        with self._lock:
            self.logs.append(line)
            if len(self.logs) > 500:
                self.logs = self.logs[-500:]
