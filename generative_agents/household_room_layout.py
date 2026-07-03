"""家庭户型与房间设备配置服务。"""

import copy
import json
import logging
import os
import random

from generative_agents.device_event_domain import (
    DEFAULT_ROOM_DEVICE_LAYOUT,
    DEVICE_STATES,
    FLOOR_PLAN_PRESETS,
    REQUIRED_ROOM_DEVICES,
    ROOM_DEVICE_CANDIDATES,
    ROOM_LABELS,
)
from generative_agents.device_event_prompts import LLM_HOME_LAYOUT_DEVICE_PROMPT
from generative_agents.device_catalog import format_devices_info
from generative_agents.household_context import format_members_info, get_person_ids_from_household


def _get_run_json_trials_for_layout():
    try:
        from global_methods import run_json_trials
        return run_json_trials
    except ImportError as e:
        logging.warning("Failed to import run_json_trials for household layout: %s", e)
        return None


def _log_layout_llm_failure(stage, error, context=None, prompt=None, result=None,
                            previous_events=None, extra=None):
    logging.exception(
        "LLM generation failed at %s: %s; context=%s; result=%s; extra=%s; prompt=%s",
        stage,
        error,
        context,
        result,
        extra,
        prompt,
    )

def household_has_room_layout(household_profile):
    if not isinstance(household_profile, dict):
        return False
    for key in ('rooms', 'room_layout', 'spaces'):
        layout = household_profile.get(key)
        if isinstance(layout, dict) and layout:
            return True
    return False


def select_floor_plan_for_household(household_profile):
    member_count = len(get_person_ids_from_household(household_profile))
    candidates = [
        item for item in FLOOR_PLAN_PRESETS
        if item["min_members"] <= member_count <= item["max_members"]
    ]
    if not candidates:
        candidates = FLOOR_PLAN_PRESETS
    return copy.deepcopy(random.choice(candidates))


def format_rooms_info(room_ids):
    return "\n".join(f"- {room_id}: {ROOM_LABELS.get(room_id, room_id)}" for room_id in room_ids)


def format_room_device_candidates(room_ids):
    lines = []
    for room_id in room_ids:
        candidates = [
            device_id for device_id in ROOM_DEVICE_CANDIDATES.get(room_id, [])
            if device_id in DEVICE_STATES
        ]
        lines.append(f"- {room_id}: {', '.join(candidates) if candidates else '无'}")
    return "\n".join(lines)


def summarize_home_devices_for_layout(device_file, max_devices=80):
    if not device_file or not os.path.exists(device_file):
        return format_devices_info(device_file)
    try:
        with open(device_file, 'r', encoding='utf-8') as f:
            devices_config = json.load(f)
    except Exception as e:
        logging.warning("Failed to load device library for layout generation: %s", e)
        return format_devices_info(device_file)

    lines = []
    categories = devices_config.get('device_categories', {})
    for category_name, category_data in categories.items():
        category_label = category_data.get('name', category_name)
        for device_id, device_info in category_data.get('devices', {}).items():
            rooms = ', '.join(device_info.get('rooms', []))
            description = device_info.get('description', '')
            lines.append(f"- {device_id}({category_label}): {description}; 适用房间: {rooms}")
            if len(lines) >= max_devices:
                return "\n".join(lines)
    return "\n".join(lines) if lines else format_devices_info(device_file)


def _format_profile_value_for_layout(value, max_items=4):
    if value is None or value == "":
        return ""
    if isinstance(value, list):
        items = [str(item) for item in value if item]
        return "、".join(items[:max_items])
    if isinstance(value, dict):
        items = []
        for key, item in value.items():
            if item:
                items.append(f"{key}={item}")
            if len(items) >= max_items:
                break
        return "、".join(items)
    return str(value)


