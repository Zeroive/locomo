"""
Household event generation utilities.

Events are generated before conversations and later selected into each session,
mirroring the original persona -> graph -> session flow.
"""

import json
import logging
import random
import re
from datetime import timedelta

from generative_agents.time_utils import catch_date, dateObj2Str, get_random_date


WEEKEND_SCENARIOS = [
    "weekend_family_outing",
    "weekend_home_relaxation",
    "family_meal_plan",
    "child_weekend_activity",
    "elderly_weekend_activity",
    "pet_weekend_care",
    "couple_leisure_plan",
    "visit_relatives",
    "conflicting_plans",
    "changed_weekend_plan",
]


SCENARIO_DIMENSIONS = {
    "weekend_family_outing": ["weekend_plan", "family_outing", "cross_member_reference"],
    "weekend_home_relaxation": ["weekend_plan", "home_activity", "leisure_activity"],
    "family_meal_plan": ["meal_arrangement", "role_responsibility"],
    "child_weekend_activity": ["child_activity", "temporary_schedule"],
    "elderly_weekend_activity": ["elderly_activity", "role_responsibility"],
    "pet_weekend_care": ["pet_care_routine", "role_responsibility"],
    "couple_leisure_plan": ["leisure_activity", "family_relationship"],
    "visit_relatives": ["family_outing", "cross_member_reference"],
    "conflicting_plans": ["preference_conflict", "cross_member_reference", "temporary_schedule"],
    "changed_weekend_plan": ["temporary_schedule", "weekend_plan"],
}


HOUSEHOLD_EVENT_PROMPT = """
你是家庭多用户 AI 助手测评数据集的事件记忆点生成器。

请根据给定 household_profile，为这个家庭生成周末/休闲主题的事件图。事件图后续会被用于生成用户与 AI 助手的对话，所以事件必须是可对话、可记忆、可追溯的家庭安排。

要求：
- 输出必须是 JSON 数组，不要输出 markdown。
- 数组长度必须是 {num_events}。
- 每个事件必须包含字段：
  - "id": "E1" 这种递增编号
  - "sub-event": 中文短句，描述具体家庭记忆点
  - "date": 日期，必须在 {start_date} 到 {end_date} 之间，格式如 "12 July, 2025"
  - "caused_by": 事件 id 数组；如果无因果则为空数组
  - "scenario_type": 必须从给定场景类型中选择
  - "participants": 家庭成员 person_id 数组，不能包含宠物
  - "mentioned_members": 被提及但非主要参与者的 person_id 数组
  - "memory_dimensions": 覆盖维度数组
- 必须至少包含一次 conflicting_plans 和一次 changed_weekend_plan。
- 如果家庭有宠物，可以生成 pet_weekend_care；宠物不能进入 participants。
- child / elderly / pet 相关事件必须匹配真实家庭成员和宠物信息。
- 事件之间尽量有少量因果关系，但 caused_by 只能引用更早的事件。

可选 scenario_type：
{scenario_types}

scenario_type 到 memory_dimensions 的参考映射：
{dimension_map}

household_profile：
{profile}
""".strip()


def parse_json_array(text):
    text = text.strip().replace("```json", "").replace("```", "").strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if not match:
            raise
        data = json.loads(match.group())
    if not isinstance(data, list):
        raise ValueError("Expected a JSON array")
    return data


def member_names(profile, ids):
    names = {member["person_id"]: member["name"] for member in profile["members"]}
    return [names[person_id] for person_id in ids if person_id in names]


def members_by_stage(profile, stages):
    return [member for member in profile["members"] if member.get("life_stage") in stages]


def choose_participants(profile, scenario_type):
    adults = members_by_stage(profile, {"adult"})
    elders = members_by_stage(profile, {"elderly"})
    children = members_by_stage(profile, {"child", "teenager"})
    members = profile["members"]

    if scenario_type == "child_weekend_activity" and children:
        return [random.choice(children)["person_id"]] + [random.choice(adults or members)["person_id"]]
    if scenario_type == "elderly_weekend_activity" and elders:
        return [random.choice(elders)["person_id"]] + [random.choice(adults or members)["person_id"]]
    if scenario_type == "pet_weekend_care" and profile.get("pets"):
        return [profile["pets"][0]["caretaker_id"]]
    if scenario_type == "couple_leisure_plan" and len(adults) >= 2:
        return [adults[0]["person_id"], adults[1]["person_id"]]
    if scenario_type in {"conflicting_plans", "changed_weekend_plan"}:
        sample_size = min(3, len(members))
        return [m["person_id"] for m in random.sample(members, sample_size)]
    sample_size = min(random.choice([2, 3]), len(members))
    return [m["person_id"] for m in random.sample(members, sample_size)]


