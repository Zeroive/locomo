"""
设备事件生成相关工具函数。

根据场景和对话内容，使用模型生成设备行为记录。
支持连续多日场景事件生成（episodes）。
"""

import os
import json
import logging
import copy
from datetime import datetime, timedelta, date
import random
from concurrent.futures import ThreadPoolExecutor, as_completed

# 延迟导入 LLM 相关函数，避免在不需要时导入 openai
_run_json_trials = None

LLM_FAILURE_LOG_MAX_CHARS = int(os.getenv("LLM_FAILURE_LOG_MAX_CHARS", "8000"))


def _format_for_llm_failure_log(value, max_chars=LLM_FAILURE_LOG_MAX_CHARS):
    if value is None:
        return None
    try:
        if isinstance(value, (dict, list)):
            text = json.dumps(value, ensure_ascii=False, indent=2)
        else:
            text = str(value)
    except Exception:
        text = repr(value)
    if len(text) > max_chars:
        return text[:max_chars] + f"... <truncated {len(text) - max_chars} chars>"
    return text


def _log_llm_failure(stage, error, context=None, prompt=None, result=None,
                     previous_events=None, extra=None):
    context = context or {}
    details = {
        "stage": stage,
        "scenario": context.get("scenario"),
        "episode_date": (
            context.get("episode_date").isoformat()
            if hasattr(context.get("episode_date"), "isoformat")
            else context.get("episode_date")
        ),
        "subject_id": context.get("default_subject"),
        "scenario_time": context.get("scenario_time"),
        "daily_state_description": context.get("daily_state_description"),
        "previous_events": previous_events,
        "result": result,
        "prompt": prompt,
        "extra": extra,
    }
    compact_details = {
        key: _format_for_llm_failure_log(value)
        for key, value in details.items()
        if value not in (None, "", [], {})
    }
    logging.exception(
        "LLM generation failed at %s: %s\nFailure details:\n%s",
        stage,
        error,
        json.dumps(compact_details, ensure_ascii=False, indent=2),
    )

def get_run_json_trials():
    """延迟导入 run_json_trials 函数"""
    global _run_json_trials
    if _run_json_trials is None:
        try:
            from global_methods import run_json_trials
            _run_json_trials = run_json_trials
        except ImportError as e:
            logging.warning(f"Failed to import run_json_trials: {e}")
            _run_json_trials = None
    return _run_json_trials

logging.basicConfig(level=logging.INFO)

# ==================== 领域定义与 Prompt 模板 ====================

from generative_agents.device_event_domain import (
    canonicalize_scenario,
    SCENE_TEMPLATES,
    PERSON_ID_MAPPING,
    DEFAULT_ROOM_DEVICE_LAYOUT,
    FLOOR_PLAN_PRESETS,
    ROOM_LABELS,
    ROOM_DEVICE_CANDIDATES,
    REQUIRED_ROOM_DEVICES,
    DEVICE_STATES,
    PERSON_ROOM_STATUS_SCHEMA,
    PERSON_STATUS_ALIASES,
    TIME_PERIODS,
)
from generative_agents.device_event_validation import (
    parse_hhmm_to_minutes,
    expand_time_range_to_segments,
    get_time_period_options,
    format_time_period_options,
    scenario_time_in_period_options,
    normalize_llm_scenario_time,
    get_time_description,
    build_episode_id,
    format_previous_scenario_descriptions,
    format_allowed_events_info,
    format_candidate_event_info,
    validate_llm_state_result,
    validate_llm_event_item_result,
    validate_person_states,
    validate_device_states,
    validate_space_occupancy,
    build_space_occupancy_from_persons,
    refresh_space_occupancy_from_persons,
    get_annotated_event_key,
    format_previous_events_for_prompt,
    find_matching_allowed_event,
    get_allowed_event_key,
    get_unused_allowed_events,
    get_missing_required_primary_events,
    validate_llm_next_event_only_result,
    validate_llm_timestamp_result,
    validate_llm_persons_result,
    validate_llm_devices_result,
    validate_llm_single_device_state_result,
)
from generative_agents.household_context import (
    format_members_info,
    format_relations_info,
    get_person_ids_from_household,
)
from generative_agents.household_room_layout import (
    household_has_room_layout,
    select_floor_plan_for_household,
    format_rooms_info,
    format_room_device_candidates,
    summarize_home_devices_for_layout,
    format_household_preferences_for_layout,
    build_rule_based_room_layout,
    validate_generated_room_layout,
    ensure_household_room_layout,
    get_household_room_layout,
    format_room_device_layout,
    get_layout_device_ids,
)
from generative_agents.device_catalog import (
    format_devices_info,
    get_available_device_ids,
)
from generative_agents.device_event_prompts import (
    LLM_STATE_DESCRIPTION_PROMPT,
    LLM_HOME_LAYOUT_DEVICE_PROMPT,
    LLM_EVENT_ITEM_PROMPT,
    LLM_NEXT_EVENT_PROMPT,
    LLM_NEXT_EVENT_ONLY_PROMPT,
    LLM_EVENT_TIMESTAMP_PROMPT,
    LLM_EVENT_PERSONS_PROMPT,
    LLM_EVENT_DEVICES_PROMPT,
    LLM_SINGLE_DEVICE_STATE_PROMPT,
    DEVICE_EVENTS_GENERATION_PROMPT,
)

