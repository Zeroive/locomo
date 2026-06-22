"""
QA generation for household multi-user conversations.
"""

import json
import logging
import os
import re

from generative_agents.household_utils import get_member, save_json, strip_generation_prompts


HOUSEHOLD_QA_PROMPT = """
你是长期家庭对话记忆 QA 数据集构造助手。

请根据给定证据材料，只生成 1 条测评 QA。

要求：
- 输出必须是 JSON 对象，不要输出 markdown。
- QA 必须包含：
  - "category": single-hop | multi-hop | temporal | cross-member | pet-related | adversarial
  - "question"
  - "answer"
  - "entity_id"
  - "evidence_turn_ids"
  - "source_fact_ids"
  - "difficulty": easy | medium | hard
  - "requires_temporal_reasoning": boolean
  - "requires_tool_use": boolean
  - "requires_cross_member_reference": boolean
- 问题必须只能根据给定证据回答。
- adversarial 的答案必须是“无法从对话中确定”，且 evidence_turn_ids 和 source_fact_ids 为空数组。
- 不要使用今天、昨天、明天等相对时间，要使用具体日期或会话时间。
- 必须严格生成 qa_plan 指定的 category。
- 不要生成重复问题。

qa_plan:
{qa_plan}

家庭与成员概况:
{profile}

证据材料:
{context}
""".strip()


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


def first_turn_id(session):
    turns = session.get("turns", [])
    return [turns[0]["dia_id"]] if turns else []


def event_for_session(profile, session):
    event_ids = session.get("related_event_ids", [])
    events = [event for event in profile.get("graph", []) if event["id"] in event_ids]
    return events[0] if events else None


def participants_answer(profile, event):
    names = [
        get_member(profile, person_id)["name"]
        for person_id in event.get("participants", [])
        if any(member["person_id"] == person_id for member in profile["members"])
    ]
    return "、".join(names) if names else "无法从对话中确定"


def make_qa(qa_id, session, entity_id, category, question, answer, evidence_turn_ids, source_fact_ids, **flags):
    return {
        "qa_id": f"QA_{qa_id}",
        "session_id": session.get("session_id"),
        "time": session.get("date_time", ""),
        "entity_id": entity_id,
        "category": category,
        "QA_details": {
            "user": question,
            "assistant": answer,
        },
        "evidence_turn_ids": evidence_turn_ids,
        "source_fact_ids": source_fact_ids,
        "difficulty": flags.pop("difficulty", "medium"),
        "requires_temporal_reasoning": flags.pop("requires_temporal_reasoning", category == "temporal"),
        "requires_tool_use": flags.pop("requires_tool_use", False),
        "requires_cross_member_reference": flags.pop("requires_cross_member_reference", category in {"cross-member", "multi-hop"}),
        **flags,
    }


def format_family_for_qa(profile):
    profile = strip_generation_prompts(profile)
    lines = [
        f"家庭：{profile.get('family', {}).get('family_name')}，类型={profile.get('family', {}).get('household_type')}。",
    ]
    if profile.get("family", {}).get("weekend_context"):
        lines.append(f"周末背景：{profile['family']['weekend_context']}")
    member_lines = [
        f"{member['person_id']}={member['name']}({member.get('age')}岁,{member.get('family_role_label')},{member.get('life_stage')})"
        for member in profile.get("members", [])
    ]
    if member_lines:
        lines.append("成员：" + "；".join(member_lines))
    if profile.get("pets"):
        pet_lines = [
            f"{pet.get('pet_id')}={pet.get('name')}({pet.get('species')}),照护人={pet.get('caretaker_id')}"
            for pet in profile.get("pets", [])
        ]
        lines.append("宠物：" + "；".join(pet_lines))
    return "\n".join(lines)


