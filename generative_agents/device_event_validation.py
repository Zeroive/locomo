"""设备事件生成中的时间、格式化与 LLM 结果校验服务。"""

import json
import logging
from datetime import datetime

from generative_agents.device_event_domain import (
    DEVICE_STATES,
    PERSON_ROOM_STATUS_SCHEMA,
    PERSON_STATUS_ALIASES,
    TIME_PERIODS,
)

def parse_hhmm_to_minutes(value):
    if not isinstance(value, str) or ':' not in value:
        return None
    try:
        hour, minute = [int(part) for part in value.split(':')[:2]]
    except ValueError:
        return None
    if hour == 24 and minute == 0:
        return 1440
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return hour * 60 + minute


def expand_time_range_to_segments(time_range):
    if not isinstance(time_range, dict):
        return [(0, 1439)]
    start = parse_hhmm_to_minutes(time_range.get('start'))
    end = parse_hhmm_to_minutes(time_range.get('end'))
    if start is None or end is None:
        return [(0, 1439)]
    if end == 1440:
        end = 1439
    if start <= end:
        return [(start, end)]
    return [(start, 1439), (0, end)]


def get_time_period_options(time_range):
    segments = expand_time_range_to_segments(time_range)
    options = []
    for period in TIME_PERIODS:
        if any(max(start, period["start_min"]) <= min(end, period["end_min"]) for start, end in segments):
            options.append(period)
    return options or TIME_PERIODS


def format_time_period_options(time_range):
    options = get_time_period_options(time_range)
    return "\n".join(
        f"- {item['label']}({item['start']}-{item['end']}), time_des={item['slug']}"
        for item in options
    )


def scenario_time_in_period_options(scenario_time, time_range, episode_date=None):
    try:
        dt = datetime.fromisoformat(str(scenario_time).replace('Z', '+00:00'))
    except ValueError:
        return False
    if episode_date is not None and dt.date() != episode_date:
        return False
    minute_of_day = dt.hour * 60 + dt.minute
    return any(
        item["start_min"] <= minute_of_day <= item["end_min"]
        for item in get_time_period_options(time_range)
    )


def normalize_llm_scenario_time(scenario_time, fallback_time, time_range, scenario, episode_date):
    if scenario_time and scenario_time_in_period_options(scenario_time, time_range, episode_date):
        return scenario_time
    if scenario_time:
        logging.warning(
            "LLM scenario_time out of allowed period for %s/%s: %s; using fallback %s",
            scenario,
            episode_date,
            scenario_time,
            fallback_time,
        )
    return fallback_time


def get_time_description(timestamp):
    hour = timestamp.hour
    if 6 <= hour <= 8:
        return "early_morning"
    if 9 <= hour <= 11:
        return "morning"
    if 12 <= hour <= 13:
        return "noon"
    if 14 <= hour <= 17:
        return "afternoon"
    if 18 <= hour <= 23:
        return "evening"
    return "late_night"


def build_episode_id(subject_id, scenario, episode_date, event_time=None, time_range=None):
    """
    生成 episode_id: {subject_id}_{time_des}_{scenario}_{YYYYMMDD}_{HHMM}
    """
    timestamp = event_time
    if isinstance(timestamp, str):
        try:
            timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        except ValueError:
            timestamp = None
    if timestamp is None:
        start_time = (time_range or {}).get('start') if isinstance(time_range, dict) else None
        if isinstance(start_time, str) and ':' in start_time:
            try:
                hour, minute = [int(part) for part in start_time.split(':')[:2]]
                timestamp = datetime.combine(episode_date, datetime.min.time()).replace(
                    hour=hour % 24,
                    minute=minute,
                )
            except ValueError:
                timestamp = None
    if timestamp is None:
        timestamp = datetime.combine(episode_date, datetime.min.time())
    time_des = get_time_description(timestamp)
    return f"{subject_id}_{time_des}_{scenario}_{episode_date.strftime('%Y%m%d')}_{timestamp.strftime('%H%M')}"


def format_previous_scenario_descriptions(descriptions):
    if not descriptions:
        return "无"
    lines = []
    for item in descriptions:
        lines.append(
            "- {time} {scenario}/{subject_id}: {description}".format(
                time=item.get('scenario_time', ''),
                scenario=item.get('scenario', ''),
                subject_id=item.get('subject_id', ''),
                description=item.get('daily_state_description', '')
            )
        )
    return '\n'.join(lines)


