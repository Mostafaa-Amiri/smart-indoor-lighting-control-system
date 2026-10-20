import json
import os
import time
import threading

import cv2
import numpy as np
import paho.mqtt.client as mqtt
import requests


CAMERA_URL = "http://192.168.1.78/image/camera.jpg"

MQTT_HOST = "192.168.1.77"
MQTT_PORT = 1883
OCCUPANCY_TOPIC = "occupancy/zones"
OCCUPANCY_REQUEST_TOPIC = "occupancy/request"
MQTT_CLIENT_ID = "occupancy-camera-cpu"
MQTT_KEEPALIVE_SECONDS = 60
MQTT_RECONNECT_MIN_SECONDS = 1
MQTT_RECONNECT_MAX_SECONDS = 10

PYTORCH_MODEL_PATH = "yolov8s.pt"
OPENVINO_MODEL_PATH = "yolov8s_openvino_model"
PREFER_OPENVINO_MODEL = True
YOLO_CONFIDENCE = 0.08
YOLO_IMAGE_SIZE = 1024
YOLO_PERSON_CLASS_ID = 0
YOLO_DEVICE = "cpu"
YOLO_HALF = False
ZONE_ASSIGN_MIN_SCORE = 0.08
LOWER_BODY_TOP_RATIO = 0.60
MAX_ZONES_PER_PERSON = 2
ZONE_FULL_BODY_WEIGHT = 1.0
ZONE_LOWER_BODY_WEIGHT = 1.6
ZONE_BOTTOM_CENTER_BONUS = 0.25
ZONE_SECOND_MIN_SCORE = 0.18
ZONE_SECOND_MIN_RATIO = 0.35

DETECTION_INTERVAL_SECONDS = 1.5
CAMERA_TIMEOUT_SECONDS = 3.0
CAMERA_ERROR_REPEAT_SECONDS = 10.0
OCCUPIED_CONFIRM_SECONDS = 3.0
VACANT_CONFIRM_SECONDS = 30.0
NEIGHBOR_RELEASE_SECONDS = 90.0
PERSON_COUNT_CONFIRM_SECONDS = 3.0
PUBLISH_ONLY_ON_CHANGE = True

# OpenCV preview is useful for validating people detection and zone mapping.
SHOW_WINDOW = True
WINDOW_NAME = "Camera Presence Detection"

model = None
model_device = None
model_half = False
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Four perspective zones based on the current camera view.
ZONES = {
    "Z1": [(0, 490), (200,522), (405, 442), (670, 584), (707,707), (805,768), (155,768), (159, 684)],
    "Z2": [(0, 190), (245, 125), (305, 386), (405, 442),  (200,522), (0, 490)],
    "Z3": [(245, 125), (394, 86), (382, 0), (908, 0), (871, 431), (670, 584), (305, 386)],
    "Z4": [(908, 0), (1024, 0), (1024, 768), (805,768), (707,707), (670, 584), (871, 431)],
}

ALLOWED_ZONE_OVERLAPS = {
    "Z1": {"Z2", "Z4"},
    "Z2": {"Z1", "Z3"},
    "Z3": {"Z2", "Z4"},
    "Z4": {"Z1", "Z3"},
}


def resolve_local_path(path):
    if os.path.isabs(path):
        return path

    return os.path.join(SCRIPT_DIR, path)


def resolve_model_path():
    openvino_path = resolve_local_path(OPENVINO_MODEL_PATH)

    if PREFER_OPENVINO_MODEL and os.path.isdir(openvino_path):
        return openvino_path

    return resolve_local_path(PYTORCH_MODEL_PATH)


def resolve_yolo_runtime(model_path):
    if os.path.isdir(model_path):
        return "intel:cpu", False

    return YOLO_DEVICE, False


def get_model():
    global model, model_device, model_half

    if model is None:
        from ultralytics import YOLO

        model_path = resolve_model_path()
        model_device, model_half = resolve_yolo_runtime(model_path)
        model = YOLO(model_path)

    return model


def get_frame(session):
    response = session.get(CAMERA_URL, timeout=CAMERA_TIMEOUT_SECONDS)
    response.raise_for_status()

    img_array = np.frombuffer(response.content, dtype=np.uint8)
    frame = cv2.imdecode(img_array, cv2.IMREAD_COLOR)

    if frame is None:
        raise RuntimeError("Could not decode camera image")

    return frame


