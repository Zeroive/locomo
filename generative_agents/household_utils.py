"""
Household profile construction utilities.

The household generator keeps structural consistency in code first, then leaves
the generated natural language fields easy to enrich with an LLM later.
"""

import json
import logging
import os
import random
import re
from collections import defaultdict


HOUSEHOLD_TYPES = [
    "couple_only",
    "nuclear_family",
    "three_generation_family",
    "single_parent_family",
    "shared_living_family",
    "pet_family",
    "elderly_care_family",
    "child_centered_family",
]


MEMBER_PERSONA_ENRICH_PROMPT = """
你是家庭多用户 AI 助手测评数据集的人物画像生成器。

请只为一个家庭成员生成 persona_summary，不要生成其他成员。

要求：
- 输出必须是 JSON 对象，不要输出 markdown。
- 只包含字段 "persona_summary"。
- persona_summary 使用中文，120-180字。
- 必须体现姓名、年龄、家庭角色、个人特征、周末休闲/照护偏好。
- 要把 member.traits 和 msc_prompt 映射到家庭责任、关系和后续可对话主题。
- 不要改变 person_id、年龄、角色，不要引入不存在的家庭成员。

家庭背景摘要：
{family_context}

当前成员：
{member}
""".strip()


HOUSEHOLD_BACKGROUND_PROMPT = """
你是家庭多用户 AI 助手测评数据集的家庭背景生成器。

请根据成员、关系、宠物和责任分工，生成家庭共享背景和周末上下文。

要求：
- 输出必须是 JSON 对象，不要输出 markdown。
- 只包含字段 "shared_background" 和 "weekend_context"。
- shared_background 80-140字，描述家庭结构、主要关系和共同生活背景。
- weekend_context 80-140字，描述周末/休闲/照护安排的总体特点。
- 不要引入不存在的新成员。
- 宠物只能作为照护对象，不是用户。

家庭信息：
{household}
""".strip()


RESPONSIBILITY_ENRICH_PROMPT = """
你是家庭多用户 AI 助手测评数据集的家庭责任分工生成器。

请为指定家庭成员生成一条周末/休闲/照护相关责任。

要求：
- 输出必须是 JSON 对象，不要输出 markdown。
- 只包含字段 "responsibility"。
- responsibility 使用中文，20-45字。
- 结合成员角色、个人特征、宠物或孩子/老人照护需求。
- 不要改变结构字段，不要引入不存在的新成员。

家庭背景：
{family_context}

成员：
{member}

已有责任：
{current_responsibility}
""".strip()


ROLE_AGE_RANGES = {
    "grandfather": (66, 78),
    "grandmother": (63, 76),
    "father": (32, 48),
    "mother": (30, 46),
    "single_parent": (31, 48),
    "spouse": (28, 48),
    "adult_relative": (25, 55),
    "adult_child": (22, 35),
    "child": (6, 11),
    "teenager": (12, 17),
}


ROLE_DISPLAY = {
    "grandfather": "祖父",
    "grandmother": "祖母",
    "father": "父亲",
    "mother": "母亲",
    "single_parent": "单亲家长",
    "spouse": "伴侣",
    "adult_relative": "同住亲属",
    "adult_child": "成年子女",
    "child": "孩子",
    "teenager": "青少年子女",
}


FAMILY_TEMPLATES = {
    "couple_only": ["spouse", "spouse"],
    "nuclear_family": ["father", "mother", "child"],
    "three_generation_family": ["grandfather", "grandmother", "father", "mother", "child"],
    "single_parent_family": ["single_parent", "child"],
    "shared_living_family": ["father", "mother", "adult_relative"],
    "pet_family": ["father", "mother"],
    "elderly_care_family": ["grandfather", "father", "mother"],
    "child_centered_family": ["father", "mother", "child", "teenager"],
}


CHINESE_NAMES = {
    "male": ["王小明", "李明", "张强", "陈浩", "赵磊", "刘建国", "周晨", "孙伟"],
    "female": ["张小丽", "王丽", "李娜", "陈芳", "赵敏", "刘桂英", "周妍", "孙慧"],
    "child_male": ["王小宝", "李乐乐", "张天天", "陈一诺"],
    "child_female": ["王可可", "李小雨", "张朵朵", "陈安安"],
}