def render_event(profile, scenario_type, participants):
    names = member_names(profile, participants)
    pet = profile.get("pets", [{}])[0] if profile.get("pets") else None
    primary = names[0] if names else "家人"
    secondary = names[1] if len(names) > 1 else "其他家人"

    templates = {
        "weekend_family_outing": f"{'、'.join(names)}计划周末上午一起去公园或商场，出门前需要确认天气和交通。",
        "weekend_home_relaxation": f"{primary}提议周末在家休息，{secondary}想安排电影、整理房间或简单运动。",
        "family_meal_plan": f"{'、'.join(names)}讨论周末家庭聚餐，决定提前准备食材或选择外卖。",
        "child_weekend_activity": f"{primary}周末有兴趣班或作业安排，{secondary}需要提醒时间并协调接送。",
        "elderly_weekend_activity": f"{primary}想周末去社区活动或散步，{secondary}需要关注出门时间和身体状况。",
        "pet_weekend_care": f"{primary}负责周末照看宠物{pet['name'] if pet else '宠物'}，需要安排喂食、清洁或遛宠。",
        "couple_leisure_plan": f"{primary}和{secondary}想安排一次夫妻二人的休闲活动，但要避开家庭其他事项。",
        "visit_relatives": f"{'、'.join(names)}计划周末探亲或接待亲友来访，需要提前协调用餐和到达时间。",
        "conflicting_plans": f"{'、'.join(names)}的周末安排出现冲突，有人想外出，有人更想在家休息。",
        "changed_weekend_plan": f"{primary}临时改变周末计划，{secondary}需要重新调整家庭活动和提醒事项。",
    }
    return templates[scenario_type]


