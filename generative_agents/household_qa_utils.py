"""
QA generation for household multi-user conversations.
"""

import json
import logging
import os
import re

from generative_agents.household_utils import get_member, save_json, strip_generation_prompts


MEMORY_DIMENSION_PREFERENCES = {
    "single-hop": (),
    "multi-hop": ("cross_member_reference", "role_responsibility", "family_relationship"),
    "temporal": ("temporary_schedule", "weekend_plan", "dining_time", "work_schedule"),
    "open-domain": (),
    "adversarial": (),
}


HOUSEHOLD_QA_PROMPT = """
你是长期家庭对话记忆 QA 数据集构造助手。

请根据给定证据材料，只生成 1 条测评 QA。

要求：
- 输出必须是 JSON 对象，不要输出 markdown。
- QA 必须包含：
  - "category": single-hop | multi-hop | temporal | open-domain | adversarial
  - "memory_dimension": 从 qa_plan.allowed_memory_dimensions 中选择 1 个最相关的记忆维度
  - "question"
  - "answer"
  - "entity_id"
  - "evidence_turn_ids"
  - "source_fact_ids"
  - "difficulty": easy | medium | hard
  - "requires_temporal_reasoning": boolean
  - "requires_tool_use": boolean
  - "requires_cross_member_reference": boolean
- category 定义：
  - single-hop：单跳问题，答案由单个会话中的一处证据直接提供。
  - multi-hop：多跳推理问题，答案需要结合多个会话或多个事实后才能得到。
  - temporal：时间推理问题，答案需要比较时间先后、计划变更、之前/之后、最近/最终安排等。
  - open-domain：开放领域知识问题，需要结合对话证据和外部常识回答；不能脱离家庭对话凭空提问。
  - adversarial：对抗性问题，问题看似相关，但上下文不存在足够信息，必须不回答。
- 除 open-domain 可使用常识外，问题必须只能根据给定证据回答。
- open-domain 的 evidence_turn_ids 和 source_fact_ids 仍要标出触发该常识问题的对话证据。
- adversarial 的答案必须是“无法从对话中确定”，且 evidence_turn_ids 和 source_fact_ids 为空数组。
- 不要使用今天、昨天、明天等相对时间，要使用具体日期或会话时间。
- question 必须客观、自包含，不能依赖读者查看上一条问题或上下文标题才能理解。
- question 必须显式写出相关人物姓名；涉及会话或事件时必须写出具体时间、地点或生活场景，不要写会话编号、事件编号、turn 编号、fact 编号等内部编号。
- question 中不要使用指代词、模糊指代或内部编号指代，包括但不限于：他、她、他们、她们、这个、那个、这些、那些、这次、那次、上述、前面、当前用户、该成员、该事件、该会话、会话S1、事件E1。
- question 不要写成“谁”“哪位成员”这类需要从指代中反推对象的问题；如果询问成员列表，要明确限定日期、地点或生活场景和已知相关人物。
- 必须严格生成 qa_plan 指定的 category。
- 必须严格使用 qa_plan 指定或允许的 memory_dimension。
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


def get_member_safe(profile, person_id):
    if not person_id:
        return {}
    try:
        return get_member(profile, person_id)
    except StopIteration:
        return {"person_id": person_id, "name": person_id}


def participants_answer(profile, event):
    names = [
        get_member(profile, person_id)["name"]
        for person_id in event.get("participants", [])
        if any(member["person_id"] == person_id for member in profile["members"])
    ]
    return "、".join(names) if names else "无法从对话中确定"


def participant_names(profile, person_ids):
    names = []
    for person_id in person_ids or []:
        member = get_member_safe(profile, person_id)
        names.append(member.get("name") or person_id)
    return names


def select_memory_dimension(dimensions, category):
    dimensions = dimensions or []
    for preferred in MEMORY_DIMENSION_PREFERENCES.get(category, ()):
        if preferred in dimensions:
            return preferred
    return dimensions[0] if dimensions else ""


def pick_memory_dimension(plan=None, event=None, item=None):
    item = item or {}
    plan = plan or {}
    candidates = plan.get("allowed_memory_dimensions") or plan.get("memory_dimensions") or []
    if not candidates and event:
        candidates = event.get("memory_dimensions", [])
    value = item.get("memory_dimension") or plan.get("memory_dimension")
    if isinstance(value, list):
        value = value[0] if value else ""
    if value and (not candidates or value in candidates):
        return value
    return select_memory_dimension(candidates, plan.get("category", ""))


def make_qa(qa_id, session, entity_id, category, question, answer, evidence_turn_ids, source_fact_ids, **flags):
    memory_dimension = flags.pop("memory_dimension", "")
    return {
        "qa_id": f"QA_{qa_id}",
        "session_id": session.get("session_id"),
        "time": session.get("date_time", ""),
        "entity_id": entity_id,
        "category": category,
        "memory_dimension": memory_dimension,
        "QA_details": {
            "user": sanitize_question(question),
            "assistant": answer,
        },
        "evidence_turn_ids": evidence_turn_ids,
        "source_fact_ids": source_fact_ids,
        "difficulty": flags.pop("difficulty", "medium"),
        "requires_temporal_reasoning": flags.pop("requires_temporal_reasoning", category == "temporal"),
        "requires_tool_use": flags.pop("requires_tool_use", False),
        "requires_cross_member_reference": flags.pop("requires_cross_member_reference", category == "multi-hop"),
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
                f"参与={','.join(event.get('participants', []))} | "
                f"memory_dimensions={','.join(event.get('memory_dimensions', []))} | {event['sub-event']}"
            )
    for session in profile.get("flat_sessions", profile.get("sessions", [])):
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
    for session in profile.get("flat_sessions", profile.get("sessions", [])):
        event = event_for_session(profile, session)
        current_user_id = session.get("current_user_id")
        current_user = get_member_safe(profile, current_user_id)
        base = {
            "session_id": session.get("session_id"),
            "time": session.get("date_time", ""),
            "current_user_id": current_user_id,
            "current_user_name": current_user.get("name", ""),
            "event_id": event.get("id") if event else "",
            "event_date": event.get("date") if event else "",
            "event_scenario_type": event.get("scenario_type") if event else "",
            "event_participant_names": participant_names(profile, event.get("participants", [])) if event else [],
        }
        if event:
            dimensions = event.get("memory_dimensions", [])
            base = {**base, "allowed_memory_dimensions": dimensions}
            for category, intent in [
                ("single-hop", "单跳问题（单个会话提供答案）：询问当前事件中明确提到的一项具体安排。"),
                ("multi-hop", "多跳推理（需要结合多个会话提供答案）：比较或汇总同一家庭中不同会话提到的相关安排、成员责任或偏好。"),
                ("temporal", "时间推理（通过时间推理）：询问计划先后、变更、冲突、最终安排或后续确认事项。"),
                ("open-domain", "开放领域知识问题（外部知识如常识来回答）：围绕当前对话事项提出需要常识辅助回答的问题。"),
                ("adversarial", "对抗性问题（上下文不存在信息，不回答）：询问证据中没有明确说明的信息，答案必须是无法从对话中确定。"),
            ]:
                plans.append({
                    **base,
                    "category": category,
                    "memory_dimension": select_memory_dimension(dimensions, category),
                    "intent": intent,
                })
        else:
            plans.append({**base, "category": "adversarial", "intent": "对抗性问题（上下文不存在信息，不回答）：询问证据中没有明确说明的信息，答案必须是无法从对话中确定。"})
    return plans


def format_single_qa_evidence(profile, plan):
    event = next((event for event in profile.get("graph", []) if event.get("id") == plan.get("event_id")), None)
    session = next((item for item in profile.get("flat_sessions", profile.get("sessions", [])) if item.get("session_id") == plan.get("session_id")), None)
    lines = []
    if event:
        participant_text = "、".join(participant_names(profile, event.get("participants", [])))
        lines.append(
            f"事件证据 {event['id']} | 日期={event['date']} | 场景={event['scenario_type']} | "
            f"参与人={participant_text} | 参与人ID={','.join(event.get('participants', []))} | "
            f"memory_dimensions={','.join(event.get('memory_dimensions', []))} | {event['sub-event']}"
        )
    if session:
        current_user = get_member_safe(profile, session.get("current_user_id"))
        lines.append(
            f"会话证据 S{session.get('session_id')} | 时间={session.get('date_time')} | "
            f"current_user={current_user.get('name')}({session.get('current_user_id')})"
        )
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


def event_anchor(event):
    if not event:
        return ""
    scenario = event.get("scenario_label") or event.get("scenario_category") or event.get("scenario_type") or "家庭安排"
    detail = event.get("sub-event", "")
    return f"{event.get('date')}的{scenario}安排（{detail}）"


def session_anchor(session):
    return f"{session.get('date_time')}的家庭AI助手对话"


def format_qa_evidence(profile, plan):
    if plan.get("category") in {"multi-hop", "temporal"}:
        return format_evidence_for_qa(profile)
    return format_single_qa_evidence(profile, plan)


def normalize_generated_qa(item, qa_id, plan):
    category = item.get("category") or plan["category"]
    question = sanitize_question(item.get("question", ""))
    return {
        "qa_id": f"QA_{qa_id}",
        "session_id": item.get("session_id", plan.get("session_id")),
        "time": item.get("time", plan.get("time", "")),
        "entity_id": item.get("entity_id", plan.get("current_user_id", "")),
        "category": category,
        "memory_dimension": pick_memory_dimension(plan=plan, item=item),
        "QA_details": {
            "user": question,
            "assistant": item.get("answer", ""),
        },
        "evidence_turn_ids": item.get("evidence_turn_ids", []),
        "source_fact_ids": item.get("source_fact_ids", []),
        "difficulty": item.get("difficulty", "medium"),
        "requires_temporal_reasoning": item.get("requires_temporal_reasoning", category == "temporal"),
        "requires_tool_use": item.get("requires_tool_use", False),
        "requires_cross_member_reference": item.get("requires_cross_member_reference", category == "multi-hop"),
    }


def sanitize_question(question):
    question = question or ""
    replacements = [
        (r"会话\s*S\d+", ""),
        (r"事件\s*E\d+", ""),
        (r"S\d+", ""),
        (r"E\d+", ""),
        (r"turn\s*\d+", ""),
        (r"fact\s*\d+", ""),
    ]
    for pattern, replacement in replacements:
        question = re.sub(pattern, replacement, question, flags=re.IGNORECASE)
    question = re.sub(r"\s+", " ", question)
    question = re.sub(r"（\s*）", "", question)
    question = re.sub(r"\(\s*\)", "", question)
    return question.strip()


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
            len(profile.get("flat_sessions", profile.get("sessions", []))),
            len(profile.get("graph", [])),
            len(qa_plans),
        )
        for idx, plan in enumerate(qa_plans, start=1):
            prompt = HOUSEHOLD_QA_PROMPT.format(
                qa_plan=json.dumps(plan, ensure_ascii=False, separators=(",", ":")),
                profile=format_family_for_qa(profile),
                context=format_qa_evidence(profile, plan),
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
    sessions = profile.get("flat_sessions", profile.get("sessions", []))

    for session in sessions:
        event = event_for_session(profile, session)
        current_user = get_member_safe(profile, session["current_user_id"])
        evidence = first_turn_id(session)
        dimensions = event.get("memory_dimensions", []) if event else []

        if event:
            qa_items.append(make_qa(
                qa_id,
                session,
                current_user["person_id"],
                "single-hop",
                f"在{session_anchor(session)}中，{current_user['name']}和AI助手围绕{event_anchor(event)}主要记录了什么周末事项？",
                event["sub-event"],
                evidence,
                [event["id"]],
                difficulty="easy",
                memory_dimension=select_memory_dimension(dimensions, "single-hop"),
            ))
            qa_id += 1

            qa_items.append(make_qa(
                qa_id,
                session,
                current_user["person_id"],
                "multi-hop",
                f"结合{event_anchor(event)}和{session_anchor(session)}，家庭周末安排主要涉及哪些成员或责任分工？",
                f"主要涉及{participants_answer(profile, event)}。",
                evidence,
                [event["id"]],
                memory_dimension=select_memory_dimension(dimensions, "multi-hop"),
            ))
            qa_id += 1

            qa_items.append(make_qa(
                qa_id,
                session,
                current_user["person_id"],
                "temporal",
                f"在{session_anchor(session)}中，{current_user['name']}围绕{event_anchor(event)}是否提到需要按具体时间后续确认或提醒的安排？",
                "有，需要按对话中提到的具体周末安排再次提醒或确认。",
                [turn["dia_id"] for turn in session.get("turns", [])[-2:]],
                [event["id"]],
                requires_temporal_reasoning=True,
                memory_dimension=select_memory_dimension(dimensions, "temporal"),
            ))
            qa_id += 1

            qa_items.append(make_qa(
                qa_id,
                session,
                current_user["person_id"],
                "open-domain",
                f"从常识看，家庭在安排{event_anchor(event)}时通常还需要提前确认什么？",
                "通常还需要提前确认时间、地点、参与人和必要物品。",
                evidence,
                [event["id"]],
                difficulty="medium",
                memory_dimension=select_memory_dimension(dimensions, "open-domain"),
            ))
            qa_id += 1

        qa_items.append(make_qa(
            qa_id,
            session,
            current_user["person_id"],
            "adversarial",
            f"在{session_anchor(session)}中，{current_user['name']}是否明确说明家庭外出交通费用的具体金额？",
            "无法从对话中确定",
            [],
            [],
            difficulty="hard",
            requires_cross_member_reference=False,
            memory_dimension=select_memory_dimension(dimensions, "adversarial"),
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