def format_evidence_for_qa(profile):
    profile = strip_generation_prompts(profile)
    lines = []
    if profile.get("graph"):
        lines.append("事件：")
        for event in profile.get("graph", []):
            lines.append(
                f"- {event['id']} | {event['date']} | {event['scenario_type']} | "
                f"参与={','.join(event.get('participants', []))} | {event['sub-event']}"
            )
    for session in profile.get("sessions", []):
        sess_id = session.get("session_id")
        lines.append(f"\n会话 S{sess_id} | time={session.get('date_time')} | current_user={session.get('current_user_id')} | events={','.join(session.get('related_event_ids', []))}")
        for turn in session.get("turns", []):
            text = turn.get("clean_text") or turn.get("text", "")
            lines.append(f"[{turn.get('dia_id')}] {turn.get('speaker')}: {text}")
        facts = profile.get(f"session_{sess_id}_facts", {})
        if facts:
            lines.append("Facts:")
            for speaker, speaker_facts in facts.items():
                for fact in speaker_facts:
                    if isinstance(fact, (list, tuple)) and len(fact) >= 2:
                        lines.append(f"- {speaker}: {fact[0]} (source={fact[1]})")
                    else:
                        lines.append(f"- {speaker}: {fact}")
    return "\n".join(lines)


def build_qa_plans(profile):
    plans = []
    for session in profile.get("sessions", []):
        event = event_for_session(profile, session)
        current_user_id = session.get("current_user_id")
        base = {
            "session_id": session.get("session_id"),
            "time": session.get("date_time", ""),
            "current_user_id": current_user_id,
            "event_id": event.get("id") if event else "",
        }
        if event:
            plans.append({**base, "category": "single-hop", "intent": "询问当前事件中明确提到的一项具体安排。"})
            plans.append({**base, "category": "cross-member", "intent": "询问当前安排涉及哪些成员或谁需要被提醒。"})
            if event.get("scenario_type") in {"changed_weekend_plan", "conflicting_plans"}:
                plans.append({**base, "category": "temporal", "intent": "询问计划变更、冲突或后续确认事项。"})
            if event.get("scenario_type") == "pet_weekend_care":
                plans.append({**base, "category": "pet-related", "intent": "询问宠物照护对象或照护人。"})
        plans.append({**base, "category": "adversarial", "intent": "询问证据中没有明确说明的信息，答案必须是无法从对话中确定。"})
    return plans


def format_single_qa_evidence(profile, plan):
    event = next((event for event in profile.get("graph", []) if event.get("id") == plan.get("event_id")), None)
    session = next((item for item in profile.get("sessions", []) if item.get("session_id") == plan.get("session_id")), None)
    lines = []
    if event:
        lines.append(
            f"事件 {event['id']} | {event['date']} | {event['scenario_type']} | "
            f"参与={','.join(event.get('participants', []))} | {event['sub-event']}"
        )
    if session:
        lines.append(f"会话 S{session.get('session_id')} | time={session.get('date_time')} | current_user={session.get('current_user_id')}")
        for turn in session.get("turns", []):
            text = turn.get("clean_text") or turn.get("text", "")
            lines.append(f"[{turn.get('dia_id')}] {turn.get('speaker')}: {text}")
        facts = profile.get(f"session_{session.get('session_id')}_facts", {})
        if facts:
            lines.append("Facts:")
            for speaker, speaker_facts in facts.items():
                for fact in speaker_facts:
                    if isinstance(fact, (list, tuple)) and len(fact) >= 2:
                        lines.append(f"- {speaker}: {fact[0]} (source={fact[1]})")
                    else:
                        lines.append(f"- {speaker}: {fact}")
    return "\n".join(lines)


def normalize_generated_qa(item, qa_id, plan):
    category = item.get("category") or plan["category"]
    return {
        "qa_id": f"QA_{qa_id}",
        "session_id": item.get("session_id", plan.get("session_id")),
        "time": item.get("time", plan.get("time", "")),
        "entity_id": item.get("entity_id", plan.get("current_user_id", "")),
        "category": category,
        "QA_details": {
            "user": item.get("question", ""),
            "assistant": item.get("answer", ""),
        },
        "evidence_turn_ids": item.get("evidence_turn_ids", []),
        "source_fact_ids": item.get("source_fact_ids", []),
        "difficulty": item.get("difficulty", "medium"),
        "requires_temporal_reasoning": item.get("requires_temporal_reasoning", category == "temporal"),
        "requires_tool_use": item.get("requires_tool_use", False),
        "requires_cross_member_reference": item.get("requires_cross_member_reference", category in {"cross-member", "multi-hop"}),
    }