def format_allowed_events_info(primary_events, allowed_events, default_subject):
    """
    将主事件和可选相关事件格式化进 LLM prompt。
    """
    lines = []
    primary_keys = {
        (event.get('event_type'), event.get('predicate'), event.get('object_id'))
        for event in primary_events
    }
    for idx, event in enumerate(allowed_events, start=1):
        required = "必选主事件" if (
            event.get('event_type'), event.get('predicate'), event.get('object_id')
        ) in primary_keys else "按当天状态可选"
        lines.append(
            "- {idx}. {required}: subject_id={subject_id}, predicate={predicate}, object_id={object_id}, "
            "event_type={event_type}, description={description}".format(
                idx=idx,
                required=required,
                subject_id=event.get('subject_id', default_subject),
                predicate=event.get('predicate', ''),
                object_id=event.get('object_id', ''),
                event_type=event.get('event_type', ''),
                description=event.get('description', '')
            )
        )
    return '\n'.join(lines) if lines else f"- 1. subject_id={default_subject}, predicate=occurred, object_id=door_main, event_type=scene_main, description=场景主要事件"


def format_candidate_event_info(event, default_subject):
    return json.dumps({
        "subject_id": event.get('subject_id', default_subject),
        "predicate": event.get('predicate', ''),
        "object_id": event.get('object_id', ''),
        "attributes": {
            "event_type": event.get('event_type', ''),
            "description": event.get('description', ''),
        }
    }, ensure_ascii=False, indent=2)


def validate_llm_state_result(result):
    if not isinstance(result, dict):
        raise ValueError(f"State description result must be a dict, got {type(result)}")
    if 'scenario_should_happen' not in result:
        raise ValueError("Missing scenario_should_happen")
    if 'daily_state_description' not in result:
        raise ValueError("Missing daily_state_description")
    return {
        "scenario_should_happen": bool(result.get('scenario_should_happen')),
        "scenario_time": result.get('scenario_time', ''),
        "skip_reason": result.get('skip_reason', ''),
        "daily_state_description": result.get('daily_state_description', ''),
        "sampled_context": result.get('sampled_context', {}),
    }


def validate_llm_event_item_result(result, candidate_event, default_subject, person_ids, available_devices, previous_events):
    if not isinstance(result, dict):
        raise ValueError(f"Event item result must be a dict, got {type(result)}")
    if not result.get('should_generate', False):
        return None
    annotated_event = result.get('annotated_event')
    if not isinstance(annotated_event, dict):
        raise ValueError("should_generate=true but annotated_event is missing")

    event = annotated_event.get('event')
    snapshot = annotated_event.get('state_snapshot')
    if not isinstance(event, dict) or not isinstance(snapshot, dict):
        raise ValueError("annotated_event must contain event and state_snapshot")

    expected_subject = candidate_event.get('subject_id', default_subject)
    expected_type = candidate_event.get('event_type', '')
    if event.get('subject_id') != expected_subject:
        raise ValueError(f"Invalid subject_id: {event.get('subject_id')}, expected {expected_subject}")
    if event.get('predicate') != candidate_event.get('predicate'):
        raise ValueError(f"Invalid predicate: {event.get('predicate')}, expected {candidate_event.get('predicate')}")
    if event.get('object_id') != candidate_event.get('object_id'):
        raise ValueError(f"Invalid object_id: {event.get('object_id')}, expected {candidate_event.get('object_id')}")
    event.setdefault('attributes', {})
    if event['attributes'].get('event_type') != expected_type:
        raise ValueError(f"Invalid event_type: {event['attributes'].get('event_type')}, expected {expected_type}")
    event['attributes'].setdefault('description', candidate_event.get('description', ''))

    if event['subject_id'] not in person_ids and event['subject_id'] not in {'home_assistant', 'system', 'visitor'}:
        raise ValueError(f"Invalid subject_id: {event['subject_id']}")
    if event['object_id'] not in available_devices:
        raise ValueError(f"Invalid object_id: {event['object_id']}")

    for key in ('timestamp', 'persons', 'devices', 'space_occupancy'):
        if key not in snapshot:
            raise ValueError(f"state_snapshot missing {key}")
    validate_person_states(snapshot, person_ids)
    validate_device_states(snapshot)
    validate_space_occupancy(snapshot)

    current_timestamp = datetime.fromisoformat(snapshot['timestamp'].replace('+08:00', ''))
    if previous_events:
        prev_timestamp = datetime.fromisoformat(
            previous_events[-1]['state_snapshot']['timestamp'].replace('+08:00', '')
        )
        if current_timestamp < prev_timestamp:
            raise ValueError(f"timestamp goes backwards: {snapshot['timestamp']}")

    return annotated_event


