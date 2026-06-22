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
from generative_agents.household_utils import strip_generation_prompts


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


SCENARIO_LABELS = {
    "weekend_family_outing": "周末全家外出",
    "weekend_home_relaxation": "周末居家休息",
    "family_meal_plan": "家庭聚餐/做饭/外卖",
    "child_weekend_activity": "孩子兴趣班/作业/玩耍",
    "elderly_weekend_activity": "老人散步/买菜/社区活动",
    "pet_weekend_care": "遛狗/喂猫/宠物看护",
    "couple_leisure_plan": "夫妻二人休闲安排",
    "visit_relatives": "探亲/亲友来访",
    "conflicting_plans": "家庭成员计划冲突",
    "changed_weekend_plan": "周末计划变更",
}


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


HOUSEHOLD_SINGLE_EVENT_PROMPT = """
你是家庭多用户 AI 助手测评数据集的事件记忆点生成器。

请根据已经由程序规划好的 event_plan，为这个家庭生成一个周末/休闲主题事件。

要求：
- 输出必须是 JSON 对象，不要输出 markdown。
- 必须保留 event_plan 中的 id、date、scenario_type、participants、mentioned_members、caused_by、memory_dimensions，不要改动。
- 只需要生成或补充 "sub-event"。
- sub-event 使用中文，30-60字，必须具体、自然、可用于后续用户与 AI 助手对话。
- sub-event 必须符合 scenario_type、参与成员角色、家庭关系、宠物信息和时间先后逻辑。
- 如果 caused_by 非空，sub-event 要自然体现它是由 previous_events 中的前置事件引发或调整而来。
- 不要引入 household_profile 中不存在的新成员。
- 宠物只能作为照护对象，不能作为 participants。

关键信息:
{context}

previous_events:
{previous_events}

event_plan:
{event_plan}
""".strip()


SCENARIO_GUIDANCE = {
    "weekend_family_outing": "全家或多名成员外出，重点是地点、出门准备、交通或天气。",
    "weekend_home_relaxation": "居家休息，重点是家庭成员休闲偏好和家务/娱乐安排。",
    "family_meal_plan": "家庭聚餐、做饭、外食或外卖安排，体现责任分工。",
    "child_weekend_activity": "孩子兴趣班、作业、玩耍或接送安排，必须有孩子或青少年参与。",
    "elderly_weekend_activity": "老人散步、买菜、社区活动或探亲，必须有老人参与。",
    "pet_weekend_care": "宠物喂养、遛宠、清洁或看护，只让照护人参与，宠物不作为用户。",
    "couple_leisure_plan": "夫妻/伴侣二人休闲安排，体现与其他家庭事项的协调。",
    "visit_relatives": "探亲或亲友来访，体现用餐、到达时间或接待准备。",
    "conflicting_plans": "多个成员周末偏好或时间冲突，后续可能需要协调。",
    "changed_weekend_plan": "已有安排发生变更，必须引用或承接一个更早事件。",
}


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


def parse_json_object(text):
    text = text.strip().replace("```json", "").replace("```", "").strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise
        data = json.loads(match.group())
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object")
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


def scenario_is_applicable(profile, scenario_type):
    if scenario_type == "child_weekend_activity":
        return bool(members_by_stage(profile, {"child", "teenager"}))
    if scenario_type == "elderly_weekend_activity":
        return bool(members_by_stage(profile, {"elderly"}))
    if scenario_type == "pet_weekend_care":
        return bool(profile.get("pets"))
    if scenario_type == "couple_leisure_plan":
        return len(members_by_stage(profile, {"adult"})) >= 2
    return True


def build_event_scenario_sequence(profile, num_events):
    required = ["conflicting_plans", "changed_weekend_plan"] if num_events >= 2 else ["conflicting_plans"]
    candidates = [scenario for scenario in WEEKEND_SCENARIOS if scenario_is_applicable(profile, scenario)]
    sequence = []
    for scenario in required:
        if scenario_is_applicable(profile, scenario):
            sequence.append(scenario)
    for scenario in candidates:
        if scenario not in sequence:
            sequence.append(scenario)
    while len(sequence) < num_events:
        sequence.append(random.choice(candidates or ["weekend_home_relaxation"]))
    # Keep changed_weekend_plan after at least one event so it can refer backward.
    if "changed_weekend_plan" in sequence and sequence.index("changed_weekend_plan") == 0 and len(sequence) > 1:
        sequence[0], sequence[1] = sequence[1], sequence[0]
    return sequence[:num_events]