def format_household_preferences_for_layout(household_profile):
    """
    将家庭画像里的偏好、习惯和照护信息压缩为户型设备选择上下文。
    """
    if not isinstance(household_profile, dict):
        return "未提供显式偏好，请按家庭人口结构和常见智能家居需求选择设备。"

    lines = []
    family = household_profile.get('family', {})
    if isinstance(family, dict):
        if family.get('shared_background'):
            lines.append(f"- 家庭背景: {family['shared_background']}")
        if family.get('weekend_context'):
            lines.append(f"- 周末/休闲安排: {family['weekend_context']}")

    members = household_profile.get('members', [])
    if isinstance(members, dict):
        member_iter = []
        for person_id, member in members.items():
            if isinstance(member, dict):
                item = member.copy()
                item.setdefault('person_id', person_id)
                member_iter.append(item)
    elif isinstance(members, list):
        member_iter = [member for member in members if isinstance(member, dict)]
    else:
        member_iter = []

    for member in member_iter:
        traits = member.get('traits', {}) if isinstance(member.get('traits'), dict) else {}
        detail_parts = []
        for key, label in (
            ('preferences', '偏好'),
            ('daily_routines', '日常习惯'),
            ('lifestyle', '生活方式'),
            ('hobbies', '兴趣'),
            ('occupation', '职业'),
        ):
            value = traits.get(key, member.get(key))
            text = _format_profile_value_for_layout(value)
            if text:
                detail_parts.append(f"{label}:{text}")
        if detail_parts:
            person_id = member.get('person_id') or member.get('id') or ''
            name = member.get('name') or person_id or '家庭成员'
            role = member.get('role') or member.get('family_role') or ''
            role_text = f"({role})" if role else ""
            lines.append(f"- {name}{role_text}: " + "；".join(detail_parts))

    responsibilities = household_profile.get('role_responsibilities', [])
    if isinstance(responsibilities, dict):
        for person_id, responsibility in responsibilities.items():
            text = _format_profile_value_for_layout(responsibility)
            if text:
                lines.append(f"- 责任分工: {person_id}: {text}")
    elif isinstance(responsibilities, list):
        for responsibility in responsibilities[:8]:
            if isinstance(responsibility, dict):
                person_id = (
                    responsibility.get('person_id')
                    or responsibility.get('member_id')
                    or responsibility.get('caretaker_id')
                    or ''
                )
                text = _format_profile_value_for_layout(
                    responsibility.get('responsibility')
                    or responsibility.get('description')
                    or responsibility.get('tasks')
                    or responsibility
                )
                if text:
                    lines.append(f"- 责任分工: {person_id}: {text}")
            elif responsibility:
                lines.append(f"- 责任分工: {responsibility}")

    pets = household_profile.get('pets', [])
    if isinstance(pets, list):
        for pet in pets[:4]:
            if not isinstance(pet, dict):
                continue
            name = pet.get('name') or pet.get('pet_id') or '宠物'
            species = pet.get('species') or pet.get('type') or ''
            caretaker = pet.get('caretaker_id') or pet.get('caretaker') or ''
            pet_parts = [item for item in [species, f"照护人={caretaker}" if caretaker else ""] if item]
            lines.append(f"- 宠物照护: {name}" + (f"({', '.join(pet_parts)})" if pet_parts else ""))

    return "\n".join(lines) if lines else "未提供显式偏好，请按家庭人口结构和常见智能家居需求选择设备。"


def build_rule_based_room_layout(floor_plan):
    rooms = {}
    for room_id in floor_plan.get('rooms', []):
        devices = []
        for device_id in REQUIRED_ROOM_DEVICES.get(room_id, []):
            if device_id in DEVICE_STATES and device_id not in devices:
                devices.append(device_id)
        for device_id in ROOM_DEVICE_CANDIDATES.get(room_id, []):
            if device_id in DEVICE_STATES and device_id not in devices:
                devices.append(device_id)
        rooms[room_id] = {
            "name": ROOM_LABELS.get(room_id, room_id),
            "devices": devices,
        }
    return {
        "layout_id": floor_plan.get('layout_id', 'default'),
        "layout_name": floor_plan.get('name', '默认户型'),
        "rooms": rooms,
    }


def validate_generated_room_layout(layout_result, floor_plan):
    if not isinstance(layout_result, dict):
        raise ValueError(f"Layout result must be a dict, got {type(layout_result)}")
    rooms = layout_result.get('rooms')
    if not isinstance(rooms, dict) or not rooms:
        raise ValueError("Layout result missing rooms")

    allowed_rooms = set(floor_plan.get('rooms', []))
    normalized_rooms = {}
    for room_id in floor_plan.get('rooms', []):
        room_data = rooms.get(room_id)
        if not isinstance(room_data, dict):
            room_data = {}
        devices = room_data.get('devices', [])
        if not isinstance(devices, list):
            devices = []
        normalized_devices = []
        room_candidates = set(ROOM_DEVICE_CANDIDATES.get(room_id, [])) | set(REQUIRED_ROOM_DEVICES.get(room_id, []))
        for device_id in devices:
            if device_id in DEVICE_STATES and (not room_candidates or device_id in room_candidates):
                if device_id not in normalized_devices:
                    normalized_devices.append(device_id)
        for device_id in REQUIRED_ROOM_DEVICES.get(room_id, []):
            if device_id in DEVICE_STATES and device_id not in normalized_devices:
                normalized_devices.append(device_id)
        normalized_rooms[room_id] = {
            "name": room_data.get('name') or ROOM_LABELS.get(room_id, room_id),
            "devices": normalized_devices,
        }

    extra_rooms = set(rooms) - allowed_rooms
    if extra_rooms:
        logging.info("Ignoring rooms outside selected floor plan: %s", sorted(extra_rooms))
    return {
        "layout_id": layout_result.get('layout_id') or floor_plan.get('layout_id', 'default'),
        "layout_name": layout_result.get('layout_name') or floor_plan.get('name', '默认户型'),
        "rooms": normalized_rooms,
    }