def validate_person_states(snapshot, person_ids):
    """
    校验 state_snapshot 中人物 location/status 是否来自预定义房间状态枚举。
    """
    persons = snapshot.get('persons')
    if not isinstance(persons, dict):
        raise ValueError("state_snapshot.persons must be a dict")

    valid_person_ids = set(person_ids)
    for person_id, person_state in persons.items():
        if person_id not in valid_person_ids and person_id != 'visitor':
            raise ValueError(f"Invalid person_id in state_snapshot: {person_id}")
        if not isinstance(person_state, dict):
            raise ValueError(f"Invalid person state for {person_id}")

        location = person_state.get('location')
        status = person_state.get('status')
        allowed_statuses = PERSON_ROOM_STATUS_SCHEMA.get(location)
        if allowed_statuses is None:
            raise ValueError(f"Invalid location for {person_id}: {location}")
        normalized_status = PERSON_STATUS_ALIASES.get((location, status), status)
        if normalized_status != status:
            logging.info(
                "Normalized person status for %s at %s: %s -> %s",
                person_id,
                location,
                status,
                normalized_status,
            )
            person_state['status'] = normalized_status
            status = normalized_status
        if status not in allowed_statuses:
            raise ValueError(
                f"Invalid status for {person_id}: {status}; "
                f"location {location} allows {', '.join(allowed_statuses)}"
            )


def validate_device_states(snapshot):
    """
    校验 state_snapshot 中设备 state 是否来自 DEVICE_STATES。
    """
    devices = snapshot.get('devices')
    if not isinstance(devices, dict):
        raise ValueError("state_snapshot.devices must be a dict")

    for device_id, device_state in devices.items():
        if not isinstance(device_state, dict):
            raise ValueError(f"Invalid device state for {device_id}")
        if device_id not in DEVICE_STATES:
            raise ValueError(f"Unknown device_id in state_snapshot: {device_id}")
        state = device_state.get('state')
        if state not in DEVICE_STATES[device_id]:
            raise ValueError(
                f"Invalid state for {device_id}: {state}; "
                f"allowed states: {', '.join(DEVICE_STATES[device_id])}"
            )


def validate_space_occupancy(snapshot):
    occupancy = snapshot.get('space_occupancy')
    if not isinstance(occupancy, dict):
        raise ValueError("state_snapshot.space_occupancy must be a dict")
    for room_id, occupants in occupancy.items():
        if not isinstance(occupants, list):
            raise ValueError(f"space_occupancy.{room_id} must be a list, got {type(occupants)}")


def build_space_occupancy_from_persons(persons):
    """
    根据 persons 的 location 推导 space_occupancy。
    """
    occupancy = {room_id: [] for room_id in PERSON_ROOM_STATUS_SCHEMA if room_id != 'outside'}
    occupancy['outside'] = []
    for person_id, person_state in persons.items():
        location = person_state.get('location')
        occupancy.setdefault(location, [])
        occupancy[location].append(person_id)
    return occupancy


def refresh_space_occupancy_from_persons(state):
    state['space_occupancy'] = build_space_occupancy_from_persons(state.get('persons', {}))
    return state


def get_annotated_event_key(annotated_event):
    event = annotated_event.get('event', {}) if isinstance(annotated_event, dict) else {}
    attributes = event.get('attributes', {}) if isinstance(event.get('attributes'), dict) else {}
    return (
        event.get('subject_id', ''),
        attributes.get('event_type', ''),
        event.get('predicate', ''),
        event.get('object_id', ''),
    )


def format_previous_events_for_prompt(previous_events):
    """
    压缩展示历史事件：旧事件只保留 event 摘要，state_snapshot 只保留最新一条。
    """
    if not previous_events:
        return "无"

    event_history = []
    latest_state_snapshot = None
    for index, annotated_event in enumerate(previous_events, start=1):
        event = annotated_event.get('event', {}) if isinstance(annotated_event, dict) else {}
        attributes = event.get('attributes', {}) if isinstance(event.get('attributes'), dict) else {}
        snapshot = annotated_event.get('state_snapshot', {}) if isinstance(annotated_event, dict) else {}
        latest_state_snapshot = snapshot or latest_state_snapshot
        event_history.append({
            "index": index,
            "timestamp": snapshot.get('timestamp', ''),
            "subject_id": event.get('subject_id', ''),
            "predicate": event.get('predicate', ''),
            "object_id": event.get('object_id', ''),
            "event_type": attributes.get('event_type', ''),
            "description": attributes.get('description', ''),
        })

    return json.dumps({
        "event_history": event_history,
        "latest_state_snapshot": latest_state_snapshot or {},
    }, ensure_ascii=False, indent=2)