def load_household_profile(household_profile_path):
    """
    加载家庭画像文件。
    
    Args:
        household_profile_path: 家庭画像文件路径
        
    Returns:
        dict: 家庭画像字典，如果文件不存在返回空字典
    """
    if os.path.exists(household_profile_path):
        try:
            with open(household_profile_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logging.warning(f"Failed to load household profile: {e}")
    return {}


def get_scene_templates(device_file=None):
    """
    获取场景模板。
    
    Args:
        device_file: 设备配置文件路径（可选）
        
    Returns:
        dict: 场景模板字典
    """
    # 基础场景模板
    templates = SCENE_TEMPLATES.copy()
    
    # 如果提供了设备文件，加载设备信息增强模板
    if device_file and os.path.exists(device_file):
        try:
            with open(device_file, 'r', encoding='utf-8') as f:
                device_config = json.load(f)
                # 可以在这里根据设备配置增强场景模板
                templates['device_config'] = device_config
        except Exception as e:
            logging.warning(f"Failed to load device config: {e}")
    
    return templates


def generate_single_day_episode_llm(scenario, episode_date, day_offset, template,
                                   household_profile, person_ids, device_file=None, subject_id=None,
                                   max_retries=3):
    """
    使用 LLM 生成单日的设备事件episode。
    
    Args:
        scenario: 场景类型
        episode_date: episode日期
        day_offset: 天数偏移（从开始算起）
        template: 场景模板
        household_profile: 家庭画像
        person_ids: 可用的人员ID列表
        device_file: 设备配置文件路径（可选）
        max_retries: 最大重试次数
        
    Returns:
        dict: episode字典，包含 daily_state_description 和 annotated_events
    """
    # 检查 LLM 是否可用
    run_json_trials_func = get_run_json_trials()
    if run_json_trials_func is None:
        logging.warning("LLM not available, skipping LLM generation")
        return None
    
    # 获取默认参数
    default_subject = subject_id or template.get('default_subject', 'dad')
    default_home = template.get('default_home', 'home_1')
    time_window = template.get('time_window', {})
    primary_events = get_primary_events(template)
    allowed_events = get_allowed_scene_events(template)
    
    # 确定时间窗口（是否是晚归日）
    is_late_day = is_late_work_day(day_offset, num_days=7)
    time_range = time_window.get('late' if is_late_day else 'normal', time_window.get('normal'))
    planned_scene_time = build_scene_time(episode_date, time_range)
    
    # 准备家庭成员信息
    members_info = format_members_info(household_profile, person_ids)
    relations_info = format_relations_info(household_profile)
    room_device_layout = format_room_device_layout(household_profile)
    person_room_status_schema = format_person_room_status_schema()
    device_state_schema = format_device_state_schema()
    
    # 准备设备信息
    devices_info = format_devices_info(device_file)
    primary_device_ids = [event.get('object_id') for event in allowed_events if event.get('object_id')]
    if primary_device_ids:
        devices_info += "\n\n## 场景候选事件设备对象\n"
        devices_info += "\n".join(f"- {device_id}: 场景候选事件对象" for device_id in primary_device_ids)
    
    # 随机抽样部分人物和设备
    sampled_persons = random.sample(person_ids, min(3, len(person_ids)))
    available_devices = get_available_device_ids(device_file)
    for device_id in get_layout_device_ids(household_profile):
        if device_id not in available_devices:
            available_devices.append(device_id)
    for device_id in primary_device_ids:
        if device_id not in available_devices:
            available_devices.append(device_id)
    sampled_devices = random.sample(available_devices, min(5, len(available_devices)))
    
    common_prompt_args = {
        "scenario": scenario,
        "scenario_desc": template.get('description', ''),
        "episode_date": episode_date.strftime('%Y-%m-%d'),
        "subject_id": default_subject,
        "members_info": members_info,
        "relations_info": relations_info,
        "room_device_layout": room_device_layout,
        "person_room_status_schema": person_room_status_schema,
        "device_state_schema": device_state_schema,
        "devices_info": devices_info,
    }

    state_prompt = LLM_STATE_DESCRIPTION_PROMPT.format(
        scenario=scenario,
        scenario_desc=template.get('description', ''),
        episode_date=episode_date.strftime('%Y-%m-%d'),
        subject_id=default_subject,
        planned_scene_time=planned_scene_time,
        time_period_options=format_time_period_options(time_range),
        previous_scenario_descriptions="无",
        members_info=members_info,
        relations_info=relations_info,
        room_device_layout=room_device_layout,
        person_room_status_schema=person_room_status_schema,
        device_state_schema=device_state_schema,
        devices_info=devices_info,
        sampled_persons=', '.join(sampled_persons),
        sampled_devices=', '.join(sampled_devices)
    )
    
    for attempt in range(max_retries):
        state_result = None
        annotated_events = None
        try:
            logging.info(f"Generating state description for {episode_date} (attempt {attempt + 1}/{max_retries})")
            
            state_result = run_json_trials_func(state_prompt, num_gen=1, num_tokens_request=1400, temperature=0.8)
            
            state_result = validate_llm_state_result(state_result)
            state_result['scenario_time'] = normalize_llm_scenario_time(
                state_result.get('scenario_time'),
                planned_scene_time,
                time_range,
                scenario,
                episode_date,
            )
            if not state_result['scenario_should_happen']:
                logging.info(
                    "Skipping episode for %s %s: %s",
                    scenario,
                    episode_date,
                    state_result.get('skip_reason', '')
                )
                return {"_skip": True}

            annotated_events = []
            for candidate_event in allowed_events:
                item_prompt = LLM_EVENT_ITEM_PROMPT.format(
                    **common_prompt_args,
                    household_state_description=state_result['household_state_description'],
                    device_event_description=state_result['device_event_description'],
                    daily_state_description=state_result['daily_state_description'],
                    previous_events=format_previous_events_for_prompt(annotated_events),
                    candidate_event_info=format_candidate_event_info(candidate_event, default_subject),
                )
                item_result = None
                try:
                    item_result = run_json_trials_func(item_prompt, num_gen=1, num_tokens_request=1600, temperature=0.7)
                    annotated_event = validate_llm_event_item_result(
                        item_result,
                        candidate_event,
                        default_subject,
                        person_ids,
                        available_devices,
                        annotated_events,
                    )
                except Exception as e:
                    _log_llm_failure(
                        "candidate_event_item",
                        e,
                        context={
                            "scenario": scenario,
                            "episode_date": episode_date,
                            "default_subject": default_subject,
                            "daily_state_description": state_result.get('daily_state_description'),
                        },
                        prompt=item_prompt,
                        result=item_result,
                        previous_events=annotated_events,
                        extra={"candidate_event": candidate_event},
                    )
                    raise
                if annotated_event:
                    annotated_events.append(annotated_event)
            
            llm_result = {
                'household_state_description': state_result['household_state_description'],
                'device_event_description': state_result['device_event_description'],
                'daily_state_description': state_result['daily_state_description'],
                'annotated_events': annotated_events,
            }
            try:
                validated_result = validate_llm_episode_result(
                    llm_result,
                    scenario,
                    episode_date,
                    default_subject,
                    default_home,
                    person_ids,
                    available_devices,
                    time_range,
                    primary_events,
                    allowed_events,
                    get_household_room_layout(household_profile)
                )
            except Exception as e:
                _log_llm_failure(
                    "single_day_episode_validation",
                    e,
                    context={
                        "scenario": scenario,
                        "episode_date": episode_date,
                        "default_subject": default_subject,
                        "daily_state_description": state_result.get('daily_state_description'),
                    },
                    result=llm_result,
                    previous_events=annotated_events,
                    extra={"primary_events": primary_events, "allowed_events": allowed_events},
                )
                raise
            
            # 添加 sampled_context
            validated_result['sampled_context'] = {
                'persons': state_result.get('sampled_context', {}).get('persons', sampled_persons),
                'devices': state_result.get('sampled_context', {}).get('devices', sampled_devices)
            }
            
            logging.info(f"Successfully generated episode for {episode_date}")
            return validated_result
            
        except Exception as e:
            _log_llm_failure(
                "single_day_episode_llm",
                e,
                context={
                    "scenario": scenario,
                    "episode_date": episode_date,
                    "default_subject": default_subject,
                },
                prompt=state_prompt,
                result=locals().get("state_result"),
                previous_events=locals().get("annotated_events"),
                extra={"attempt": attempt + 1, "max_retries": max_retries},
            )
            if attempt == max_retries - 1:
                logging.error(f"All {max_retries} attempts failed for {episode_date}, falling back to rule-based generation")
                return None
    
    return None


def generate_daily_device_episodes(generation_plan, num_days=7, household_profile=None,
                                   scene_templates=None, device_file=None, use_llm=True,
                                   day_workers=1):
    """
    按天生成所有情景：LLM 路径先生成当天所有情景描述，再逐情景生成事件。
    rule-based 路径回退到原有按情景生成逻辑。
    """
    if scene_templates is None:
        scene_templates = SCENE_TEMPLATES
    if household_profile is None:
        household_profile = {}

    if not use_llm:
        episodes = []
        for plan_item in generation_plan:
            episodes.extend(generate_scenario_device_episodes(
                scenario=plan_item['scenario'],
                num_days=num_days,
                household_profile=household_profile,
                scene_templates=scene_templates,
                device_file=device_file,
                use_llm=False,
                subject_id=plan_item['person_id'],
                subject_profile=plan_item.get('member'),
            ))
        return episodes

    run_json_trials_func = get_run_json_trials()
    if run_json_trials_func is None:
        logging.warning("LLM not available, falling back to rule-based daily generation")
        return generate_daily_device_episodes(
            generation_plan,
            num_days=num_days,
            household_profile=household_profile,
            scene_templates=scene_templates,
            device_file=device_file,
            use_llm=False,
        )

    person_ids = get_person_ids_from_household(household_profile)
    layout_device_ids = get_layout_device_ids(household_profile)
    base_available_devices = get_available_device_ids(device_file)
    for device_id in layout_device_ids:
        if device_id not in base_available_devices:
            base_available_devices.append(device_id)

    members_info = format_members_info(household_profile, person_ids)
    relations_info = format_relations_info(household_profile)
    room_device_layout = format_room_device_layout(household_profile)
    person_room_status_schema = format_person_room_status_schema()
    device_state_schema = format_device_state_schema()
    devices_info = format_devices_info(device_file)

    start_date = datetime.now().date() - timedelta(days=num_days - 1)
    
    def generate_one_day(day_offset):
        episode_date = start_date + timedelta(days=day_offset)
        day_episodes = []
        contexts = []
        available_devices = list(base_available_devices)

        for plan_index, plan_item in enumerate(generation_plan):
            scenario = canonicalize_scenario(plan_item['scenario'])
            template = scene_templates.get(scenario)
            if not template:
                logging.warning("Unknown scenario in generation plan: %s", scenario)
                continue

            default_subject = plan_item.get('person_id') or template.get('default_subject', 'dad')
            default_home = template.get('default_home', 'home_1')
            time_window = template.get('time_window', {})
            is_late_day = is_late_work_day(day_offset, num_days=7)
            time_range = time_window.get('late' if is_late_day else 'normal', time_window.get('normal'))
            planned_scene_time = build_scene_time(episode_date, time_range, fallback_hour=8 + plan_index)
            primary_events = get_primary_events(template)
            allowed_events = get_allowed_scene_events(template)

            for event in allowed_events:
                object_id = event.get('object_id')
                if object_id and object_id not in available_devices:
                    available_devices.append(object_id)
            event_device_ids = list(dict.fromkeys(
                event.get('object_id') for event in allowed_events if event.get('object_id')
            ))
            context_devices_info = devices_info
            if event_device_ids:
                context_devices_info += "\n\n## 场景候选事件设备对象\n"
                context_devices_info += "\n".join(f"- {device_id}: 场景候选事件对象" for device_id in event_device_ids)
            household_device_ids = list(dict.fromkeys(layout_device_ids + event_device_ids))

            contexts.append({
                'scenario': scenario,
                'scenario_desc': template.get('description', ''),
                'episode_date': episode_date,
                'day_offset': day_offset,
                'template': template,
                'default_subject': default_subject,
                'default_home': default_home,
                'time_range': time_range,
                'planned_scene_time': planned_scene_time,
                'primary_events': primary_events,
                'allowed_events': allowed_events,
                'household_profile': household_profile,
                'person_ids': person_ids,
                'available_devices': available_devices,
                'household_device_ids': household_device_ids,
                'members_info': members_info,
                'relations_info': relations_info,
                'room_device_layout': room_device_layout,
                'person_room_status_schema': person_room_status_schema,
                'device_state_schema': device_state_schema,
                'devices_info': context_devices_info,
                'subject_profile': plan_item.get('member'),
            })

        contexts.sort(key=lambda item: item['planned_scene_time'])

        generated_descriptions = []
        active_contexts = []
        for context in contexts:
            sampled_persons = random.sample(person_ids, min(3, len(person_ids))) if person_ids else []
            sampled_devices = random.sample(available_devices, min(5, len(available_devices))) if available_devices else []
            state_prompt = LLM_STATE_DESCRIPTION_PROMPT.format(
                scenario=context['scenario'],
                scenario_desc=context['scenario_desc'],
                episode_date=episode_date.strftime('%Y-%m-%d'),
                subject_id=context['default_subject'],
                planned_scene_time=context['planned_scene_time'],
                time_period_options=format_time_period_options(context['time_range']),
                previous_scenario_descriptions=format_previous_scenario_descriptions(generated_descriptions),
                members_info=members_info,
                relations_info=relations_info,
                room_device_layout=room_device_layout,
                person_room_status_schema=person_room_status_schema,
                device_state_schema=device_state_schema,
                devices_info=context['devices_info'],
                sampled_persons=', '.join(sampled_persons),
                sampled_devices=', '.join(sampled_devices),
            )

            state_result = None
            try:
                state_result = run_json_trials_func(
                    state_prompt,
                    num_gen=1,
                    num_tokens_request=1600,
                    temperature=0.8,
                )
                state_result = validate_llm_state_result(state_result)
                state_result['scenario_time'] = normalize_llm_scenario_time(
                    state_result.get('scenario_time'),
                    context['planned_scene_time'],
                    context['time_range'],
                    context['scenario'],
                    episode_date,
                )
            except Exception as e:
                _log_llm_failure(
                    "daily_state_description",
                    e,
                    context=context,
                    prompt=state_prompt,
                    result=locals().get("state_result"),
                )
                continue

            if not state_result['scenario_should_happen']:
                logging.info(
                    "Skipping episode for %s %s: %s",
                    context['scenario'],
                    episode_date,
                    state_result.get('skip_reason', ''),
                )
                continue

            scenario_time = state_result.get('scenario_time') or context['planned_scene_time']
            context['scenario_time'] = scenario_time
            context['daily_state_description'] = state_result['daily_state_description']
            context['household_state_description'] = state_result['household_state_description']
            context['device_event_description'] = state_result['device_event_description']
            context['sampled_context'] = {
                'persons': state_result.get('sampled_context', {}).get('persons', sampled_persons),
                'devices': state_result.get('sampled_context', {}).get('devices', sampled_devices),
            }
            generated_descriptions.append({
                'scenario': context['scenario'],
                'subject_id': context['default_subject'],
                'scenario_time': scenario_time,
                'daily_state_description': context['daily_state_description'],
                'household_state_description': context['household_state_description'],
                'device_event_description': context['device_event_description'],
            })
            active_contexts.append(context)

        all_descriptions = format_previous_scenario_descriptions(generated_descriptions)
        for context in active_contexts:
            context['all_scenario_descriptions'] = all_descriptions
            episode = generate_scenario_events_from_description_llm(context, run_json_trials_func)
            if not episode:
                logging.warning(
                    "LLM event generation failed for %s/%s, falling back to rule-based episode",
                    context['scenario'],
                    episode_date,
                )
                template = context['template']
                episode = generate_single_day_episode_rule_based(
                    scenario=context['scenario'],
                    episode_date=episode_date,
                    day_offset=day_offset,
                    template=template,
                    core_events=template.get('core_events', []),
                    noise_events=template.get('noise_events', []),
                    time_window=template.get('time_window', {}),
                    default_subject=context['default_subject'],
                    default_home=context['default_home'],
                    household_profile=household_profile,
                    person_ids=person_ids,
                )
            if episode:
                if context.get('subject_profile'):
                    episode['subject_profile'] = context['subject_profile']
                day_episodes.append(episode)

        return day_offset, day_episodes

    day_workers = max(1, int(day_workers or 1))
    if day_workers == 1 or num_days <= 1:
        episodes = []
        for day_offset in range(num_days):
            _, day_episodes = generate_one_day(day_offset)
            episodes.extend(day_episodes)
    else:
        max_workers = min(day_workers, num_days)
        day_results = {}
        logging.info("Generating device episodes by day with %s workers", max_workers)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_day = {
                executor.submit(generate_one_day, day_offset): day_offset
                for day_offset in range(num_days)
            }
            for future in as_completed(future_to_day):
                day_offset = future_to_day[future]
                try:
                    result_day_offset, day_episodes = future.result()
                    day_results[result_day_offset] = day_episodes
                except Exception as e:
                    logging.exception("Daily generation failed for day_offset=%s: %s", day_offset, e)
                    day_results[day_offset] = []
        episodes = []
        for day_offset in range(num_days):
            episodes.extend(day_results.get(day_offset, []))

    logging.info("Generated %s episodes for %s days with daily planning", len(episodes), num_days)
    return episodes


def get_primary_events(template):
    """
    获取场景级必选事件。未配置时返回空列表，避免回退到动作细节。
    """
    primary_events = template.get('primary_events') or []
    if primary_events:
        return [event.copy() for event in primary_events]
    return []


def get_allowed_scene_events(template):
    """
    获取场景期间允许出现的事件：主事件 + 可控设备核心事件 + 由当天家庭状态触发的相关设备事件。
    """
    events = get_primary_events(template)
    known_device_ids = set(DEVICE_STATES.keys())
    for devices in DEFAULT_ROOM_DEVICE_LAYOUT.values():
        known_device_ids.update(devices)
    seen_keys = {
        (event.get('subject_id'), event.get('event_type'), event.get('predicate'), event.get('object_id'))
        for event in events
    }
    for event in template.get('core_events', []):
        if event.get('object_id') not in known_device_ids:
            continue
        event_key = (
            event.get('subject_id'),
            event.get('event_type'),
            event.get('predicate'),
            event.get('object_id'),
        )
        if event_key in seen_keys:
            continue
        events.append(event.copy())
        seen_keys.add(event_key)
    events.extend(event.copy() for event in template.get('related_events', []))
    return events


def build_scene_time(episode_date, time_range, fallback_hour=8):
    """
    根据场景时间窗生成一个 ISO8601 时间。只固定到小时，分钟默认为 00。
    """
    start = (time_range or {}).get('start') if isinstance(time_range, dict) else None
    hour = fallback_hour
    minute = 0
    if isinstance(start, str) and ':' in start:
        try:
            hour, minute = [int(part) for part in start.split(':')[:2]]
        except ValueError:
            hour, minute = fallback_hour, 0
    hour = hour % 24
    scene_datetime = datetime.combine(episode_date, datetime.min.time()).replace(hour=hour, minute=minute)
    return scene_datetime.strftime('%Y-%m-%dT%H:%M:%S+08:00')




def generate_single_device_state_llm(context, run_json_trials_func, device_id, timestamp,
                                     event_json, persons, previous_events_text):
    prompt = LLM_SINGLE_DEVICE_STATE_PROMPT.format(
        scenario=context['scenario'],
        episode_date=context['episode_date'].strftime('%Y-%m-%d'),
        timestamp=timestamp,
        device_id=device_id,
        allowed_states=', '.join(DEVICE_STATES.get(device_id, [])),
        room_device_layout=context['room_device_layout'],
        devices_info=context['devices_info'],
        household_state_description=context['household_state_description'],
        device_event_description=context['device_event_description'],
        daily_state_description=context['daily_state_description'],
        previous_events=previous_events_text,
        event_json=event_json,
        persons_json=json.dumps(persons, ensure_ascii=False, indent=2),
    )
    result = None
    try:
        result = run_json_trials_func(
            prompt,
            num_gen=1,
            num_tokens_request=300,
            temperature=0.5,
        )
        return validate_llm_single_device_state_result(result, device_id)
    except Exception as e:
        _log_llm_failure(
            "single_device_state",
            e,
            context=context,
            prompt=prompt,
            result=result,
            previous_events=previous_events_text,
            extra={"device_id": device_id, "timestamp": timestamp, "event": event_json},
        )
        raise


def generate_all_device_states_llm(context, run_json_trials_func, household_device_ids,
                                   timestamp, event_json, persons, previous_events_text):
    max_workers = min(8, max(1, len(household_device_ids)))
    devices = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_device = {
            executor.submit(
                generate_single_device_state_llm,
                context,
                run_json_trials_func,
                device_id,
                timestamp,
                event_json,
                persons,
                previous_events_text,
            ): device_id
            for device_id in household_device_ids
        }
        for future in as_completed(future_to_device):
            device_id = future_to_device[future]
            try:
                devices.update(future.result())
            except Exception as e:
                raise ValueError(f"Failed to generate state for device {device_id}: {e}")

    return validate_llm_devices_result({"devices": devices}, household_device_ids)


def validate_llm_next_event_result(result, allowed_events, default_subject, person_ids,
                                   available_devices, previous_events):
    if not isinstance(result, dict):
        raise ValueError(f"Next event result must be a dict, got {type(result)}")
    if not result.get('should_continue', False):
        return None

    annotated_event = result.get('annotated_event')
    if not isinstance(annotated_event, dict):
        raise ValueError("should_continue=true but annotated_event is missing")
    if isinstance(annotated_event.get('event'), dict):
        annotated_event['event']['subject_id'] = default_subject

    current_key = get_annotated_event_key(annotated_event)
    used_keys = {get_annotated_event_key(event) for event in previous_events}
    if current_key in used_keys:
        logging.info("LLM generated duplicate event %s; treating it as scenario end", current_key)
        return None

    candidate_event = find_matching_allowed_event(annotated_event, allowed_events, default_subject)
    if not candidate_event:
        raise ValueError(f"Generated event is not in remaining allowed event set: {current_key}")

    return validate_llm_event_item_result(
        {"should_generate": True, "annotated_event": annotated_event},
        candidate_event,
        default_subject,
        person_ids,
        available_devices,
        previous_events,
    )


def generate_split_annotated_event_llm(context, run_json_trials_func, previous_events):
    """
    分步生成一个 annotated_event：event、timestamp、persons、devices 分别请求模型生成。
    """
    scenario = context['scenario']
    episode_date = context['episode_date']
    default_subject = context['default_subject']
    person_ids = context['person_ids']
    allowed_events = context['allowed_events']
    primary_events = context['primary_events']
    available_devices = context['available_devices']
    household_device_ids = context['household_device_ids']
    all_scenario_descriptions = context.get('all_scenario_descriptions') or "无"
    previous_events_text = format_previous_events_for_prompt(previous_events)
    previous_events_persons_text = format_previous_events_for_prompt(previous_events, include_devices=False)
    missing_required_primary_events = get_missing_required_primary_events(
        primary_events,
        previous_events,
        default_subject,
    )
    remaining_allowed_events = get_unused_allowed_events(allowed_events, previous_events, default_subject)
    if not remaining_allowed_events:
        return None
    allowed_events_info = format_allowed_events_info(primary_events, remaining_allowed_events, default_subject)
    if missing_required_primary_events:
        allowed_events_info += "\n\n## 尚未生成的必选主事件\n"
        allowed_events_info += format_allowed_events_info(
            primary_events,
            missing_required_primary_events,
            default_subject,
        )
        allowed_events_info += "\n- 在这些必选主事件全部生成之前，不允许输出 should_continue=false。"

    event_prompt = LLM_NEXT_EVENT_ONLY_PROMPT.format(
        scenario=scenario,
        scenario_desc=context['scenario_desc'],
        episode_date=episode_date.strftime('%Y-%m-%d'),
        subject_id=default_subject,
        scenario_time=context['scenario_time'],
        household_state_description=context['household_state_description'],
        device_event_description=context['device_event_description'],
        daily_state_description=context['daily_state_description'],
        previous_events=previous_events_text,
        allowed_events_info=allowed_events_info,
    )
    event_result = None
    try:
        event_result = run_json_trials_func(
            event_prompt,
            num_gen=1,
            num_tokens_request=900,
            temperature=0.7,
        )
        event = validate_llm_next_event_only_result(
            event_result,
            remaining_allowed_events,
            default_subject,
            previous_events,
        )
    except Exception as e:
        _log_llm_failure(
            "next_event",
            e,
            context=context,
            prompt=event_prompt,
            result=event_result,
            previous_events=previous_events,
            extra={
                "missing_required_primary_events": missing_required_primary_events,
                "remaining_allowed_events": remaining_allowed_events,
                "all_allowed_events": allowed_events,
            },
        )
        raise
    if not event:
        if missing_required_primary_events:
            raise ValueError(
                "LLM ended scenario before required primary events were generated: "
                f"{[get_allowed_event_key(item, default_subject) for item in missing_required_primary_events]}"
            )
        return None

    event_json = json.dumps(event, ensure_ascii=False, indent=2)
    timestamp_prompt = LLM_EVENT_TIMESTAMP_PROMPT.format(
        scenario=scenario,
        episode_date=episode_date.strftime('%Y-%m-%d'),
        scenario_time=context['scenario_time'],
        household_state_description=context['household_state_description'],
        device_event_description=context['device_event_description'],
        daily_state_description=context['daily_state_description'],
        previous_events=previous_events_text,
        event_json=event_json,
    )
    timestamp_result = None
    try:
        timestamp_result = run_json_trials_func(
            timestamp_prompt,
            num_gen=1,
            num_tokens_request=300,
            temperature=0.4,
        )
        timestamp = validate_llm_timestamp_result(timestamp_result, previous_events)
    except Exception as e:
        _log_llm_failure(
            "event_timestamp",
            e,
            context=context,
            prompt=timestamp_prompt,
            result=timestamp_result,
            previous_events=previous_events,
            extra={"event": event_json},
        )
        raise

    persons_prompt = LLM_EVENT_PERSONS_PROMPT.format(
        scenario=scenario,
        subject_id=default_subject,
        episode_date=episode_date.strftime('%Y-%m-%d'),
        timestamp=timestamp,
        members_info=context['members_info'],
        relations_info=context['relations_info'],
        person_room_status_schema=context['person_room_status_schema'],
        room_device_layout=context['room_device_layout'],
        all_scenario_descriptions=all_scenario_descriptions,
        household_state_description=context['household_state_description'],
        device_event_description=context['device_event_description'],
        daily_state_description=context['daily_state_description'],
        previous_events=previous_events_persons_text,
        event_json=event_json,
    )
    persons_result = None
    try:
        persons_result = run_json_trials_func(
            persons_prompt,
            num_gen=1,
            num_tokens_request=900,
            temperature=0.6,
        )
        persons = validate_llm_persons_result(persons_result, person_ids)
    except Exception as e:
        _log_llm_failure(
            "event_persons",
            e,
            context=context,
            prompt=persons_prompt,
            result=persons_result,
            previous_events=previous_events,
            extra={"timestamp": timestamp, "event": event_json},
        )
        raise

    try:
        devices = generate_all_device_states_llm(
            context,
            run_json_trials_func,
            household_device_ids,
            timestamp,
            event_json,
            persons,
            previous_events_text,
        )
    except Exception as e:
        _log_llm_failure(
            "event_devices",
            e,
            context=context,
            previous_events=previous_events,
            extra={
                "timestamp": timestamp,
                "event": event_json,
                "persons": persons,
                "household_device_ids": household_device_ids,
            },
        )
        raise

    annotated_event = {
        'event': event,
        'state_snapshot': {
            'timestamp': timestamp,
            'persons': persons,
            'devices': devices,
            'space_occupancy': build_space_occupancy_from_persons(persons),
        }
    }
    candidate_event = find_matching_allowed_event(annotated_event, allowed_events, default_subject)
    try:
        return validate_llm_event_item_result(
            {'should_generate': True, 'annotated_event': annotated_event},
            candidate_event,
            default_subject,
            person_ids,
            available_devices,
            previous_events,
        )
    except Exception as e:
        _log_llm_failure(
            "annotated_event_validation",
            e,
            context=context,
            previous_events=previous_events,
            extra={"annotated_event": annotated_event, "candidate_event": candidate_event},
        )
        raise


def generate_split_annotated_event_with_retries(context, run_json_trials_func, previous_events, max_retries=3):
    """
    对单个 annotated_event 的分步生成做局部重试。
    返回 None 表示模型明确判断当前情景结束；抛错才触发重试。
    """
    last_error = None
    for attempt in range(max_retries):
        previous_events_backup = copy.deepcopy(previous_events)
        try:
            return generate_split_annotated_event_llm(
                context,
                run_json_trials_func,
                previous_events,
            )
        except Exception as e:
            previous_events[:] = previous_events_backup
            last_error = e
            logging.warning(
                "Split annotated_event generation attempt %s/%s failed for %s/%s: %s",
                attempt + 1,
                max_retries,
                context.get('scenario'),
                context.get('episode_date'),
                e,
            )
    raise last_error


def generate_scenario_events_from_description_llm(context, run_json_trials_func, max_retries=3):
    scenario = context['scenario']
    episode_date = context['episode_date']
    default_subject = context['default_subject']
    default_home = context['default_home']
    person_ids = context['person_ids']
    available_devices = context['available_devices']
    allowed_events = context['allowed_events']
    primary_events = context['primary_events']
    time_range = context['time_range']
    household_profile = context['household_profile']
    annotated_events = []

    max_events = max(1, len(allowed_events))
    all_scenario_descriptions = context.get('all_scenario_descriptions') or "无"

    for attempt in range(max_retries):
        annotated_events = []
        try:
            for _ in range(max_events):
                annotated_event = generate_split_annotated_event_with_retries(
                    context,
                    run_json_trials_func,
                    annotated_events,
                    max_retries=3,
                )
                if not annotated_event:
                    break
                annotated_events.append(annotated_event)

            llm_result = {
                'household_state_description': context['household_state_description'],
                'device_event_description': context['device_event_description'],
                'daily_state_description': context['daily_state_description'],
                'annotated_events': annotated_events,
            }
            try:
                episode = validate_llm_episode_result(
                    llm_result,
                    scenario,
                    episode_date,
                    default_subject,
                    default_home,
                    person_ids,
                    available_devices,
                    time_range,
                    primary_events,
                    allowed_events,
                    get_household_room_layout(household_profile),
                )
            except Exception as e:
                _log_llm_failure(
                    "scenario_episode_validation",
                    e,
                    context=context,
                    result=llm_result,
                    previous_events=annotated_events,
                    extra={"primary_events": primary_events, "allowed_events": allowed_events},
                )
                raise
            episode['scenario_time'] = context['scenario_time']
            episode['sampled_context'] = context.get('sampled_context', {})
            return episode
        except Exception as e:
            _log_llm_failure(
                "scenario_event_generation_attempt",
                e,
                context=context,
                previous_events=annotated_events,
                extra={
                    "attempt": attempt + 1,
                    "max_retries": max_retries,
                    "max_events": max_events,
                    "all_scenario_descriptions": all_scenario_descriptions,
                },
            )
            if attempt == max_retries - 1:
                return None

    return None




def format_person_room_status_schema():
    """
    格式化人物在不同房间中的可用状态枚举，作为 LLM 约束输入。
    """
    lines = []
    for room_id, statuses in PERSON_ROOM_STATUS_SCHEMA.items():
        lines.append(f"- {room_id}: {', '.join(statuses)}")
    lines.append("- 注意: 卧室中表示睡着必须使用 sleeping，不要使用 asleep。")
    return '\n'.join(lines)


def format_device_state_schema():
    """
    格式化设备状态枚举，作为 LLM 约束输入。
    """
    lines = []
    for device_id, states in DEVICE_STATES.items():
        lines.append(f"- {device_id}: {', '.join(states)}")
    return '\n'.join(lines)


def validate_llm_episode_result(result, scenario, episode_date, default_subject, 
                                 default_home, person_ids, available_devices, time_range,
                                 primary_events=None, allowed_events=None, household_layout=None):
    """
    验证 LLM 生成的 episode 结果。
    
    Args:
        result: LLM 返回的结果
        scenario: 场景类型
        episode_date: episode日期
        default_subject: 默认主体ID
        default_home: 默认家庭ID
        person_ids: 可用的人员ID列表
        available_devices: 可用的设备ID列表
        time_range: 时间范围
        
    Returns:
        dict: 验证后的 episode
        
    Raises:
        ValueError: 验证失败时抛出异常
    """
    # 检查必需字段
    if 'daily_state_description' not in result:
        raise ValueError("Missing daily_state_description")
    
    if 'annotated_events' not in result:
        raise ValueError("Missing annotated_events")
    
    annotated_events = result['annotated_events']
    
    primary_events = primary_events or []
    allowed_events = allowed_events or primary_events
    min_event_count = len(primary_events) if primary_events else 1
    max_event_count = len(allowed_events) if allowed_events else max(min_event_count, 1)
    
    # 检查事件数量：必须包含主事件，相关设备事件按当天家庭状态选择。
    if len(annotated_events) < min_event_count or len(annotated_events) > max_event_count:
        raise ValueError(
            f"Invalid number of events: {len(annotated_events)}, expected {min_event_count}-{max_event_count} scene events"
        )
    
    allowed_event_map = {
        (
            default_subject,
            event.get('event_type', ''),
            event.get('predicate', ''),
            event.get('object_id', '')
        ): event
        for event in allowed_events
    }
    required_event_keys = {
        (
            default_subject,
            event.get('event_type', ''),
            event.get('predicate', ''),
            event.get('object_id', '')
        )
        for event in primary_events
    }
    seen_event_keys = set()
    
    # 验证每个事件
    prev_timestamp = None
    for i, event_data in enumerate(annotated_events):
        # 检查 event 字段
        if 'event' not in event_data:
            raise ValueError(f"Event {i} missing 'event' field")
        
        event = event_data['event']
        
        # 检查必需的 event 字段
        if 'subject_id' not in event:
            raise ValueError(f"Event {i} missing subject_id")
        if 'predicate' not in event:
            raise ValueError(f"Event {i} missing predicate")
        if 'object_id' not in event:
            raise ValueError(f"Event {i} missing object_id")
        if 'attributes' not in event:
            event['attributes'] = {}
        event['subject_id'] = default_subject
        
        # 验证 subject_id 在可用人员列表或系统执行主体中
        if event['subject_id'] not in person_ids and event['subject_id'] not in {'home_assistant', 'system', 'visitor'}:
            raise ValueError(f"Event {i} has invalid subject_id: {event['subject_id']}")
        
        # 验证 object_id 在可用设备列表中
        if event['object_id'] not in available_devices:
            raise ValueError(f"Event {i} has invalid object_id: {event['object_id']}")
        
        actual_type = event.get('attributes', {}).get('event_type', '')
        event_key = (event['subject_id'], actual_type, event['predicate'], event['object_id'])
        if allowed_event_map and event_key not in allowed_event_map:
            raise ValueError(f"Event {i} is not an allowed scene event: {event_key}")
        if event_key in seen_event_keys:
            raise ValueError(f"Event {i} duplicates an earlier scene event: {event_key}")
        seen_event_keys.add(event_key)
        
        # 检查 state_snapshot 字段
        if 'state_snapshot' not in event_data:
            raise ValueError(f"Event {i} missing state_snapshot")
        
        snapshot = event_data['state_snapshot']
        
        # 检查必需的 snapshot 字段
        if 'timestamp' not in snapshot:
            raise ValueError(f"Event {i} missing timestamp")
        if 'persons' not in snapshot:
            raise ValueError(f"Event {i} missing persons in state_snapshot")
        if 'devices' not in snapshot:
            raise ValueError(f"Event {i} missing devices in state_snapshot")
        if 'space_occupancy' not in snapshot:
            raise ValueError(f"Event {i} missing space_occupancy in state_snapshot")
        validate_person_states(snapshot, person_ids)
        validate_device_states(snapshot)
        validate_space_occupancy(snapshot)
        
        # 验证时间戳格式和递增性
        try:
            current_timestamp = datetime.fromisoformat(snapshot['timestamp'].replace('+08:00', ''))
            if prev_timestamp and current_timestamp < prev_timestamp:
                raise ValueError(f"Event {i} timestamp goes backwards: {snapshot['timestamp']}")
            prev_timestamp = current_timestamp
        except ValueError as e:
            raise ValueError(f"Event {i} has invalid timestamp format: {e}")
    
    missing_required = required_event_keys - seen_event_keys
    if missing_required:
        raise ValueError(f"Missing required primary events: {sorted(missing_required)}")

    first_event_time = None
    if annotated_events:
        first_event_time = annotated_events[0].get('state_snapshot', {}).get('timestamp')
    
    # 构建完整的 episode
    episode = {
        "episode_id": build_episode_id(default_subject, scenario, episode_date, first_event_time, time_range),
        "home_id": default_home,
        "scene": scenario,
        "subject_id": default_subject,
        "confidence": round(0.85 + random.random() * 0.1, 2),
        "date": episode_date.isoformat(),
        "household_layout": household_layout or get_household_room_layout({}),
        "household_state_description": result['household_state_description'],
        "device_event_description": result['device_event_description'],
        "daily_state_description": result['daily_state_description'],
        "annotated_events": annotated_events
    }
    
    return episode


def generate_scenario_device_episodes(scenario, num_days=7, household_profile=None, 
                                      scene_templates=None, device_file=None, use_llm=True,
                                      subject_id=None, subject_profile=None):
    """
    生成连续多日的设备事件episodes。
    
    Args:
        scenario: 场景类型（如 'family_return'）
        num_days: 生成天数，默认7天
        household_profile: 家庭画像字典（可选）
        scene_templates: 场景模板字典（可选）
        device_file: 设备配置文件路径（可选）
        use_llm: 是否使用LLM生成（默认True）
        
    Returns:
        list: episodes列表，每个episode包含annotated_events
    """
    scenario = canonicalize_scenario(scenario)
    
    if scene_templates is None:
        scene_templates = SCENE_TEMPLATES
    
    if household_profile is None:
        household_profile = {}
    
    # 获取场景模板
    template = scene_templates.get(scenario)
    if not template:
        logging.error(f"Unknown scenario: {scenario}")
        return []
    
    # 获取默认参数
    default_subject = subject_id or template.get('default_subject', 'dad')
    default_home = template.get('default_home', 'home_1')
    core_events = template.get('core_events', [])
    noise_events = template.get('noise_events', [])
    time_window = template.get('time_window', {})
    
    episodes = []
    
    # 获取家庭画像信息
    members = household_profile.get('members', {})
    relations = household_profile.get('relations', {})
    family_info = household_profile.get('family', {})
    
    # 获取家庭成员映射（结合家庭画像和默认映射）
    person_ids = get_person_ids_from_household(household_profile)
    if default_subject not in person_ids:
        person_ids.append(default_subject)
    
    # 确定起始日期（从今天往前推num_days天）
    start_date = datetime.now().date() - timedelta(days=num_days - 1)
    
    # 为每一天生成一个episode
    for day_offset in range(num_days):
        episode_date = start_date + timedelta(days=day_offset)
        if should_skip_scene_by_calendar(scenario, episode_date):
            logging.info("Skipping %s for %s due to calendar constraints", scenario, episode_date)
            continue
        
        if use_llm:
            # 使用 LLM 生成 episode
            episode = generate_single_day_episode_llm(
                scenario=scenario,
                episode_date=episode_date,
                day_offset=day_offset,
                template=template,
                household_profile=household_profile,
                person_ids=person_ids,
                device_file=device_file,
                subject_id=default_subject
            )
            if episode and episode.get('_skip'):
                continue
            
            # 如果 LLM 生成失败，回退到规则模板生成
            if not episode:
                logging.warning(f"LLM generation failed for {episode_date}, falling back to rule-based generation")
                episode = generate_single_day_episode_rule_based(
                    scenario=scenario,
                    episode_date=episode_date,
                    day_offset=day_offset,
                    template=template,
                    core_events=core_events,
                    noise_events=noise_events,
                    time_window=time_window,
                    default_subject=default_subject,
                    default_home=default_home,
                    household_profile=household_profile,
                    person_ids=person_ids
                )
        else:
            # 使用规则模板生成
            episode = generate_single_day_episode_rule_based(
                scenario=scenario,
                episode_date=episode_date,
                day_offset=day_offset,
                template=template,
                core_events=core_events,
                noise_events=noise_events,
                time_window=time_window,
                default_subject=default_subject,
                default_home=default_home,
                household_profile=household_profile,
                person_ids=person_ids
            )
        
        if episode:
            if subject_profile:
                episode['subject_profile'] = subject_profile
            episodes.append(episode)
    
    logging.info(f"Generated {len(episodes)} episodes for scenario '{scenario}'")
    return episodes


def should_skip_scene_by_calendar(scenario, episode_date):
    """
    规则兜底下的日历约束：周末不生成工作日/上学日强绑定场景。
    LLM 路径会在状态描述阶段做更细判断。
    """
    if episode_date.weekday() >= 5 and scenario in {'leave_work', 'family_return', 'child_return'}:
        return True
    return False


def generate_single_day_episode_rule_based(scenario, episode_date, day_offset, template,
                                           core_events, noise_events, time_window,
                                           default_subject, default_home,
                                           household_profile, person_ids):
    """
    使用规则模板生成单日的设备事件episode（原有逻辑）。
    
    Args:
        scenario: 场景类型
        episode_date: episode日期
        day_offset: 天数偏移（从开始算起）
        template: 场景模板
        core_events: 核心事件列表
        noise_events: 噪声事件列表
        time_window: 时间窗口配置
        default_subject: 默认主体ID
        default_home: 默认家庭ID
        household_profile: 家庭画像
        person_ids: 可用的人员ID列表
        
    Returns:
        dict: episode字典
    """
    # 确定时间窗口（是否是晚归日）
    is_late_day = is_late_work_day(day_offset, num_days=7)
    time_range = time_window.get('late' if is_late_day else 'normal', time_window.get('normal'))
    
    start_time = time_range.get('start', '17:00')
    end_time = time_range.get('end', '22:30')
    
    # 生成时间戳
    base_timestamp = generate_timestamp(episode_date, start_time, end_time)
    
    current_state = initialize_state(person_ids)
    all_events = get_primary_events(template)
    all_events.extend(select_contextual_related_events(template, current_state))
    
    # 生成annotated_events
    annotated_events = []
    event_time = base_timestamp
    
    for event_data in all_events:
        current_state = prepare_state_for_primary_event(current_state, event_data, default_subject)
        # 创建事件前的状态快照
        state_snapshot = create_state_snapshot(
            timestamp=event_time.isoformat(),
            persons=current_state['persons'],
            devices=current_state['devices'].copy(),
            space_occupancy=current_state['space_occupancy'].copy()
        )
        
        # 创建事件对象
        event_obj = {
            "event": {
                "subject_id": event_data.get('subject_id', default_subject),
                "predicate": event_data['predicate'],
                "object_id": event_data['object_id'],
                "attributes": {
                    "event_type": event_data.get('event_type', ''),
                    "description": event_data.get('description', '')
                }
            },
            "state_snapshot": state_snapshot
        }
        
        annotated_events.append(event_obj)
        
        # 更新状态机
        current_state = apply_event_to_state(current_state, event_data)
        
        # 增加时间（30秒到5分钟之间）
        time_increment = timedelta(seconds=random.randint(30, 300))
        event_time += time_increment
    
    # 生成episode
    episode = {
        "episode_id": build_episode_id(default_subject, scenario, episode_date, base_timestamp, time_window),
        "home_id": default_home,
        "scene": scenario,
        "subject_id": default_subject,
        "confidence": round(0.85 + random.random() * 0.1, 2),
        "date": episode_date.isoformat(),
        "household_layout": get_household_room_layout(household_profile),
        "daily_state_description": f"基于规则模板生成的{template.get('name', scenario)}场景，只记录当天的场景主要事件和对应设备状态。",
        "annotated_events": annotated_events
    }
    
    return episode



def generate_single_day_episode(scenario, episode_date, day_offset, template,
                                core_events, noise_events, time_window,
                                default_subject, default_home,
                                household_profile, person_ids):
    """
    生成单日的设备事件episode。
    
    Args:
        scenario: 场景类型
        episode_date: episode日期
        day_offset: 天数偏移（从开始算起）
        template: 场景模板
        core_events: 核心事件列表
        noise_events: 噪声事件列表
        time_window: 时间窗口配置
        default_subject: 默认主体ID
        default_home: 默认家庭ID
        household_profile: 家庭画像
        person_ids: 可用的人员ID列表
        
    Returns:
        dict: episode字典
    """
    # 确定时间窗口（是否是晚归日）
    is_late_day = is_late_work_day(day_offset, num_days=7)
    time_range = time_window.get('late' if is_late_day else 'normal', time_window.get('normal'))
    
    start_time = time_range.get('start', '17:00')
    end_time = time_range.get('end', '22:30')
    
    # 生成时间戳
    base_timestamp = generate_timestamp(episode_date, start_time, end_time)
    
    # 选择核心事件数量（2-5条）
    num_core_events = random.randint(2, min(5, len(core_events)))
    
    # 随机选择核心事件（保持顺序）
    selected_core_events = select_core_events(core_events, num_core_events)
    
    # 选择噪声事件数量（0-3条）
    num_noise_events = random.randint(0, min(3, len(noise_events)))
    
    # 随机选择噪声事件
    selected_noise_events = random.sample(noise_events, num_noise_events) if num_noise_events > 0 else []
    
    # 合并并排序事件
    all_events = merge_and_sort_events(selected_core_events, selected_noise_events)
    
    # 生成annotated_events
    annotated_events = []
    current_state = initialize_state(person_ids)
    event_time = base_timestamp
    
    for event_data in all_events:
        # 创建事件前的状态快照
        state_snapshot = create_state_snapshot(
            timestamp=event_time.isoformat(),
            persons=current_state['persons'],
            devices=current_state['devices'].copy()
        )
        
        # 创建事件对象
        event_obj = {
            "event": {
                "subject_id": event_data.get('subject_id', default_subject),
                "predicate": event_data['predicate'],
                "object_id": event_data['object_id'],
                "attributes": {
                    "event_type": event_data.get('event_type', ''),
                    "description": event_data.get('description', '')
                }
            },
            "state_snapshot": state_snapshot
        }
        
        annotated_events.append(event_obj)
        
        # 更新状态机
        current_state = apply_event_to_state(current_state, event_data)
        
        # 增加时间（30秒到5分钟之间）
        time_increment = timedelta(seconds=random.randint(30, 300))
        event_time += time_increment
    
    # 生成episode
    episode = {
        "episode_id": build_episode_id(default_subject, scenario, episode_date, base_timestamp, time_window),
        "home_id": default_home,
        "scene": scenario,
        "subject_id": default_subject,
        "confidence": round(0.85 + random.random() * 0.1, 2),
        "date": episode_date.isoformat(),
        "annotated_events": annotated_events
    }
    
    return episode


def is_late_work_day(day_offset, num_days=7):
    """
    判断某天是否是晚归日（噪声日）。
    
    Args:
        day_offset: 天数偏移
        num_days: 总天数
        
    Returns:
        bool: True表示晚归日
    """
    # 大约20%的概率是晚归日
    if random.random() < 0.2:
        return True
    
    # 周五更容易晚归
    if (datetime.now().date() - timedelta(days=num_days - 1 - day_offset)).weekday() == 4:
        if random.random() < 0.4:
            return True
    
    return False


def generate_timestamp(episode_date, start_time, end_time):
    """
    在时间窗口内生成随机时间戳。
    
    Args:
        episode_date: 日期
        start_time: 开始时间字符串（如 '17:00'）
        end_time: 结束时间字符串（如 '22:30'）
        
    Returns:
        datetime: 生成的时间戳
    """
    # 解析开始和结束时间
    start_hour, start_min = map(int, start_time.split(':'))
    end_hour, end_min = map(int, end_time.split(':'))
    
    # 处理跨午夜的情况
    if end_hour < start_hour:
        end_hour += 24
    
    # 计算时间范围（分钟）
    start_total = start_hour * 60 + start_min
    end_total = end_hour * 60 + end_min
    
    # 随机选择时间
    random_total = random.randint(start_total, end_total)
    
    # 转换回小时和分钟
    hour = random_total // 60
    minute = random_total % 60
    
    # 处理跨天
    if hour >= 24:
        hour -= 24
        episode_date += timedelta(days=1)
    
    return datetime(episode_date.year, episode_date.month, episode_date.day, hour, minute, 0)


def select_core_events(core_events, num_events):
    """
    选择核心事件（保持顺序）。
    
    Args:
        core_events: 核心事件列表
        num_events: 需要选择的数量
        
    Returns:
        list: 选中的事件列表
    """
    if len(core_events) <= num_events:
        return core_events.copy()
    
    # 确保首尾事件被选中（保证完整性）
    selected = [core_events[0]]
    
    # 选择中间事件
    middle_indices = list(range(1, len(core_events) - 1))
    selected_indices = sorted(random.sample(middle_indices, min(num_events - 2, len(middle_indices))))
    
    for idx in selected_indices:
        selected.append(core_events[idx])
    
    # 添加最后一个事件
    if len(selected) < num_events and len(core_events) > 1:
        selected.append(core_events[-1])
    
    return selected


def merge_and_sort_events(core_events, noise_events):
    """
    合并核心事件和噪声事件，并保持合理的顺序。
    
    Args:
        core_events: 核心事件列表
        noise_events: 噪声事件列表
        
    Returns:
        list: 合并后的事件列表
    """
    # 噪声事件可以插入到核心事件之间
    if not noise_events:
        return core_events
    
    result = []
    noise_idx = 0
    
    for i, core_event in enumerate(core_events):
        result.append(core_event)
        
        # 有一定概率在核心事件之间插入噪声事件
        if noise_idx < len(noise_events) and random.random() < 0.4:
            result.append(noise_events[noise_idx])
            noise_idx += 1
    
    # 添加剩余的噪声事件
    result.extend(noise_events[noise_idx:])
    
    return result


def initialize_state(person_ids):
    """
    初始化状态（事件发生前的默认状态）。
    
    Args:
        person_ids: 人员ID列表
        
    Returns:
        dict: 初始状态
    """
    # 初始化人员状态
    persons = {}
    for person_id in person_ids:
        # 根据人员角色设置初始状态
        if person_id == 'dad':
            persons[person_id] = {"status": "outside", "location": "outside"}
        elif person_id == 'mom':
            persons[person_id] = {"status": "cooking", "location": "kitchen"}
        elif person_id == 'grandpa':
            persons[person_id] = {"status": "resting", "location": "living_room"}
        elif person_id == 'grandma':
            persons[person_id] = {"status": "resting", "location": "bedroom"}
        elif person_id == 'child':
            persons[person_id] = {"status": "studying", "location": "study"}
        else:
            persons[person_id] = {"status": "outside", "location": "outside"}
    
    # 初始化设备状态
    devices = {
        "wifi_router": {"state": "online"},
        "door_camera": {"state": "idle"},
        "door_main": {"state": "locked"},
        "door_bedroom": {"state": "closed"},
        "door_bell": {"state": "silent"},
        "temp_humidity_sensor": {"state": "normal"},
        "light_sensor": {"state": "bright"},
        "air_quality_sensor": {"state": "good"},
        "light_hallway": {"state": "off"},
        "light_living_room": {"state": "off"},
        "light_bedroom": {"state": "off"},
        "light_study": {"state": "off"},
        "light_bathroom": {"state": "off"},
        "ac_living_room": {"state": "off"},
        "ac_bedroom": {"state": "off"},
        "tv_living_room": {"state": "off"},
        "tv_bedroom": {"state": "off"},
        "curtain_living_room": {"state": "open"},
        "curtain_bedroom": {"state": "closed"},
        "fresh_air_system": {"state": "off"},
        "security_system": {"state": "disarmed"},
        "motion_sensor": {"state": "clear"},
        "security_camera": {"state": "idle"},
        "coffee_machine": {"state": "idle"},
        "smart_speaker": {"state": "idle"}
    }
    
    return {
        "persons": persons,
        "devices": devices,
        "space_occupancy": build_space_occupancy_from_persons(persons)
    }


def select_contextual_related_events(template, current_state):
    """
    根据当天家庭状态选择会被场景触发的相关设备事件。
    """
    related_events = template.get('related_events', [])
    if not related_events:
        return []

    selected = []
    scenario_name = template.get('name', '')
    living_room_occupied = random.random() < 0.35
    bedroom_occupied = random.random() < 0.25
    if '上班离家' in scenario_name:
        if not living_room_occupied and 'grandpa' in current_state['persons']:
            current_state['persons']['grandpa'] = {"status": "resting", "location": "bedroom"}
        if living_room_occupied and 'grandpa' in current_state['persons']:
            current_state['persons']['grandpa'] = {"status": "watching_tv", "location": "living_room"}
        refresh_space_occupancy_from_persons(current_state)

    for event in related_events:
        event_type = event.get('event_type', '')

        if '上班离家' in scenario_name:
            if event_type == 'lock_main_door':
                selected.append(event.copy())
            elif event_type in {
                'turn_off_living_room_light',
                'turn_off_living_room_tv',
                'turn_off_living_room_ac',
            } and not living_room_occupied:
                selected.append(event.copy())
            elif event_type in {
                'turn_off_bedroom_light',
                'turn_off_bedroom_ac',
            } and not bedroom_occupied:
                selected.append(event.copy())
        elif '下班回家' in scenario_name:
            if event_type == 'turn_on_living_room_light' and random.random() < 0.75:
                selected.append(event.copy())
            elif event_type == 'turn_on_living_room_ac' and random.random() < 0.55:
                selected.append(event.copy())
            elif event_type == 'turn_on_living_room_tv' and random.random() < 0.35:
                selected.append(event.copy())
        elif random.random() < 0.5:
            selected.append(event.copy())

    return selected


def create_state_snapshot(timestamp, persons, devices, space_occupancy=None):
    """
    创建状态快照。
    
    Args:
        timestamp: 时间戳字符串
        persons: 人员状态字典
        devices: 设备状态字典
        space_occupancy: 空间占用字典
        
    Returns:
        dict: 状态快照
    """
    return {
        "timestamp": timestamp,
        "persons": copy.deepcopy(persons),
        "devices": copy.deepcopy(devices),
        "space_occupancy": copy.deepcopy(space_occupancy or {})
    }


def prepare_state_for_primary_event(current_state, event_data, default_subject):
    """
    为场景级主事件准备快照状态，避免规则兜底沿用过细的过程状态。
    """
    state = {
        "persons": copy.deepcopy(current_state['persons']),
        "devices": copy.deepcopy(current_state['devices']),
        "space_occupancy": copy.deepcopy(current_state['space_occupancy'])
    }
    subject_id = event_data.get('subject_id', default_subject)
    event_type = event_data.get('event_type', '')
    object_id = event_data.get('object_id', '')
    predicate = event_data.get('predicate')

    if event_type in {'return_home', 'visitor_arrival'}:
        if subject_id in state['persons']:
            state['persons'][subject_id] = {"status": "arriving", "location": "entrance"}
        if object_id in state['devices']:
            state['devices'][object_id] = {"state": "closed" if object_id == "door_main" else state['devices'][object_id].get('state', 'idle')}
        refresh_space_occupancy_from_persons(state)
    elif event_type == 'arm_away_mode':
        for person_id in state['persons']:
            state['persons'][person_id] = {"status": "outside", "location": "outside"}
        if object_id in state['devices']:
            state['devices'][object_id] = {"state": "armed"}
        refresh_space_occupancy_from_persons(state)
    elif event_type == 'anomaly_detected' and object_id in state['devices']:
        state['devices'][object_id] = {"state": "clear"}
    elif event_type == 'lock_main_door' and object_id in state['devices']:
        state['devices'][object_id] = {"state": "closed"}
        if 'dad' in state['persons']:
            state['persons']['dad'] = {"status": "left_home", "location": "outside"}
        refresh_space_occupancy_from_persons(state)
    elif predicate == 'off' and object_id in state['devices']:
        state['devices'][object_id] = {"state": "on"}
    elif predicate == 'on' and object_id in state['devices']:
        state['devices'][object_id] = {"state": "off"}
    elif predicate == 'open' and object_id in state['devices']:
        state['devices'][object_id] = {"state": "closed"}
    elif predicate == 'closed' and object_id in state['devices']:
        state['devices'][object_id] = {"state": "open"}
    elif predicate == 'locked' and object_id in state['devices']:
        state['devices'][object_id] = {"state": "closed"}

    return state


def apply_event_to_state(current_state, event_data):
    """
    将事件应用到状态机，更新状态。
    
    Args:
        current_state: 当前状态
        event_data: 事件数据
        
    Returns:
        dict: 更新后的状态
    """
    new_state = {
        "persons": copy.deepcopy(current_state['persons']),
        "devices": copy.deepcopy(current_state['devices']),
        "space_occupancy": copy.deepcopy(current_state['space_occupancy'])
    }
    
    predicate = event_data['predicate']
    object_id = event_data['object_id']
    event_type = event_data.get('event_type', '')
    
    # 更新人员状态
    subject_id = event_data.get('subject_id', 'dad')
    if subject_id in new_state['persons']:
        if predicate in {'entered', 'returned', 'arrived'}:
            new_state['persons'][subject_id]['status'] = 'arriving'
            new_state['persons'][subject_id]['location'] = 'entrance'
        elif predicate == 'left':
            new_state['persons'][subject_id]['status'] = 'left_home'
            new_state['persons'][subject_id]['location'] = 'outside'
        elif predicate in {'open', 'closed', 'locked'} and object_id == 'door_main':
            new_state['persons'][subject_id]['status'] = 'leaving' if event_type in {
                'open_main_door', 'close_main_door', 'elderly_open_main_door', 'elderly_close_main_door'
            } else 'arriving'
            new_state['persons'][subject_id]['location'] = 'entrance'
        elif predicate == 'is':
            # 状态描述类事件
            if object_id == 'grandpa':
                new_state['persons']['grandpa']['status'] = 'sleeping'
                new_state['persons']['grandpa']['location'] = 'bedroom'
            elif object_id == 'child':
                new_state['persons']['child']['status'] = 'studying'
                new_state['persons']['child']['location'] = 'study'
            elif object_id == 'mom':
                new_state['persons']['mom']['status'] = 'cooking'
                new_state['persons']['mom']['location'] = 'kitchen'
    
    # 更新设备状态
    if object_id in new_state['devices']:
        device = new_state['devices'][object_id]
        if predicate in DEVICE_STATES.get(object_id, []):
            device['state'] = predicate
    
    refresh_space_occupancy_from_persons(new_state)
    
    return new_state


def get_device_events_summary(device_events):
    """
    获取设备事件的摘要信息。
    
    Args:
        device_events: 设备事件字典（支持两种格式）
        
    Returns:
        str: 摘要信息字符串
    """
    summary = []
    
    # 支持两种格式：新格式（包含episodes）和旧格式（包含sessions）
    if 'episodes' in device_events:
        episodes = device_events.get('episodes', [])
        summary.append(f"场景: {device_events.get('scenario', 'unknown')}")
        summary.append(f"Episode数量: {len(episodes)}")
        
        total_events = 0
        for episode in episodes:
            events = episode.get('annotated_events', [])
            total_events += len(events)
        
        summary.append(f"总事件数量: {total_events}")
        
        if episodes:
            first_date = episodes[0].get('date', 'unknown')
            last_date = episodes[-1].get('date', 'unknown')
            summary.append(f"日期范围: {first_date} - {last_date}")
    
    else:
        # 旧格式
        summary.append(f"场景: {device_events.get('scenario', 'unknown')}")
        
        sessions = device_events.get('sessions', {})
        summary.append(f"会话数量: {len(sessions)}")
        
        total_events = 0
        for session_name, session_data in sessions.items():
            if isinstance(session_data, dict):
                events = session_data.get('annotated_events', [])
                total_events += len(events)
        
        summary.append(f"总事件数量: {total_events}")
    
    return "\n".join(summary)


# ==================== 旧版函数（保持向后兼容） ====================

def generate_all_device_events(agents, args):
    """
    为所有会话生成设备事件记录。
    
    Args:
        agents: 包含 agent_a 和 agent_b 的列表
        args: 命令行参数
        
    Returns:
        dict: 所有会话的设备事件记录
    """
    agent_a, agent_b = agents[0], agents[1]
    
    all_device_events = {
        "scenario": args.scenario if hasattr(args, 'scenario') else 'unknown',
        "sessions": {}
    }
    
    # 确定需要处理的会话数量
    num_sessions = args.num_sessions if hasattr(args, 'num_sessions') else 20
    
    for sess_id in range(1, num_sessions + 1):
        # 检查会话是否存在
        if 'session_%s' % sess_id not in agent_b:
            break
        
        # 检查是否已有设备事件且不需要覆盖
        if 'device_events' in agent_b and f'session_{sess_id}_device_events' in agent_b:
            if not hasattr(args, 'overwrite_events') or not args.overwrite_events:
                logging.info(f"Device events for session {sess_id} already exist, skipping")
                all_device_events['sessions'][f'session_{sess_id}'] = agent_b[f'session_{sess_id}_device_events']
                continue
        
        # 生成设备事件（此功能已移至 remove.py）
        # 需要使用 LLM 生成，暂未实现
        logging.info(f"Session {sess_id} device events generation not implemented")
    
    return all_device_events


def save_device_events(agents, args, device_events):
    """
    保存设备事件记录到文件。
    
    Args:
        agents: 包含 agent_a 和 agent_b 的列表
        args: 命令行参数
        device_events: 设备事件字典
        
    Returns:
        str: 保存的文件路径
    """
    output_dir = args.out_dir
    
    # 保存到 JSON 文件
    output_file = os.path.join(output_dir, 'device_events.json')
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(device_events, f, ensure_ascii=False, indent=2)
    
    logging.info(f"Device events saved to: {output_file}")
    return output_file