PET_NAMES = ["豆豆", "团团", "米粒", "花花", "雪球"]


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(data, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def strip_generation_prompts(value):
    if isinstance(value, dict):
        return {
            key: strip_generation_prompts(item)
            for key, item in value.items()
            if key not in {
                "generation_prompts",
                "generation_prompt",
                "profile_generation_prompt",
                "event_generation_prompt",
                "fact_generation_prompt",
                "qa_generation_prompt",
            }
        }
    if isinstance(value, list):
        return [strip_generation_prompts(item) for item in value]
    return value


def load_persona_source(path):
    data = load_json(path)
    if isinstance(data, dict) and "train" in data:
        return [item.get("Speaker", []) for item in data["train"] if item.get("Speaker")]
    if isinstance(data, list):
        return data
    return []


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


def create_assistant():
    return {
        "name": "AI助手",
        "persona_summary": (
            "你是一个友好、专业的家庭智能助手，负责帮助多位家庭成员管理周末安排、"
            "休闲活动、家庭聚餐、老人照护、儿童活动和宠物照护。你能记住不同成员的"
            "偏好与责任分工，并在对话中根据当前时间、近期事件和家庭关系给出简洁建议。"
        ),
        "msc_prompt": [
            "I am a smart home AI assistant.",
            "I remember household members, roles, routines, and weekend plans.",
            "I help coordinate family activities and care responsibilities.",
        ],
    }


def infer_traits(msc_prompt):
    text = " ".join(msc_prompt).lower()
    daily_routines = []
    preferences = []
    possible_family_roles = []

    if any(k in text for k in ["dog", "cat", "pet", "pup"]):
        daily_routines.append("usually takes care of pets")
        preferences.append("likes animals")
    if any(k in text for k in ["garden", "plant", "flower"]):
        preferences.append("likes gardening")
    if any(k in text for k in ["cook", "food", "bake", "restaurant", "italian", "vegan"]):
        preferences.append("cares about meals")
    if any(k in text for k in ["hike", "outdoor", "basketball", "walk", "concert"]):
        preferences.append("likes outdoor or leisure activities")
    if any(k in text for k in ["school", "grades", "high school", "college"]):
        possible_family_roles.append("child")
    if any(k in text for k in ["married", "wife", "husband", "daughter", "son"]):
        possible_family_roles.append("parent")
    if any(k in text for k in ["grandmother", "grandfather", "retired"]):
        possible_family_roles.append("grandparent")

    return {
        "daily_routines": daily_routines,
        "preferences": preferences,
        "possible_family_roles": possible_family_roles,
    }


def life_stage_for_age(age):
    if age < 12:
        return "child"
    if age < 18:
        return "teenager"
    if age >= 60:
        return "elderly"
    return "adult"


def gender_for_role(role):
    if role in {"father", "grandfather"}:
        return "male"
    if role in {"mother", "grandmother"}:
        return "female"
    return random.choice(["male", "female"])


def name_for_role(role, gender, used_names):
    if role in {"child", "teenager"}:
        pool = CHINESE_NAMES["child_male" if gender == "male" else "child_female"]
    else:
        pool = CHINESE_NAMES[gender]
    candidates = [name for name in pool if name not in used_names]
    name = random.choice(candidates or pool)
    used_names.add(name)
    return name


def build_member(idx, role, persona_prompts, used_names):
    min_age, max_age = ROLE_AGE_RANGES[role]
    age = random.randint(min_age, max_age)
    gender = gender_for_role(role)
    name = name_for_role(role, gender, used_names)
    msc_prompt = random.choice(persona_prompts) if persona_prompts else []
    traits = infer_traits(msc_prompt)

    if role in {"grandfather", "grandmother"}:
        traits["possible_family_roles"].append("grandparent")
    elif role in {"father", "mother", "single_parent"}:
        traits["possible_family_roles"].append("parent")
    elif role in {"child", "teenager"}:
        traits["possible_family_roles"].append("child")

    persona_summary = (
        f"{name}今年{age}岁，是家庭中的{ROLE_DISPLAY[role]}。"
        f"{name}的日常特点包括：{'; '.join(msc_prompt[:3]) if msc_prompt else '重视家庭生活'}。"
        f"在周末安排中，{name}常参与家庭沟通、休闲计划或照护分工。"
    )
    return {
        "person_id": f"person_{idx:03d}",
        "name": name,
        "gender": "男" if gender == "male" else "女",
        "age": age,
        "age_range": f"{max(0, age - 2)}-{age + 2}",
        "life_stage": life_stage_for_age(age),
        "family_role": role,
        "family_role_label": ROLE_DISPLAY[role],
        "person_type": "family_member",
        "persona_summary": persona_summary,
        "msc_prompt": msc_prompt,
        "traits": traits,
        "can_chat_with_ai": True,
    }


def relation(source, target, rel_type):
    return {"from": source, "to": target, "type": rel_type}


def add_bidirectional(relations, a, b, rel_type, reverse_type=None):
    relations.append(relation(a, b, rel_type))
    relations.append(relation(b, a, reverse_type or rel_type))


def build_relations(members):
    by_role = defaultdict(list)
    for member in members:
        by_role[member["family_role"]].append(member)

    relations = []
    parents = by_role["father"] + by_role["mother"] + by_role["single_parent"]
    children = by_role["child"] + by_role["teenager"] + by_role["adult_child"]
    grandparents = by_role["grandfather"] + by_role["grandmother"]

    if by_role["father"] and by_role["mother"]:
        add_bidirectional(relations, by_role["father"][0]["person_id"], by_role["mother"][0]["person_id"], "SPOUSE_OF")
    if len(by_role["spouse"]) >= 2:
        add_bidirectional(relations, by_role["spouse"][0]["person_id"], by_role["spouse"][1]["person_id"], "SPOUSE_OF")
    if by_role["grandfather"] and by_role["grandmother"]:
        add_bidirectional(relations, by_role["grandfather"][0]["person_id"], by_role["grandmother"][0]["person_id"], "SPOUSE_OF")

    for parent in parents:
        for child in children:
            add_bidirectional(relations, parent["person_id"], child["person_id"], "PARENT_OF", "CHILD_OF")

    grandparent_child = (by_role["father"] or by_role["mother"] or by_role["single_parent"] or by_role["adult_child"])
    for grandparent in grandparents:
        for parent in grandparent_child[:1]:
            add_bidirectional(relations, grandparent["person_id"], parent["person_id"], "PARENT_OF", "CHILD_OF")
        for child in children:
            add_bidirectional(relations, grandparent["person_id"], child["person_id"], "GRANDPARENT_OF", "GRANDCHILD_OF")

    relatives = by_role["adult_relative"]
    anchor = (parents or grandparents or children)[0] if (parents or grandparents or children) else None
    for relative_member in relatives:
        if anchor:
            add_bidirectional(relations, relative_member["person_id"], anchor["person_id"], "RELATIVE_OF")

    return dedupe_relations(relations)


def dedupe_relations(relations):
    seen = set()
    unique = []
    for rel in relations:
        key = (rel["from"], rel["to"], rel["type"])
        if key not in seen:
            seen.add(key)
            unique.append(rel)
    return unique


def build_pets(household_type, with_pet, members):
    if not with_pet and household_type != "pet_family":
        return []
    caretaker = choose_pet_caretaker(members)
    return [{
        "pet_id": "pet_001",
        "name": random.choice(PET_NAMES),
        "species": random.choice(["dog", "cat"]),
        "care_routine": f"{caretaker['name']}主要负责周末喂养和陪伴宠物。",
        "caretaker_id": caretaker["person_id"],
        "is_user": False,
    }]


def choose_pet_caretaker(members):
    candidates = [
        m for m in members
        if "usually takes care of pets" in m.get("traits", {}).get("daily_routines", [])
        and m.get("life_stage") in {"adult", "elderly"}
    ]
    if candidates:
        return random.choice(candidates)
    adults = [m for m in members if m.get("life_stage") in {"adult", "elderly"}]
    return random.choice(adults or members)


def build_role_responsibilities(members, pets):
    responsibilities = []
    for member in members:
        role = member["family_role"]
        if role in {"father", "mother", "single_parent"}:
            text = "协调周末家庭计划和孩子活动"
        elif role in {"grandfather", "grandmother"}:
            text = "安排散步、买菜或社区活动"
        elif role in {"child", "teenager"}:
            text = "完成作业、兴趣班和家庭娱乐安排"
        else:
            text = "协助家庭聚餐或临时安排"
        responsibilities.append({"person_id": member["person_id"], "responsibility": text})

    for pet in pets:
        responsibilities.append({
            "person_id": pet["caretaker_id"],
            "responsibility": f"照看宠物{pet['name']}的周末喂养和活动",
        })
    return responsibilities


def validate_household(profile):
    members = profile.get("members", [])
    member_ids = {m["person_id"] for m in members}
    errors = []

    connected = set()
    relation_keys = {(r["from"], r["to"], r["type"]) for r in profile.get("relations", [])}
    reverse_map = {
        "SPOUSE_OF": "SPOUSE_OF",
        "PARENT_OF": "CHILD_OF",
        "CHILD_OF": "PARENT_OF",
        "GRANDPARENT_OF": "GRANDCHILD_OF",
        "GRANDCHILD_OF": "GRANDPARENT_OF",
        "RELATIVE_OF": "RELATIVE_OF",
    }

    for rel in profile.get("relations", []):
        if rel["from"] not in member_ids or rel["to"] not in member_ids:
            errors.append(f"Relation references unknown member: {rel}")
        connected.add(rel["from"])
        connected.add(rel["to"])
        expected_reverse = reverse_map.get(rel["type"])
        if expected_reverse and (rel["to"], rel["from"], expected_reverse) not in relation_keys:
            errors.append(f"Missing reverse relation for {rel}")

    isolated = member_ids - connected
    if isolated:
        errors.append(f"Isolated household members: {sorted(isolated)}")

    for member in members:
        if member["life_stage"] in {"child", "teenager"} and member["family_role"] in {"father", "mother", "single_parent"}:
            errors.append(f"Child or teenager cannot be parent: {member['person_id']}")

    pet_ids = {pet["pet_id"] for pet in profile.get("pets", [])}
    for session in profile.get("sessions", []):
        current_user_id = session.get("current_user_id")
        if current_user_id in pet_ids:
            errors.append(f"Pet used as current_user: {current_user_id}")
        if current_user_id and current_user_id not in member_ids:
            errors.append(f"Unknown current_user: {current_user_id}")

    if errors:
        raise ValueError("; ".join(errors))
    return True


def build_family_context(profile):
    compact = {
        "family": profile.get("family", {}),
        "members": [
            {
                "person_id": member["person_id"],
                "name": member["name"],
                "age": member["age"],
                "gender": member["gender"],
                "family_role": member["family_role"],
                "family_role_label": member["family_role_label"],
                "life_stage": member["life_stage"],
            }
            for member in profile.get("members", [])
        ],
        "relations": profile.get("relations", []),
        "pets": profile.get("pets", []),
    }
    return json.dumps(compact, ensure_ascii=False, indent=2)


def enrich_member_persona_with_llm(profile, member):
    from global_methods import run_chatgpt

    prompt = MEMBER_PERSONA_ENRICH_PROMPT.format(
        family_context=build_family_context(profile),
        member=json.dumps(member, ensure_ascii=False, indent=2),
    )
    logging.info(
        "Calling LLM for member persona: person_id=%s, name=%s, role=%s",
        member.get("person_id"),
        member.get("name"),
        member.get("family_role"),
    )
    response = run_chatgpt(prompt, num_gen=1, num_tokens_request=700, temperature=0.8)
    logging.info("LLM member persona response received for %s: chars=%s", member.get("person_id"), len(response or ""))
    data = parse_json_object(response)
    persona_summary = data.get("persona_summary")
    if not persona_summary:
        raise ValueError("Missing persona_summary")
    member["persona_summary"] = persona_summary
    return member


def enrich_household_background_with_llm(profile):
    from global_methods import run_chatgpt

    prompt = HOUSEHOLD_BACKGROUND_PROMPT.format(
        household=json.dumps({
            "family": profile.get("family", {}),
            "members": profile.get("members", []),
            "relations": profile.get("relations", []),
            "pets": profile.get("pets", []),
            "role_responsibilities": profile.get("role_responsibilities", []),
        }, ensure_ascii=False, indent=2)
    )
    logging.info("Calling LLM for household background: family_id=%s", profile.get("family", {}).get("family_id"))
    response = run_chatgpt(prompt, num_gen=1, num_tokens_request=900, temperature=0.7)
    logging.info("LLM household background response received: chars=%s", len(response or ""))
    data = parse_json_object(response)
    if data.get("shared_background"):
        profile["family"]["shared_background"] = data["shared_background"]
    if data.get("weekend_context"):
        profile["family"]["weekend_context"] = data["weekend_context"]
    return profile


def enrich_responsibility_with_llm(profile, responsibility):
    from global_methods import run_chatgpt

    member = next((m for m in profile.get("members", []) if m["person_id"] == responsibility.get("person_id")), None)
    if member is None:
        return responsibility
    prompt = RESPONSIBILITY_ENRICH_PROMPT.format(
        family_context=build_family_context(profile),
        member=json.dumps(member, ensure_ascii=False, indent=2),
        current_responsibility=responsibility.get("responsibility", ""),
    )
    logging.info("Calling LLM for responsibility: person_id=%s", member["person_id"])
    response = run_chatgpt(prompt, num_gen=1, num_tokens_request=300, temperature=0.6)
    logging.info("LLM responsibility response received for %s: chars=%s", member["person_id"], len(response or ""))
    data = parse_json_object(response)
    if data.get("responsibility"):
        responsibility["responsibility"] = data["responsibility"]
    return responsibility


def enrich_household_profile_with_llm(profile, on_profile_updated=None):
    for idx, member in enumerate(profile.get("members", [])):
        try:
            profile["members"][idx] = enrich_member_persona_with_llm(profile, member)
            validate_household(profile)
            logging.info("Member persona enriched and validated: %s", member["person_id"])
            if on_profile_updated:
                on_profile_updated(profile, f"member_persona:{member['person_id']}")
        except Exception as exc:
            logging.warning("LLM member persona enrichment failed for %s, keeping rule persona: %s", member.get("person_id"), exc)

    try:
        profile = enrich_household_background_with_llm(profile)
        validate_household(profile)
        logging.info("Household background enriched and validated")
        if on_profile_updated:
            on_profile_updated(profile, "household_background")
    except Exception as exc:
        logging.warning("LLM household background enrichment failed, keeping rule background: %s", exc)

    for idx, responsibility in enumerate(profile.get("role_responsibilities", [])):
        try:
            profile["role_responsibilities"][idx] = enrich_responsibility_with_llm(profile, responsibility)
            validate_household(profile)
            logging.info("Responsibility enriched and validated: %s", responsibility.get("person_id"))
            if on_profile_updated:
                on_profile_updated(profile, f"responsibility:{responsibility.get('person_id')}")
        except Exception as exc:
            logging.warning("LLM responsibility enrichment failed for %s, keeping rule responsibility: %s", responsibility.get("person_id"), exc)

    return profile


def sample_household_profile(household_type, persona_source, family_id="family_001", with_pet=False, use_llm=True, on_profile_updated=None):
    if household_type not in HOUSEHOLD_TYPES:
        raise ValueError(f"Unsupported household_type: {household_type}")

    roles = list(FAMILY_TEMPLATES[household_type])
    persona_prompts = load_persona_source(persona_source)
    used_names = set()
    members = [build_member(i + 1, role, persona_prompts, used_names) for i, role in enumerate(roles)]
    relations = build_relations(members)
    pets = build_pets(household_type, with_pet, members)
    responsibilities = build_role_responsibilities(members, pets)

    family_surname = members[0]["name"][0] if members else "家庭"
    profile = {
        "family": {
            "family_id": family_id,
            "family_name": f"{family_surname}家",
            "household_type": household_type,
            "shared_background": build_shared_background(members, pets),
            "weekend_context": "这个家庭的周末重点围绕休息、家庭聚餐、孩子活动、老人社区活动和宠物照护展开。",
        },
        "members": members,
        "relations": relations,
        "pets": pets,
        "role_responsibilities": responsibilities,
        "events_start_date": "",
        "graph": [],
        "sessions": [],
    }
    validate_household(profile)
    if use_llm:
        try:
            profile = enrich_household_profile_with_llm(profile, on_profile_updated=on_profile_updated)
        except Exception as exc:
            logging.warning("LLM household profile enrichment failed, using rule profile: %s", exc)
    else:
        logging.info("LLM disabled; using rule-based household profile")
    return profile


def build_shared_background(members, pets):
    role_text = "、".join([f"{m['name']}是{m['family_role_label']}" for m in members])
    pet_text = ""
    if pets:
        pet = pets[0]
        caretaker = next((m for m in members if m["person_id"] == pet["caretaker_id"]), None)
        pet_text = f" 家里养了一只{pet['species']}，名叫{pet['name']}，主要由{caretaker['name'] if caretaker else '家人'}照顾。"
    return f"这是一个多成员家庭，{role_text}。家庭成员会在周末共同协调休闲、聚餐和照护安排。{pet_text}".strip()


def summarize_relations(profile):
    members = {m["person_id"]: m["name"] for m in profile.get("members", [])}
    lines = []
    for rel in profile.get("relations", []):
        if rel["type"] in {"CHILD_OF", "GRANDCHILD_OF"}:
            continue
        lines.append(f"{members.get(rel['from'], rel['from'])} -> {rel['type']} -> {members.get(rel['to'], rel['to'])}")
    return "\n".join(lines)


def get_member(profile, person_id):
    return next(member for member in profile["members"] if member["person_id"] == person_id)