def point_inside_zone(x, y, zone_polygon):
    polygon = np.array(zone_polygon, dtype=np.int32)
    return cv2.pointPolygonTest(polygon, (float(x), float(y)), False) >= 0


def sampled_zone_overlap(person_box, zone_polygon, grid_size=6):
    x1, y1, x2, y2 = person_box

    if x2 <= x1 or y2 <= y1:
        return 0.0

    inside = 0
    total = 0

    for ix in range(grid_size):
        x = x1 + (ix + 0.5) * (x2 - x1) / grid_size

        for iy in range(grid_size):
            y = y1 + (iy + 0.5) * (y2 - y1) / grid_size
            total += 1

            if point_inside_zone(x, y, zone_polygon):
                inside += 1

    return inside / total if total else 0.0


def lower_body_box(person_box):
    x1, y1, x2, y2 = person_box
    lower_y1 = int(y1 + (y2 - y1) * LOWER_BODY_TOP_RATIO)

    return x1, lower_y1, x2, y2


def zone_scores_for_box(region_box):
    scores = {}

    for zone_name, zone_polygon in ZONES.items():
        score = sampled_zone_overlap(region_box, zone_polygon)

        scores[zone_name] = score

    return scores


def zone_scores_for_person(person_box):
    x1, _y1, x2, y2 = person_box
    bottom_center_x = int((x1 + x2) / 2)
    bottom_center_y = int(y2)
    full_body_scores = zone_scores_for_box(person_box)
    lower_scores = zone_scores_for_box(lower_body_box(person_box))
    scores = {}

    for zone_name, zone_polygon in ZONES.items():
        full_score = full_body_scores.get(zone_name, 0.0)
        lower_score = lower_scores.get(zone_name, 0.0)
        score = (
            full_score * ZONE_FULL_BODY_WEIGHT
            + lower_score * ZONE_LOWER_BODY_WEIGHT
        )

        if point_inside_zone(bottom_center_x, bottom_center_y, zone_polygon):
            score += ZONE_BOTTOM_CENTER_BONUS

        scores[zone_name] = score

    return scores


def zones_can_overlap(zone_a, zone_b):
    return (
        zone_b in ALLOWED_ZONE_OVERLAPS.get(zone_a, set())
        and zone_a in ALLOWED_ZONE_OVERLAPS.get(zone_b, set())
    )


def select_valid_zones(scores):
    candidates = {
        zone_name: score
        for zone_name, score in scores.items()
        if score >= ZONE_ASSIGN_MIN_SCORE
    }

    if not candidates:
        return [], 0.0

    sorted_candidates = sorted(
        candidates.items(),
        key=lambda item: item[1],
        reverse=True,
    )
    primary_zone, primary_score = sorted_candidates[0]
    selected_zones = [primary_zone]
    selected_score = primary_score

    if MAX_ZONES_PER_PERSON >= 2:
        second_required_score = max(
            ZONE_SECOND_MIN_SCORE,
            primary_score * ZONE_SECOND_MIN_RATIO,
        )

        for zone_name, score in sorted_candidates[1:]:
            if (
                zones_can_overlap(primary_zone, zone_name)
                and score >= second_required_score
            ):
                selected_zones.append(zone_name)
                selected_score += score
                break

    return list(selected_zones[:MAX_ZONES_PER_PERSON]), selected_score


def find_zones_for_person(person_box):
    return select_valid_zones(zone_scores_for_person(person_box))


def format_zone_label(zone_names):
    if not zone_names:
        return None

    return "+".join(zone_names)


def build_occupancy(frame, draw=False):
    yolo_model = get_model()
    display_frame = frame if draw else None
    occupied = {zone_name: False for zone_name in ZONES}
    persons_per_zone = {zone_name: 0 for zone_name in ZONES}
    person_count = 0

    results = yolo_model(
        frame,
        conf=YOLO_CONFIDENCE,
        imgsz=YOLO_IMAGE_SIZE,
        classes=[YOLO_PERSON_CLASS_ID],
        device=model_device,
        half=model_half,
        verbose=False,
    )

    for result in results:
        for box in result.boxes:
            cls_id = int(box.cls[0])
            cls_name = yolo_model.names[cls_id]

            if cls_name != "person":
                continue

            confidence = float(box.conf[0])
            person_box = tuple(map(int, box.xyxy[0]))
            assigned_zones, _score = find_zones_for_person(person_box)
            person_count += 1

            for assigned_zone in assigned_zones:
                occupied[assigned_zone] = True
                persons_per_zone[assigned_zone] += 1

            if draw:
                draw_person(display_frame, person_box, confidence, format_zone_label(assigned_zones))

    if draw:
        draw_zones(display_frame, occupied)

    return occupied, persons_per_zone, person_count, display_frame