def ensure_required_room_devices(household_profile):
    if not isinstance(household_profile, dict):
        return household_profile
    for layout_key in ('rooms', 'room_layout', 'spaces'):
        layout = household_profile.get(layout_key)
        if not isinstance(layout, dict) or not layout:
            continue
        changed = False
        for room_id, required_devices in REQUIRED_ROOM_DEVICES.items():
            if room_id not in layout:
                continue
            room_data = layout[room_id]
            if isinstance(room_data, dict):
                devices = room_data.get('devices') or room_data.get('device_ids') or []
                if not isinstance(devices, list):
                    devices = []
                for device_id in required_devices:
                    if device_id in DEVICE_STATES and device_id not in devices:
                        devices.append(device_id)
                        changed = True
                room_data['devices'] = devices
            elif isinstance(room_data, list):
                for device_id in required_devices:
                    if device_id in DEVICE_STATES and device_id not in room_data:
                        room_data.append(device_id)
                        changed = True
        if changed:
            logging.info("Added missing required room devices to existing household layout")
        return household_profile
    return household_profile


def ensure_household_room_layout(household_profile, device_file=None, use_llm=True, overwrite=False):
    if household_profile is None:
        household_profile = {}
    if household_has_room_layout(household_profile) and not overwrite:
        return ensure_required_room_devices(household_profile)

    floor_plan = select_floor_plan_for_household(household_profile)
    layout_result = None
    if use_llm:
        run_json_trials_func = _get_run_json_trials_for_layout()
        if run_json_trials_func is not None:
            prompt = LLM_HOME_LAYOUT_DEVICE_PROMPT.format(
                members_info=format_members_info(household_profile, get_person_ids_from_household(household_profile)),
                household_preferences=format_household_preferences_for_layout(household_profile),
                layout_id=floor_plan.get('layout_id', ''),
                layout_name=floor_plan.get('name', ''),
                rooms_info=format_rooms_info(floor_plan.get('rooms', [])),
                devices_info=summarize_home_devices_for_layout(device_file),
                allowed_device_ids=", ".join(sorted(DEVICE_STATES.keys())),
                room_device_candidates=format_room_device_candidates(floor_plan.get('rooms', [])),
            )
            try:
                result = run_json_trials_func(
                    prompt,
                    num_gen=1,
                    num_tokens_request=2200,
                    temperature=0.5,
                )
                layout_result = validate_generated_room_layout(result, floor_plan)
            except Exception as e:
                _log_layout_llm_failure(
                    "household_room_layout",
                    e,
                    context={"scenario": "household_layout"},
                    prompt=prompt,
                    result=locals().get('result'),
                    extra={"floor_plan": floor_plan},
                )
        else:
            logging.warning("LLM not available; using rule-based household room layout")

    if layout_result is None:
        layout_result = validate_generated_room_layout(build_rule_based_room_layout(floor_plan), floor_plan)

    household_profile['floor_plan'] = {
        "layout_id": layout_result['layout_id'],
        "layout_name": layout_result['layout_name'],
    }
    household_profile['rooms'] = layout_result['rooms']
    logging.info(
        "Assigned household room layout: %s with %s rooms",
        layout_result['layout_id'],
        len(layout_result['rooms']),
    )
    return household_profile


def get_household_room_layout(household_profile):
    """
    获取家庭房间与设备布局，家庭画像未提供时使用默认布局。
    """
    for key in ('rooms', 'room_layout', 'spaces'):
        layout = household_profile.get(key)
        if isinstance(layout, dict) and layout:
            normalized = {}
            for room_id, room_data in layout.items():
                if isinstance(room_data, dict):
                    devices = room_data.get('devices') or room_data.get('device_ids') or []
                elif isinstance(room_data, list):
                    devices = room_data
                else:
                    devices = []
                normalized[room_id] = list(devices)
            if normalized:
                return normalized
    return copy.deepcopy(DEFAULT_ROOM_DEVICE_LAYOUT)


def format_room_device_layout(household_profile):
    """
    格式化房间与设备布局。
    """
    layout = get_household_room_layout(household_profile)
    lines = []
    for room_id, devices in layout.items():
        device_text = ', '.join(devices) if devices else '无固定设备'
        lines.append(f"- {room_id}: {device_text}")
    return '\n'.join(lines)


def get_layout_device_ids(household_profile):
    """
    从房间设备布局中提取设备 ID。
    """
    layout = get_household_room_layout(household_profile)
    device_ids = []
    for devices in layout.values():
        device_ids.extend(devices)
    return list(dict.fromkeys(device_ids))