def find_matching_allowed_event(annotated_event, allowed_events, default_subject):
    key = get_annotated_event_key(annotated_event)
    for candidate_event in allowed_events:
        candidate_key = (
            candidate_event.get('subject_id', default_subject),
            candidate_event.get('event_type', ''),
            candidate_event.get('predicate', ''),
            candidate_event.get('object_id', ''),
        )
        if key == candidate_key:
            return candidate_event
    return None


def get_allowed_event_key(event, default_subject):
    return (
        event.get('subject_id', default_subject),
        event.get('event_type', ''),
        event.get('predicate', ''),
        event.get('object_id', ''),
    )


def get_unused_allowed_events(allowed_events, previous_events, default_subject):
    used_keys = {get_annotated_event_key(item) for item in previous_events}
    return [
        event
        for event in allowed_events
        if get_allowed_event_key(event, default_subject) not in used_keys
    ]


def get_missing_required_primary_events(primary_events, previous_events, default_subject):
    """
    按模板顺序返回尚未生成的必选主事件。
    """
    used_keys = {get_annotated_event_key(item) for item in previous_events}
    return [
        event
        for event in primary_events
        if get_allowed_event_key(event, default_subject) not in used_keys
    ]


def validate_llm_next_event_only_result(result, allowed_events, default_subject, previous_events):
    if not isinstance(result, dict):
        raise ValueError(f"Next event result must be a dict, got {type(result)}")
    if not result.get('should_continue', False):
        return None

    event = result.get('event')
    if not isinstance(event, dict):
        raise ValueError("should_continue=true but event is missing")

    annotated_event = {'event': event}
    current_key = get_annotated_event_key(annotated_event)
    used_keys = {get_annotated_event_key(item) for item in previous_events}
    if current_key in used_keys:
        logging.info("LLM generated duplicate event %s; treating it as scenario end", current_key)
        return None

    candidate_event = find_matching_allowed_event(annotated_event, allowed_events, default_subject)
    if not candidate_event:
        raise ValueError(f"Generated event is not in remaining allowed event set: {current_key}")

    event.setdefault('attributes', {})
    event['attributes'].setdefault('description', candidate_event.get('description', ''))
    return event


def validate_llm_timestamp_result(result, previous_events):
    if not isinstance(result, dict):
        raise ValueError(f"Timestamp result must be a dict, got {type(result)}")
    timestamp = result.get('timestamp')
    if not timestamp:
        raise ValueError("Missing timestamp")
    current_timestamp = datetime.fromisoformat(timestamp.replace('+08:00', ''))
    if previous_events:
        prev_timestamp = datetime.fromisoformat(
            previous_events[-1]['state_snapshot']['timestamp'].replace('+08:00', '')
        )
        if current_timestamp < prev_timestamp:
            raise ValueError(f"timestamp goes backwards: {timestamp}")
    return timestamp


def validate_llm_persons_result(result, person_ids):
    if not isinstance(result, dict):
        raise ValueError(f"Persons result must be a dict, got {type(result)}")
    persons = result.get('persons')
    snapshot = {'persons': persons}
    validate_person_states(snapshot, person_ids)
    missing = set(person_ids) - set(persons.keys())
    if missing:
        raise ValueError(f"persons missing household members: {sorted(missing)}")
    return persons


def validate_llm_devices_result(result, household_device_ids):
    if not isinstance(result, dict):
        raise ValueError(f"Devices result must be a dict, got {type(result)}")
    devices = result.get('devices')
    snapshot = {'devices': devices}
    validate_device_states(snapshot)
    expected_devices = set(household_device_ids)
    actual_devices = set(devices.keys())
    missing = expected_devices - actual_devices
    extra = actual_devices - expected_devices
    if missing:
        raise ValueError(f"devices missing household devices: {sorted(missing)}")
    if extra:
        raise ValueError(f"devices contains devices not in household layout: {sorted(extra)}")
    return devices


def validate_llm_single_device_state_result(result, device_id):
    if not isinstance(result, dict):
        raise ValueError(f"Single device result must be a dict, got {type(result)}")
    if result.get('device_id') != device_id:
        raise ValueError(f"Invalid device_id: {result.get('device_id')}, expected {device_id}")
    state = result.get('state')
    if device_id not in DEVICE_STATES:
        raise ValueError(f"Unknown device_id: {device_id}")
    if state not in DEVICE_STATES[device_id]:
        raise ValueError(
            f"Invalid state for {device_id}: {state}; allowed states: {', '.join(DEVICE_STATES[device_id])}"
        )
    return {device_id: {"state": state}}
