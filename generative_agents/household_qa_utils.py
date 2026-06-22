"""
QA generation for household multi-user conversations.
"""

import json
import logging
import os
import re

from generative_agents.household_utils import get_member, save_json


HOUSEHOLD_QA_PROMPT = """
你是长期家庭对话记忆 QA 数据集构造助手。

请根据 household_profile、家庭事件、session facts 和原始对话 turns 生成测评 QA。

要求：
- 输出必须是 JSON 数组，不要输出 markdown。
- 每条 QA 必须包含：
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
- 至少覆盖 single-hop、cross-member、adversarial；如果存在计划冲突或变更，必须生成 temporal 或 multi-hop。
- 如果存在宠物照护事件，必须生成 pet-related。

household_profile:
{profile}

sessions/facts/events:
{context}
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


def generate_household_qa_pairs(profile, out_dir, use_llm=True):
    try:
        if not use_llm:
            raise ValueError("LLM disabled")
        from global_methods import run_chatgpt

        logging.info(
            "Calling LLM for household QA generation: sessions=%s, events=%s",
            len(profile.get("sessions", [])),
            len(profile.get("graph", [])),
        )
        prompt = HOUSEHOLD_QA_PROMPT.format(
            profile=json.dumps({
                "family": profile.get("family", {}),
                "members": profile.get("members", []),
                "relations": profile.get("relations", []),
                "pets": profile.get("pets", []),
                "role_responsibilities": profile.get("role_responsibilities", []),
            }, ensure_ascii=False, indent=2),
            context=json.dumps({
                "graph": profile.get("graph", []),
                "sessions": profile.get("sessions", []),
                "session_facts": {
                    key: value for key, value in profile.items()
                    if key.startswith("session_") and key.endswith("_facts")
                },
            }, ensure_ascii=False, indent=2),
        )
        response = run_chatgpt(prompt, num_gen=1, num_tokens_request=4000, temperature=0.7)
        logging.info("LLM QA response received: chars=%s", len(response or ""))
        generated_items = parse_json_array(response)
        qa_items = []
        for idx, item in enumerate(generated_items, start=1):
            if not isinstance(item, dict):
                continue
            category = item.get("category", "single-hop")
            qa_items.append({
                "qa_id": f"QA_{idx}",
                "session_id": item.get("session_id"),
                "time": item.get("time", ""),
                "entity_id": item.get("entity_id", ""),
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
            })
        if qa_items:
            logging.info("LLM QA parsed: %s items", len(qa_items))
            output = {
                "description": "家庭多用户与AI助手对话测评数据",
                "family": profile.get("family", {}),
                "members": profile.get("members", []),
                "relations": profile.get("relations", []),
                "QA": qa_items,
                "qa_generation_prompt": prompt,
            }
            save_json(output, os.path.join(out_dir, "qa_pairs.json"))
            return output
        raise ValueError("No valid generated QA items")
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