def generate_template_household_events(profile, num_events, num_days=60, start_date=None):
    if start_date is None:
        start_date = get_random_date()
    end_date = start_date + timedelta(days=num_days)

    scenario_pool = list(WEEKEND_SCENARIOS)
    while len(scenario_pool) < num_events:
        scenario_pool.extend(WEEKEND_SCENARIOS)

    selected_scenarios = scenario_pool[:num_events]
    random.shuffle(selected_scenarios)
    if num_events >= 2:
        selected_scenarios[0] = "conflicting_plans"
        selected_scenarios[1] = "changed_weekend_plan"

    graph = []
    for idx, scenario_type in enumerate(selected_scenarios[:num_events], start=1):
        participants = choose_participants(profile, scenario_type)
        mentioned = [
            member["person_id"] for member in profile["members"]
            if member["person_id"] not in participants and random.random() < 0.35
        ]
        event_date = start_date + timedelta(days=min(num_days, idx * max(1, num_days // max(1, num_events))))
        caused_by = []
        if idx > 1 and scenario_type in {"changed_weekend_plan", "conflicting_plans"}:
            caused_by = [f"E{max(1, idx - 1)}"]
        graph.append({
            "id": f"E{idx}",
            "sub-event": render_event(profile, scenario_type, participants),
            "date": dateObj2Str(event_date),
            "caused_by": caused_by,
            "scenario_type": scenario_type,
            "participants": participants,
            "mentioned_members": mentioned,
            "memory_dimensions": SCENARIO_DIMENSIONS[scenario_type],
        })

    profile["events_start_date"] = dateObj2Str(start_date)
    profile["graph"] = graph
    profile["events_end_date"] = dateObj2Str(end_date)
    return graph


def normalize_event_graph(raw_events, profile, num_events, start_date, end_date):
    member_ids = {member["person_id"] for member in profile["members"]}
    normalized = []
    existing_ids = set()

    for idx, event in enumerate(raw_events[:num_events], start=1):
        if not isinstance(event, dict):
            continue
        event_id = str(event.get("id") or f"E{idx}")
        if not re.match(r"^E\d+$", event_id) or event_id in existing_ids:
            event_id = f"E{idx}"
        existing_ids.add(event_id)

        scenario_type = event.get("scenario_type")
        if scenario_type not in WEEKEND_SCENARIOS:
            scenario_type = WEEKEND_SCENARIOS[(idx - 1) % len(WEEKEND_SCENARIOS)]

        participants = [pid for pid in event.get("participants", []) if pid in member_ids]
        if not participants:
            participants = choose_participants(profile, scenario_type)
        mentioned = [
            pid for pid in event.get("mentioned_members", [])
            if pid in member_ids and pid not in participants
        ]

        caused_by = [
            eid for eid in event.get("caused_by", [])
            if eid in existing_ids and eid != event_id
        ]

        date_text = event.get("date") or dateObj2Str(start_date + timedelta(days=idx))
        try:
            event_date = catch_date(date_text)
            if event_date < catch_date(dateObj2Str(start_date)) or event_date > catch_date(dateObj2Str(end_date)):
                date_text = dateObj2Str(start_date + timedelta(days=idx))
        except Exception:
            date_text = dateObj2Str(start_date + timedelta(days=idx))

        normalized.append({
            "id": event_id,
            "sub-event": event.get("sub-event") or render_event(profile, scenario_type, participants),
            "date": date_text,
            "caused_by": caused_by,
            "scenario_type": scenario_type,
            "participants": participants,
            "mentioned_members": mentioned,
            "memory_dimensions": event.get("memory_dimensions") or SCENARIO_DIMENSIONS[scenario_type],
        })

    if len(normalized) < num_events:
        fallback = generate_template_household_events(profile, num_events, (end_date - start_date).days, start_date)
        seen = {event["id"] for event in normalized}
        normalized.extend([event for event in fallback if event["id"] not in seen][:num_events - len(normalized)])

    scenario_types = {event["scenario_type"] for event in normalized}
    if num_events >= 2 and "conflicting_plans" not in scenario_types:
        normalized[0]["scenario_type"] = "conflicting_plans"
        normalized[0]["memory_dimensions"] = SCENARIO_DIMENSIONS["conflicting_plans"]
    if num_events >= 2 and "changed_weekend_plan" not in scenario_types:
        normalized[1]["scenario_type"] = "changed_weekend_plan"
        normalized[1]["memory_dimensions"] = SCENARIO_DIMENSIONS["changed_weekend_plan"]

    return normalized[:num_events]


def generate_household_events(profile, num_events, num_days=60, start_date=None, use_llm=True):
    if start_date is None:
        start_date = get_random_date()
    end_date = start_date + timedelta(days=num_days)

    if not use_llm:
        logging.info("LLM disabled; generating household events with template fallback")
        return generate_template_household_events(profile, num_events, num_days, start_date)

    from global_methods import run_chatgpt

    prompt = HOUSEHOLD_EVENT_PROMPT.format(
        num_events=num_events,
        start_date=dateObj2Str(start_date),
        end_date=dateObj2Str(end_date),
        scenario_types=json.dumps(WEEKEND_SCENARIOS, ensure_ascii=False, indent=2),
        dimension_map=json.dumps(SCENARIO_DIMENSIONS, ensure_ascii=False, indent=2),
        profile=json.dumps(profile, ensure_ascii=False, indent=2),
    )
    try:
        logging.info(
            "Calling LLM for household event graph: family_id=%s, num_events=%s, date_range=%s~%s",
            profile.get("family", {}).get("family_id"),
            num_events,
            dateObj2Str(start_date),
            dateObj2Str(end_date),
        )
        response = run_chatgpt(prompt, num_gen=1, num_tokens_request=3000, temperature=1.0)
        logging.info("LLM household event response received: chars=%s", len(response or ""))
        raw_events = parse_json_array(response)
        graph = normalize_event_graph(raw_events, profile, num_events, start_date, end_date)
        logging.info("Normalized LLM household events: %s", len(graph))
    except Exception as exc:
        logging.warning("LLM household event generation failed, using template fallback: %s", exc)
        graph = generate_template_household_events(profile, num_events, num_days, start_date)

    profile["events_start_date"] = dateObj2Str(start_date)
    profile["graph"] = graph
    profile["events_end_date"] = dateObj2Str(end_date)
    profile["event_generation_prompt"] = prompt
    return graph


def sort_events_by_time(events):
    return sorted(events, key=lambda event: catch_date(event["date"]))


def get_household_session_date(events, num_events_per_session=2, prev_date=None):
    sorted_events = sort_events_by_time(events)
    eligible = []
    for event in sorted_events:
        event_date = catch_date(event["date"])
        if prev_date is None or event_date >= prev_date:
            eligible.append(event_date)
        if len(eligible) >= num_events_per_session:
            break
    if eligible:
        return eligible[-1] + timedelta(days=random.choice([1, 2]))
    if prev_date:
        return prev_date + timedelta(days=random.choice([3, 5, 7]))
    if sorted_events:
        return catch_date(sorted_events[0]["date"]) + timedelta(days=1)
    return get_random_date()


def get_relevant_household_events(events, curr_date, prev_date=None):
    selected = []
    for event in sort_events_by_time(events):
        event_date = catch_date(event["date"])
        if prev_date is not None:
            if prev_date <= event_date <= curr_date:
                selected.append(event)
        elif event_date <= curr_date:
            selected.append(event)
    return selected[-4:]