def generate_household_qa_pairs(profile, out_dir, use_llm=True):
    try:
        if not use_llm:
            raise ValueError("LLM disabled")
        from global_methods import run_chatgpt

        output = {
            "description": "家庭多用户与AI助手对话测评数据",
            "family": profile.get("family", {}),
            "members": profile.get("members", []),
            "relations": profile.get("relations", []),
            "QA": [],
        }
        qa_plans = build_qa_plans(profile)
        logging.info(
            "Calling LLM for household QA generation: sessions=%s, events=%s, qa_plans=%s",
            len(profile.get("sessions", [])),
            len(profile.get("graph", [])),
            len(qa_plans),
        )
        for idx, plan in enumerate(qa_plans, start=1):
            prompt = HOUSEHOLD_QA_PROMPT.format(
                qa_plan=json.dumps(plan, ensure_ascii=False, separators=(",", ":")),
                profile=format_family_for_qa(profile),
                context=format_single_qa_evidence(profile, plan),
            )
            logging.info("Calling LLM for QA %s/%s: category=%s, session=%s, prompt_chars=%s", idx, len(qa_plans), plan["category"], plan.get("session_id"), len(prompt))
            response = run_chatgpt(prompt, num_gen=1, num_tokens_request=900, temperature=0.7)
            logging.info("LLM QA %s response received: chars=%s", idx, len(response or ""))
            item = parse_json_object(response)
            qa = normalize_generated_qa(item, idx, plan)
            output["QA"].append(qa)
            save_json(output, os.path.join(out_dir, "qa_pairs.json"))
            logging.info("Autosaved QA %s/%s: %s", idx, len(qa_plans), qa["category"])
        return output
    except Exception as exc:
        logging.warning("LLM household QA generation failed, using fallback QA: %s", exc)

    qa_items = []
    qa_id = 1
    sessions = profile.get("sessions", [])

    for session in sessions:
        event = event_for_session(profile, session)
        current_user = get_member(profile, session["current_user_id"])
        evidence = first_turn_id(session)

        if event:
            qa_items.append(make_qa(
                qa_id,
                session,
                current_user["person_id"],
                "single-hop",
                f"{current_user['name']}这次和AI助手主要记录了什么周末事项？",
                event["sub-event"],
                evidence,
                [event["id"]],
                difficulty="easy",
            ))
            qa_id += 1

            qa_items.append(make_qa(
                qa_id,
                session,
                current_user["person_id"],
                "cross-member",
                "这个安排涉及哪些家庭成员？",
                participants_answer(profile, event),
                evidence,
                [event["id"]],
            ))
            qa_id += 1

            if event["scenario_type"] in {"changed_weekend_plan", "conflicting_plans"}:
                qa_items.append(make_qa(
                    qa_id,
                    session,
                    current_user["person_id"],
                    "temporal",
                    "这次对话中有没有需要后续重新确认或提醒的安排？",
                    "有，需要按最新周末安排再次提醒或确认。",
                    [turn["dia_id"] for turn in session.get("turns", [])[-2:]],
                    [event["id"]],
                    requires_temporal_reasoning=True,
                ))
                qa_id += 1

            if event["scenario_type"] == "pet_weekend_care":
                pet = profile.get("pets", [{}])[0]
                qa_items.append(make_qa(
                    qa_id,
                    session,
                    pet.get("pet_id", "pet_001"),
                    "pet-related",
                    "宠物照护事项由谁负责？",
                    participants_answer(profile, event),
                    evidence,
                    [event["id"]],
                    requires_cross_member_reference=True,
                ))
                qa_id += 1

        qa_items.append(make_qa(
            qa_id,
            session,
            current_user["person_id"],
            "adversarial",
            f"{current_user['name']}在这次对话中明确说了具体外出交通费用是多少吗？",
            "无法从对话中确定",
            [],
            [],
            difficulty="hard",
            requires_cross_member_reference=False,
        ))
        qa_id += 1

    output = {
        "description": "家庭多用户与AI助手对话测评数据",
        "family": profile.get("family", {}),
        "members": profile.get("members", []),
        "relations": profile.get("relations", []),
        "QA": qa_items,
    }
    save_json(output, os.path.join(out_dir, "qa_pairs.json"))
    return output