def build_event_plan(profile, idx, scenario_type, start_date, num_days, num_events, previous_events):
    spacing = max(2, num_days // max(1, num_events))
    event_date = start_date + timedelta(days=min(num_days, idx * spacing))
    participants = choose_participants(profile, scenario_type)
    mentioned = [
        member["person_id"] for member in profile["members"]
        if member["person_id"] not in participants and random.random() < 0.35
    ]
    caused_by = []
    if previous_events and scenario_type == "changed_weekend_plan":
        caused_by = [previous_events[-1]["id"]]
    elif previous_events and scenario_type == "conflicting_plans" and random.random() < 0.5:
        caused_by = [previous_events[-1]["id"]]
    return {
        "id": f"E{idx}",
        "date": dateObj2Str(event_date),
        "scenario_type": scenario_type,
        "scenario_category": scenario_type,
        "scenario_label": SCENARIO_LABELS[scenario_type],
        "scenario_guidance": SCENARIO_GUIDANCE.get(scenario_type, ""),
        "participants": participants,
        "mentioned_members": mentioned,
        "caused_by": caused_by,
        "memory_dimensions": SCENARIO_DIMENSIONS[scenario_type],
    }


def compact_member_for_event(member):
    member = strip_generation_prompts(member)
    traits = member.get("traits", {})
    preferences = "、".join(traits.get("preferences", [])[:2])
    routines = "、".join(traits.get("daily_routines", [])[:1])
    return {
        "person_id": member["person_id"],
        "name": member["name"],
        "age": member.get("age"),
        "life_stage": member.get("life_stage"),
        "family_role_label": member.get("family_role_label"),
        "summary": member.get("persona_summary", ""),
        "traits": "；".join([item for item in [preferences, routines] if item]),
    }


def build_event_prompt_context(profile, event_plan, previous_events):
    profile = strip_generation_prompts(profile)
    previous_events = strip_generation_prompts(previous_events)
    relevant_ids = set(event_plan.get("participants", [])) | set(event_plan.get("mentioned_members", []))
    members = [
        compact_member_for_event(member)
        for member in profile.get("members", [])
        if member["person_id"] in relevant_ids
    ]
    relations = [
        rel for rel in profile.get("relations", [])
        if rel.get("from") in relevant_ids and rel.get("to") in relevant_ids
    ]
    pets = [
        pet for pet in profile.get("pets", [])
        if pet.get("caretaker_id") in relevant_ids
    ]
    responsibilities = [
        item for item in profile.get("role_responsibilities", [])
        if item.get("person_id") in relevant_ids
    ]
    previous_event_summaries = [
        {
            "id": event["id"],
            "date": event["date"],
            "scenario_type": event["scenario_type"],
            "sub-event": event["sub-event"],
        }
        for event in previous_events[-3:]
        if event["id"] in event_plan.get("caused_by", []) or event_plan.get("scenario_type") in {"changed_weekend_plan", "conflicting_plans"}
    ]
    return {
        "family": {
            "family_id": profile.get("family", {}).get("family_id"),
            "family_name": profile.get("family", {}).get("family_name"),
            "household_type": profile.get("family", {}).get("household_type"),
            "weekend_context": profile.get("family", {}).get("weekend_context"),
        },
        "relevant_members": members,
        "relevant_relations": relations,
        "relevant_pets": pets,
        "relevant_responsibilities": responsibilities,
        "previous_events": previous_event_summaries,
    }


def format_event_context_text(prompt_context):
    family = prompt_context["family"]
    lines = [
        f"家庭: {family.get('family_name')}，类型={family.get('household_type')}。",
    ]
    if family.get("weekend_context"):
        lines.append(f"周末背景: {family['weekend_context']}")
    if prompt_context["relevant_members"]:
        member_text = []
        for member in prompt_context["relevant_members"]:
            desc = f"{member['person_id']}={member['name']}({member.get('age')}岁,{member.get('family_role_label')},{member.get('life_stage')})"
            if member.get("traits"):
                desc += f"，特征:{member['traits']}"
            if member.get("summary"):
                desc += f"，简介:{member['summary']}"
            member_text.append(desc)
        lines.append("相关成员: " + "；".join(member_text))
    if prompt_context["relevant_relations"]:
        relations = [
            f"{rel['from']}-{rel['type']}-{rel['to']}"
            for rel in prompt_context["relevant_relations"][:4]
        ]
        lines.append("相关关系: " + "；".join(relations))
    if prompt_context["relevant_pets"]:
        pets = [
            f"{pet.get('pet_id')}={pet.get('name')}({pet.get('species')}),照护人={pet.get('caretaker_id')}"
            for pet in prompt_context["relevant_pets"]
        ]
        lines.append("相关宠物: " + "；".join(pets))
    if prompt_context["relevant_responsibilities"]:
        responsibilities = [
            f"{item.get('person_id')}:{item.get('responsibility', '')}"
            for item in prompt_context["relevant_responsibilities"][:4]
        ]
        lines.append("相关责任: " + "；".join(responsibilities))
    return "\n".join(lines)


def compact_previous_events_for_prompt(previous_events):
    return "\n".join([
        f"{event['id']}({event['date']},{event['scenario_type']}): {event['sub-event']}"
        for event in previous_events[-2:]
    ]) or "无"


def compact_event_plan_for_prompt(event_plan):
    return {
        "id": event_plan["id"],
        "date": event_plan["date"],
        "scenario_type": event_plan["scenario_type"],
        "scenario_label": event_plan["scenario_label"],
        "scenario_guidance": event_plan["scenario_guidance"],
        "participants": event_plan["participants"],
        "mentioned_members": event_plan["mentioned_members"],
        "caused_by": event_plan["caused_by"],
        "memory_dimensions": event_plan["memory_dimensions"],
    }


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

    graph = []
    selected_scenarios = build_event_scenario_sequence(profile, num_events)
    for idx, scenario_type in enumerate(selected_scenarios[:num_events], start=1):
        event_plan = build_event_plan(profile, idx, scenario_type, start_date, num_days, num_events, graph)
        graph.append({
            "id": event_plan["id"],
            "sub-event": render_event(profile, scenario_type, event_plan["participants"]),
            "date": event_plan["date"],
            "caused_by": event_plan["caused_by"],
            "scenario_type": scenario_type,
            "scenario_category": scenario_type,
            "scenario_label": SCENARIO_LABELS[scenario_type],
            "participants": event_plan["participants"],
            "mentioned_members": event_plan["mentioned_members"],
            "memory_dimensions": SCENARIO_DIMENSIONS[scenario_type],
        })

    profile["events_start_date"] = dateObj2Str(start_date)
    profile["graph"] = graph
    profile["events_end_date"] = dateObj2Str(end_date)
    applicable_scenarios = [scenario for scenario in WEEKEND_SCENARIOS if scenario_is_applicable(profile, scenario)]
    generated_scenarios = [event["scenario_type"] for event in graph]
    profile["event_scenario_catalog"] = {
        scenario: {
            "label": SCENARIO_LABELS[scenario],
            "memory_dimensions": SCENARIO_DIMENSIONS[scenario],
            "guidance": SCENARIO_GUIDANCE[scenario],
            "applicable": scenario in applicable_scenarios,
        }
        for scenario in WEEKEND_SCENARIOS
    }
    profile["event_scenario_coverage"] = {
        "generated": generated_scenarios,
        "covered": sorted(set(generated_scenarios)),
        "applicable": applicable_scenarios,
        "missing_applicable": [scenario for scenario in applicable_scenarios if scenario not in generated_scenarios],
    }
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


def normalize_single_event(raw_event, event_plan, profile):
    member_ids = {member["person_id"] for member in profile["members"]}
    event = dict(event_plan)
    if isinstance(raw_event, dict) and raw_event.get("sub-event"):
        event["sub-event"] = raw_event["sub-event"]
    else:
        event["sub-event"] = render_event(profile, event_plan["scenario_type"], event_plan["participants"])
    event["participants"] = [pid for pid in event_plan["participants"] if pid in member_ids]
    event["mentioned_members"] = [pid for pid in event_plan["mentioned_members"] if pid in member_ids and pid not in event["participants"]]
    event["caused_by"] = list(event_plan.get("caused_by", []))
    event["memory_dimensions"] = SCENARIO_DIMENSIONS[event_plan["scenario_type"]]
    event["scenario_category"] = event_plan["scenario_type"]
    event["scenario_label"] = SCENARIO_LABELS[event_plan["scenario_type"]]
    event.pop("scenario_guidance", None)
    return event


def validate_event_timeline(graph, profile):
    member_ids = {member["person_id"] for member in profile.get("members", [])}
    event_dates = {}
    previous_date = None
    for event in graph:
        event_date = catch_date(event["date"])
        if previous_date and event_date < previous_date:
            raise ValueError(f"Event dates are not non-decreasing at {event['id']}")
        previous_date = event_date
        event_dates[event["id"]] = event_date
        unknown_participants = set(event.get("participants", [])) - member_ids
        if unknown_participants:
            raise ValueError(f"Event {event['id']} has unknown participants: {unknown_participants}")
        for cause_id in event.get("caused_by", []):
            if cause_id not in event_dates:
                raise ValueError(f"Event {event['id']} caused_by references missing or future event: {cause_id}")
            if event_dates[cause_id] > event_date:
                raise ValueError(f"Event {event['id']} caused_by {cause_id} occurs after event date")
    return True


def generate_household_events(profile, num_events, num_days=60, start_date=None, use_llm=True, on_event_generated=None):
    if start_date is None:
        start_date = get_random_date()
    end_date = start_date + timedelta(days=num_days)

    if not use_llm:
        logging.info("LLM disabled; generating household events with template fallback")
        return generate_template_household_events(profile, num_events, num_days, start_date)

    from global_methods import run_chatgpt

    graph = []
    scenario_sequence = build_event_scenario_sequence(profile, num_events)
    applicable_scenarios = [scenario for scenario in WEEKEND_SCENARIOS if scenario_is_applicable(profile, scenario)]
    profile["events_start_date"] = dateObj2Str(start_date)
    profile["events_end_date"] = dateObj2Str(end_date)
    profile["event_generation_mode"] = "planned_single_event_llm"
    profile["event_scenario_catalog"] = {
        scenario: {
            "label": SCENARIO_LABELS[scenario],
            "memory_dimensions": SCENARIO_DIMENSIONS[scenario],
            "guidance": SCENARIO_GUIDANCE[scenario],
            "applicable": scenario in applicable_scenarios,
        }
        for scenario in WEEKEND_SCENARIOS
    }
    profile["graph"] = []

    for idx, scenario_type in enumerate(scenario_sequence, start=1):
        event_plan = build_event_plan(profile, idx, scenario_type, start_date, num_days, num_events, graph)
        prompt_context = build_event_prompt_context(profile, event_plan, graph)
        prompt = HOUSEHOLD_SINGLE_EVENT_PROMPT.format(
            context=format_event_context_text(prompt_context),
            previous_events=compact_previous_events_for_prompt(prompt_context["previous_events"]),
            event_plan=json.dumps(compact_event_plan_for_prompt(event_plan), ensure_ascii=False, separators=(",", ":")),
        )
        logging.info(
            "Calling LLM for household event %s/%s: family_id=%s, scenario=%s, date=%s, caused_by=%s, prompt_chars=%s",
            idx,
            num_events,
            profile.get("family", {}).get("family_id"),
            scenario_type,
            event_plan["date"],
            event_plan["caused_by"],
            len(prompt),
        )
        try:
            response = run_chatgpt(prompt, num_gen=1, num_tokens_request=700, temperature=0.9)
            logging.info("LLM household event %s response received: chars=%s", event_plan["id"], len(response or ""))
            raw_event = parse_json_object(response)
            event = normalize_single_event(raw_event, event_plan, profile)
        except Exception as exc:
            logging.warning("LLM household event %s generation failed, using event fallback: %s", event_plan["id"], exc)
            event = normalize_single_event({}, event_plan, profile)

        graph.append(event)
        profile["graph"] = list(graph)
        logging.info(
            "Generated event %s [%s] date=%s participants=%s caused_by=%s",
            event["id"],
            event["scenario_type"],
            event["date"],
            event["participants"],
            event["caused_by"],
        )
        if on_event_generated:
            on_event_generated(profile, event)

    profile["events_start_date"] = dateObj2Str(start_date)
    profile["graph"] = graph
    profile["events_end_date"] = dateObj2Str(end_date)
    generated_scenarios = [event["scenario_type"] for event in graph]
    profile["event_scenario_coverage"] = {
        "generated": generated_scenarios,
        "covered": sorted(set(generated_scenarios)),
        "applicable": applicable_scenarios,
        "missing_applicable": [scenario for scenario in applicable_scenarios if scenario not in generated_scenarios],
    }
    validate_event_timeline(graph, profile)
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