def draw_person(frame, person_box, confidence, assigned_zone):
    x1, y1, x2, y2 = person_box
    label = f"person {confidence:.2f}"

    if assigned_zone is not None:
        label = f"{label} -> {assigned_zone}"

    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
    cv2.putText(
        frame,
        label,
        (x1, max(y1 - 8, 20)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (0, 255, 0),
        2,
    )


def draw_zones(frame, occupied):
    for zone_name, zone_polygon in ZONES.items():
        color = (0, 0, 255) if occupied[zone_name] else (255, 0, 0)
        status = "occupied" if occupied[zone_name] else "free"
        polygon = np.array(zone_polygon, dtype=np.int32)
        label_x, label_y = polygon.mean(axis=0).astype(int)

        cv2.polylines(frame, [polygon], isClosed=True, color=color, thickness=3)
        cv2.putText(
            frame,
            f"{zone_name}: {status}",
            (max(10, label_x - 60), max(35, label_y)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            color,
            2,
        )


def init_stable_zone_state():
    now = time.monotonic()

    return {
        zone_name: {
            "stable": False,
            "candidate": False,
            "candidate_since": now,
            "changed_at": now,
            "neighbor_hold_since": None,
        }
        for zone_name in ZONES
    }


def init_person_count_state():
    now = time.monotonic()

    return {
        "stable": None,
        "candidate": None,
        "candidate_since": now,
    }


def update_stable_person_count(raw_person_count, count_state):
    now = time.monotonic()
    raw_count = int(raw_person_count)

    if count_state["stable"] is None:
        count_state["stable"] = raw_count
        count_state["candidate"] = raw_count
        count_state["candidate_since"] = now
        return raw_count

    if raw_count != count_state["candidate"]:
        count_state["candidate"] = raw_count
        count_state["candidate_since"] = now

    if (
        raw_count != count_state["stable"]
        and (now - count_state["candidate_since"]) >= PERSON_COUNT_CONFIRM_SECONDS
    ):
        count_state["stable"] = raw_count

    return int(count_state["stable"])


def has_raw_occupied_neighbor(zone_name, raw_occupied):
    return any(
        bool(raw_occupied.get(neighbor_zone, False))
        for neighbor_zone in ALLOWED_ZONE_OVERLAPS.get(zone_name, set())
    )


def effective_zone_value(
    zone_name,
    raw_occupied,
    stable_state,
    now,
    allow_neighbor_hold,
):
    raw_value = bool(raw_occupied.get(zone_name, False))
    state = stable_state[zone_name]

    if raw_value:
        state["neighbor_hold_since"] = None
        return True

    if (
        not allow_neighbor_hold
        or not state["stable"]
        or not has_raw_occupied_neighbor(zone_name, raw_occupied)
    ):
        state["neighbor_hold_since"] = None
        return False

    if state["neighbor_hold_since"] is None:
        state["neighbor_hold_since"] = now

    return (now - state["neighbor_hold_since"]) < NEIGHBOR_RELEASE_SECONDS


def update_stable_occupancy(
    raw_occupied,
    stable_person_count,
    previous_stable_person_count,
    stable_state,
):
    now = time.monotonic()
    stable_occupied = {}
    stable_labels = {}
    allow_neighbor_hold = (
        previous_stable_person_count is not None
        and int(stable_person_count) == int(previous_stable_person_count)
    )

    for zone_name in ZONES:
        raw_value = effective_zone_value(
            zone_name,
            raw_occupied,
            stable_state,
            now,
            allow_neighbor_hold,
        )
        state = stable_state[zone_name]

        if raw_value != state["candidate"]:
            state["candidate"] = raw_value
            state["candidate_since"] = now

        required_seconds = (
            OCCUPIED_CONFIRM_SECONDS
            if raw_value
            else VACANT_CONFIRM_SECONDS
        )

        if (
            raw_value != state["stable"]
            and (now - state["candidate_since"]) >= required_seconds
        ):
            state["stable"] = raw_value
            state["changed_at"] = now

        stable_value = bool(state["stable"])
        stable_occupied[zone_name] = stable_value
        stable_labels[zone_name] = (
            "occupied stable"
            if stable_value
            else "unoccupied stable"
        )

    return stable_occupied, stable_labels


latest_occupancy_payload = None
latest_occupancy_lock = None


def publish_occupancy_payload(mqtt_client, payload):
    result = mqtt_client.publish(
        OCCUPANCY_TOPIC,
        json.dumps(payload, separators=(",", ":")),
        qos=0,
        retain=True,
    )

    if result.rc != mqtt.MQTT_ERR_SUCCESS:
        print(f"MQTT publish failed: rc={result.rc}")
        return False

    return True


def build_occupancy_payload(
    occupied,
    persons_per_zone,
    person_count,
    raw_occupied,
    raw_persons_per_zone,
    raw_person_count,
    stable_labels,
    request_id=None,
):
    payload = {
        "occupied": occupied,
        "persons_per_zone": persons_per_zone,
        "person_count": person_count,
        "raw_occupied": raw_occupied,
        "raw_persons_per_zone": raw_persons_per_zone,
        "raw_person_count": raw_person_count,
        "stable": stable_labels,
        "timestamp": time.strftime("%H:%M:%S"),
    }

    if request_id is not None:
        payload["request_id"] = request_id

    return payload


def publish_occupancy(
    mqtt_client,
    occupied,
    persons_per_zone,
    person_count,
    raw_occupied,
    raw_persons_per_zone,
    raw_person_count,
    stable_labels,
):
    payload = build_occupancy_payload(
        occupied,
        persons_per_zone,
        person_count,
        raw_occupied,
        raw_persons_per_zone,
        raw_person_count,
        stable_labels,
    )

    return publish_occupancy_payload(mqtt_client, payload)


def on_mqtt_message(client, _userdata, msg):
    global latest_occupancy_payload

    if msg.topic != OCCUPANCY_REQUEST_TOPIC:
        return

    request_id = None

    try:
        data = json.loads(msg.payload.decode("utf-8", errors="replace"))
        if isinstance(data, dict):
            request_id = data.get("request_id")
    except Exception:
        request_id = None

    if latest_occupancy_lock is None:
        payload = None
    else:
        with latest_occupancy_lock:
            payload = dict(latest_occupancy_payload) if latest_occupancy_payload else None

    if payload is None:
        payload = build_occupancy_payload(
            occupied={zone_name: False for zone_name in ZONES},
            persons_per_zone={zone_name: 0 for zone_name in ZONES},
            person_count=0,
            raw_occupied={zone_name: False for zone_name in ZONES},
            raw_persons_per_zone={zone_name: 0 for zone_name in ZONES},
            raw_person_count=0,
            stable_labels={zone_name: "unoccupied stable" for zone_name in ZONES},
            request_id=request_id,
        )
    else:
        payload["request_id"] = request_id
        payload["timestamp"] = time.strftime("%H:%M:%S")

    publish_occupancy_payload(client, payload)


def occupancy_state(
    occupied,
    persons_per_zone,
    person_count,
    raw_occupied,
    raw_persons_per_zone,
    raw_person_count,
):
    return (
        tuple(sorted(occupied.items())),
        tuple(sorted(persons_per_zone.items())),
        int(person_count),
        tuple(sorted(raw_occupied.items())),
        tuple(sorted(raw_persons_per_zone.items())),
        int(raw_person_count),
    )


def should_publish(current_state, previous_state):
    if not PUBLISH_ONLY_ON_CHANGE:
        return True

    return current_state != previous_state


def sleep_until_next_cycle(cycle_started):
    elapsed = time.monotonic() - cycle_started
    remaining = DETECTION_INTERVAL_SECONDS - elapsed

    if remaining > 0:
        time.sleep(remaining)


def on_mqtt_connect(_client, _userdata, _flags, rc):
    if rc == 0:
        print("MQTT connected.")
        _client.subscribe(OCCUPANCY_REQUEST_TOPIC, qos=0)
    else:
        print(f"MQTT connection failed: rc={rc}")


def on_mqtt_disconnect(_client, _userdata, rc):
    if rc == 0:
        print("MQTT disconnected cleanly.")
    else:
        print(f"MQTT disconnected unexpectedly: rc={rc}. Reconnect will be attempted.")


def log_camera_error(exc, error_state):
    now = time.monotonic()
    message = str(exc)

    if (
        message != error_state["message"]
        or (now - error_state["last_print"]) >= CAMERA_ERROR_REPEAT_SECONDS
    ):
        print(f"Camera error: {message}")
        error_state["message"] = message
        error_state["last_print"] = now


def main():
    global latest_occupancy_lock, latest_occupancy_payload

    session = requests.Session()
    session.headers.update({"Connection": "keep-alive"})

    mqtt_client = mqtt.Client(client_id=MQTT_CLIENT_ID)
    mqtt_client.on_connect = on_mqtt_connect
    mqtt_client.on_disconnect = on_mqtt_disconnect
    mqtt_client.on_message = on_mqtt_message
    mqtt_client.reconnect_delay_set(
        min_delay=MQTT_RECONNECT_MIN_SECONDS,
        max_delay=MQTT_RECONNECT_MAX_SECONDS,
    )
    mqtt_client.connect(MQTT_HOST, MQTT_PORT, MQTT_KEEPALIVE_SECONDS)
    mqtt_client.subscribe(OCCUPANCY_REQUEST_TOPIC, qos=0)
    mqtt_client.loop_start()

    previous_state = None
    previous_stable_person_count = None
    person_count_state = init_person_count_state()
    stable_state = init_stable_zone_state()
    camera_error_state = {"message": None, "last_print": 0.0}
    latest_occupancy_lock = threading.Lock()

    print("YOLO occupancy detection started.")
    print(f"Detection interval: {DETECTION_INTERVAL_SECONDS:.1f} seconds")
    print(f"YOLO model: {resolve_model_path()}, image size: {YOLO_IMAGE_SIZE}")
    print("YOLO CPU runtime will initialize on the first camera frame.")
    print(f"Publish only on change: {PUBLISH_ONLY_ON_CHANGE}")
    print(f"Publishing MQTT occupancy to: {OCCUPANCY_TOPIC}")

    try:
        while True:
            cycle_started = time.monotonic()

            try:
                frame = get_frame(session)
                raw_occupied, raw_persons_per_zone, raw_person_count, display_frame = build_occupancy(
                    frame,
                    draw=SHOW_WINDOW,
                )
            except Exception as exc:
                log_camera_error(exc, camera_error_state)
                sleep_until_next_cycle(cycle_started)
                continue

            stable_person_count = update_stable_person_count(
                raw_person_count,
                person_count_state,
            )
            occupied, stable_labels = update_stable_occupancy(
                raw_occupied,
                stable_person_count,
                previous_stable_person_count,
                stable_state,
            )
            previous_stable_person_count = stable_person_count
            persons_per_zone = {
                zone_name: raw_persons_per_zone.get(zone_name, 0)
                if occupied.get(zone_name, False)
                else 0
                for zone_name in ZONES
            }
            person_count = raw_person_count

            current_state = occupancy_state(
                occupied,
                persons_per_zone,
                person_count,
                raw_occupied,
                raw_persons_per_zone,
                raw_person_count,
            )

            payload = build_occupancy_payload(
                occupied,
                persons_per_zone,
                person_count,
                raw_occupied,
                raw_persons_per_zone,
                raw_person_count,
                stable_labels,
            )

            with latest_occupancy_lock:
                latest_occupancy_payload = payload

            if should_publish(current_state, previous_state):
                published = publish_occupancy_payload(mqtt_client, payload)

                if published:
                    previous_state = current_state
                    print({
                        "occupied": occupied,
                        "persons_per_zone": persons_per_zone,
                        "person_count": person_count,
                        "raw_occupied": raw_occupied,
                        "raw_person_count": raw_person_count,
                    })

            if SHOW_WINDOW:
                cv2.imshow(WINDOW_NAME, display_frame)
                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    break

            sleep_until_next_cycle(cycle_started)

    except KeyboardInterrupt:
        print("Stopping occupancy detection.")
    finally:
        mqtt_client.loop_stop()
        mqtt_client.disconnect()
        session.close()

        if SHOW_WINDOW:
            cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
