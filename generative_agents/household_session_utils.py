"""
Household multi-user session generation utilities.

Each session keeps the original interaction shape: one current household user
talks with the AI assistant, grounded in current time and relevant events.
"""

import json
import logging
import random
import re

from generative_agents.household_utils import get_member, strip_generation_prompts


def detect_mentioned_member_ids(text, profile):
    return [
        member["person_id"] for member in profile.get("members", [])
        if member["name"] in text
    ]


def choose_current_user(profile, relevant_events=None, sess_id=1):
    member_ids = [member["person_id"] for member in profile["members"] if member.get("can_chat_with_ai", True)]
    if relevant_events:
        participant_ids = []
        for event in relevant_events:
            participant_ids.extend(event.get("participants", []))
        participant_ids = [pid for pid in participant_ids if pid in member_ids]
        if participant_ids:
            return participant_ids[(sess_id - 1) % len(participant_ids)]
    return member_ids[(sess_id - 1) % len(member_ids)]


def event_brief(events):
    if not events:
        return "暂时没有新的家庭安排。"
    return "；".join([event["sub-event"] for event in events])


def scoped_member_ids(profile, current_user, relevant_events):
    ids = {current_user["person_id"]}
    for event in relevant_events or []:
        ids.update(event.get("participants", []))
        ids.update(event.get("mentioned_members", []))
    return ids


def scoped_family_context(profile, current_user, relevant_events):
    profile = strip_generation_prompts(profile)
    current_user = strip_generation_prompts(current_user)
    relevant_events = strip_generation_prompts(relevant_events)
    ids = scoped_member_ids(profile, current_user, relevant_events)
    members = [
        {
            "person_id": member["person_id"],
            "name": member["name"],
            "age": member.get("age"),
            "life_stage": member.get("life_stage"),
            "family_role_label": member.get("family_role_label"),
            "persona_summary": member.get("persona_summary"),
        }
        for member in profile.get("members", [])
        if member["person_id"] in ids
    ]
    relations = [
        rel for rel in profile.get("relations", [])
        if rel.get("from") in ids and rel.get("to") in ids
    ]
    pets = [
        pet for pet in profile.get("pets", [])
        if pet.get("caretaker_id") in ids
    ]
    responsibilities = [
        item for item in profile.get("role_responsibilities", [])
        if item.get("person_id") in ids
    ]
    return json.dumps({
        "family_name": profile.get("family", {}).get("family_name"),
        "household_type": profile.get("family", {}).get("household_type"),
        "current_user_related_members": members,
        "current_user_related_relations": relations,
        "current_user_related_pets": pets,
        "current_user_related_responsibilities": responsibilities,
    }, ensure_ascii=False, indent=2)


def non_speaking_member_names(profile, current_user):
    return [
        member["name"] for member in profile.get("members", [])
        if member.get("person_id") != current_user.get("person_id")
    ]


def build_household_turn_prompt(
    profile,
    assistant,
    current_user,
    relevant_events,
    curr_date_time,
    prev_date_time="",
    previous_summary="",
    conv_so_far="",
    speaker_role="user",
    instruct_stop=False,
):
    speaker_label = "当前用户" if speaker_role == "user" else "AI助手"
    role_instruction = (
        f"你只能扮演当前用户{current_user['name']}，生成{current_user['name']}接下来对AI助手说的一句话。"
        if speaker_role == "user"
        else f"你只能扮演AI助手{assistant['name']}，只对当前用户{current_user['name']}刚才的请求或聊天做日常回复。"
    )
    assistant_style = (
        "- AI助手回复时只做自然日常回应，不要主动补充额外事实、不要解释记忆维度、事件编号、家庭关系图或内部推理。\n"
        "- AI助手可以确认、安慰、提醒、简单追问，但不要替用户扩展新的安排。"
        if speaker_role == "assistant"
        else ""
    )
    blocked_speakers = "、".join(non_speaking_member_names(profile, current_user)) or "无"
    stop_instruction = "如果对话已经自然完成，可以只输出“再见！”。" if instruct_stop else ""
    return f"""
你正在生成家庭多用户与AI助手的逐轮对话。每次只生成一位说话人的下一句话。

当前时间：{curr_date_time}
上次会话时间：{prev_date_time or "无"}
AI助手：{assistant["persona_summary"]}
当前用户：{current_user["name"]}，{current_user["persona_summary"]}
当前事件：{event_brief(relevant_events)}
当前交流人相关家庭上下文：
{scoped_family_context(profile, current_user, relevant_events)}
上一轮会话摘要：
{previous_summary or "无"}
已有对话：
{conv_so_far or "无"}

要求：
- 当前轮次角色是：{speaker_label}
- {role_instruction}
- 只输出一句话，不要输出 JSON，不要输出说话人名字。
- 本段对话只有两个发言方：当前用户{current_user['name']} 和 AI助手{assistant['name']}。
- 其他家庭成员不能作为发言人，不能直接说话，不能写成“某某：……”的形式。
- 不能发言的家庭成员包括：{blocked_speakers}。
- 本 session 主要基于当前事件、当前交流人相关家庭上下文、上一轮会话摘要和已有对话生成。
- AI助手只知道当前交流人相关的家庭信息，不能使用未提供的其他家庭关系。
- 当前用户可以自然提及当前事件里的其他人，但AI助手只能按用户说法日常回应。
- 宠物只能作为照护对象，不能作为发言人。
- 对话必须围绕当前事件、当前时间和周末/休闲任务特征。
- 每句自然口语化，不要超过 40 个中文字。
{assistant_style}
{stop_instruction}
""".strip()


def build_household_session_prompt(profile, assistant, current_user, relevant_events, curr_date_time, prev_date_time="", previous_summary=""):
    return build_household_turn_prompt(
        profile,
        assistant,
        current_user,
        relevant_events,
        curr_date_time,
        prev_date_time=prev_date_time,
        previous_summary=previous_summary,
        conv_so_far="",
        speaker_role="user",
    )


FACT_EXTRACTION_PROMPT = """
根据家庭多用户与AI助手的对话内容，为每个说话人写一份简洁的观察事实列表。

要求：
- 输出必须是 JSON 字典，不要输出 markdown。
- 键是说话人姓名，值是事实列表。
- 每个事实用二元数组表示：[事实文本, 来源ID]。
- 来源ID 必须来自对话 dia_id 或相关 event id。
- 事实应客观、可作为记忆数据库使用，不要写抽象评价。

当前会话可见上下文：
{context}

当前会话：
{conversation}
""".strip()


def parse_json_value(text):
    text = text.strip().replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"(\[.*\]|\{.*\})", text, re.DOTALL)
        if not match:
            raise
    return json.loads(match.group())


def format_fact_context_text(profile, current_user, current_events):
    profile = strip_generation_prompts(profile)
    current_user = strip_generation_prompts(current_user)
    current_events = strip_generation_prompts(current_events)
    lines = [
        f"当前用户：{current_user['name']}，{current_user.get('age')}岁，{current_user.get('family_role_label')}，{current_user.get('life_stage')}。",
        f"当前用户画像：{current_user.get('persona_summary', '')}",
    ]
    related_context = json.loads(scoped_family_context(profile, current_user, current_events))
    related_members = related_context.get("current_user_related_members", [])
    if related_members:
        member_lines = []
        for member in related_members:
            if member["person_id"] == current_user["person_id"]:
                continue
            member_lines.append(
                f"{member['name']}({member.get('age')}岁,{member.get('family_role_label')},{member.get('life_stage')})"
            )
        if member_lines:
            lines.append("相关成员：" + "；".join(member_lines))
    relations = related_context.get("current_user_related_relations", [])
    if relations:
        lines.append("相关关系：" + "；".join([f"{rel['from']}-{rel['type']}-{rel['to']}" for rel in relations]))
    responsibilities = related_context.get("current_user_related_responsibilities", [])
    if responsibilities:
        lines.append("相关责任：" + "；".join([f"{item.get('person_id')}:{item.get('responsibility')}" for item in responsibilities]))
    pets = related_context.get("current_user_related_pets", [])
    if pets:
        lines.append("相关宠物：" + "；".join([f"{pet.get('name')}({pet.get('species')}),照护人={pet.get('caretaker_id')}" for pet in pets]))
    if current_events:
        event_lines = [
            f"{event['id']}({event['date']},{event['scenario_type']}): {event['sub-event']}"
            for event in current_events
        ]
        lines.append("当前事件：" + "；".join(event_lines))
    return "\n".join(lines)


def format_conversation_for_facts(session):
    lines = []
    for turn in session.get("turns", []):
        text = turn.get("clean_text") or turn.get("text", "")
        lines.append(f"[{turn.get('dia_id')}] {turn.get('speaker')}: {text}")
    return "\n".join(lines)


def clean_turn_text(text, speaker_name, profile=None, allowed_speaker_names=None):
    text = text.strip().split("\n")[0].strip()
    text = text.replace("```", "").strip()
    allowed_speaker_names = allowed_speaker_names or [speaker_name]
    speaker_prefixes = []
    for name in allowed_speaker_names:
        speaker_prefixes.extend([f"{name}：", f"{name}:"])
    if profile:
        for member in profile.get("members", []):
            for label in [member.get("name"), member.get("family_role_label")]:
                if label:
                    speaker_prefixes.extend([f"{label}：", f"{label}:"])
    for prefix in speaker_prefixes + ["用户：", "用户:", "AI助手：", "AI助手:", "助手：", "助手:"]:
        if text.startswith(prefix):
            if not any(prefix.startswith(name) for name in allowed_speaker_names):
                logging.warning("Removed non-current speaker prefix from generated turn: %s", prefix)
            text = text[len(prefix):].strip()
    return text.strip('"“” ')


def user_opening(current_user, events):
    if not events:
        return f"小艾，帮我看一下这个周末家里有什么安排。"
    event = events[0]
    return f"小艾，{event['sub-event']}你帮我记一下。"


def assistant_response(profile, current_user, events):
    if not events:
        return "好的，我帮你留意一下。"
    return "好的，我记下了。"


def follow_up_user(profile, current_user, events):
    if not events:
        return "如果有人临时改计划，也提醒我一下。"
    event = events[0]
    names = [
        member["name"] for member in profile["members"]
        if member["person_id"] in event.get("participants", []) and member["person_id"] != current_user["person_id"]
    ]
    if names:
        return f"到时候也提醒一下{'、'.join(names)}，别把时间弄混了。"
    return "这件事如果有变化，你也帮我提醒一下。"


def assistant_memory_reply(profile, events):
    if not events:
        return "没问题，到时候提醒你。"
    event = events[0]
    if event["scenario_type"] == "changed_weekend_plan":
        return "好的，我会按新的来提醒。"
    if event["scenario_type"] == "conflicting_plans":
        return "嗯，那我晚点提醒你们再确认一下。"
    if event["scenario_type"] == "pet_weekend_care":
        return "好的，到时候我提醒你。"
    return "没问题，到时候我提醒你。"


def closing_user(current_user):
    return "好，那周末前再提醒我一次。"


def closing_assistant():
    return "好的，我会在合适时间提醒你。"


def make_turn(sess_id, turn_idx, speaker_name, speaker_id, text, current_user_id, profile, related_event_ids):
    return {
        "text": text,
        "raw_text": text,
        "speaker": speaker_name,
        "clean_text": text,
        "dia_id": f"D{sess_id}:{turn_idx}",
        "speaker_id": speaker_id,
        "current_user_id": current_user_id,
        "mentioned_member_ids": detect_mentioned_member_ids(text, profile),
        "related_event_ids": related_event_ids,
    }


def generate_household_session(
    profile,
    assistant,
    sess_id,
    curr_date_time,
    current_user_id=None,
    prev_date_time="",
    previous_summary="",
    max_turns=8,
    use_llm=True,
    on_turn_generated=None,
):
    events = profile.get(f"events_session_{sess_id}", [])
    if current_user_id is None:
        current_user_id = choose_current_user(profile, events, sess_id)
    current_user = get_member(profile, current_user_id)
    related_event_ids = [event["id"] for event in events]
    logging.info(
        "Preparing session %s: current_user=%s(%s), related_events=%s, curr_time=%s",
        sess_id,
        current_user["name"],
        current_user_id,
        related_event_ids,
        curr_date_time,
    )

    initial_prompt = build_household_session_prompt(
        profile=profile,
        assistant=assistant,
        current_user=current_user,
        relevant_events=events,
        curr_date_time=curr_date_time,
        prev_date_time=prev_date_time,
        previous_summary=previous_summary,
    )

    try:
        if not use_llm:
            raise ValueError("LLM disabled")
        from global_methods import run_chatgpt

        session = []
        conv_so_far = ""
        curr_speaker = "user"
        stop_dialog_count = max_turns if max_turns <= 4 else random.choice(list(range(4, max_turns + 1)))
        logging.info("Session %s iterative LLM generation started: max_turns=%s, stop_hint_from_turn=%s", sess_id, max_turns, stop_dialog_count)

        for turn_idx in range(1, max_turns + 1):
            speaker_name = current_user["name"] if curr_speaker == "user" else assistant["name"]
            speaker_id = current_user_id if curr_speaker == "user" else "assistant"
            turn_prompt = build_household_turn_prompt(
                profile=profile,
                assistant=assistant,
                current_user=current_user,
                relevant_events=events,
                curr_date_time=curr_date_time,
                prev_date_time=prev_date_time,
                previous_summary=previous_summary,
                conv_so_far=conv_so_far,
                speaker_role=curr_speaker,
                instruct_stop=turn_idx >= stop_dialog_count,
            )
            logging.info("Session %s turn %s calling LLM for speaker=%s", sess_id, turn_idx, speaker_name)
            output = clean_turn_text(
                run_chatgpt(turn_prompt, num_gen=1, num_tokens_request=120, temperature=1.1),
                speaker_name,
                profile=profile,
                allowed_speaker_names=[speaker_name],
            )
            if not output:
                output = "再见！" if turn_idx >= 4 else ("好的。" if curr_speaker == "assistant" else "我知道了。")

            session.append(make_turn(sess_id, turn_idx, speaker_name, speaker_id, output, current_user_id, profile, related_event_ids))
            conv_so_far += f"{speaker_name}: {output}\n"
            logging.info("Session %s turn %s [%s]: %s", sess_id, turn_idx, speaker_name, output)
            if on_turn_generated:
                on_turn_generated({
                    "session_id": sess_id,
                    "date_time": curr_date_time,
                    "current_user_id": current_user_id,
                    "current_user_name": current_user["name"],
                    "related_event_ids": related_event_ids,
                    "turn_generation_mode": "iterative_partial",
                    "turns": list(session),
                })

            if output.endswith("再见！") and turn_idx >= 4:
                logging.info("Session %s ended early at turn %s", sess_id, turn_idx)
                break
            curr_speaker = "assistant" if curr_speaker == "user" else "user"

        if len(session) < 2:
            raise ValueError("Not enough valid generated turns")
        return {
            "session_id": sess_id,
            "date_time": curr_date_time,
            "current_user_id": current_user_id,
            "current_user_name": current_user["name"],
            "related_event_ids": related_event_ids,
            "turn_generation_mode": "iterative",
            "turns": session,
        }
    except Exception as exc:
        logging.warning("LLM household session generation failed, using fallback turns: %s", exc)
        scripted_turns = [
            (current_user["name"], current_user_id, user_opening(current_user, events)),
            (assistant["name"], "assistant", assistant_response(profile, current_user, events)),
            (current_user["name"], current_user_id, follow_up_user(profile, current_user, events)),
            (assistant["name"], "assistant", assistant_memory_reply(profile, events)),
            (current_user["name"], current_user_id, closing_user(current_user)),
            (assistant["name"], "assistant", closing_assistant()),
        ]
    scripted_turns = scripted_turns[:max(2, min(max_turns, len(scripted_turns)))]
    session = [
        make_turn(sess_id, idx, speaker, speaker_id, text, current_user_id, profile, related_event_ids)
        for idx, (speaker, speaker_id, text) in enumerate(scripted_turns, start=1)
    ]

    return {
        "session_id": sess_id,
        "date_time": curr_date_time,
        "current_user_id": current_user_id,
        "current_user_name": current_user["name"],
        "related_event_ids": related_event_ids,
        "turn_generation_mode": "fallback",
        "turns": session,
    }


def summarize_session(session):
    user_name = session.get("current_user_name", "家庭成员")
    event_ids = "、".join(session.get("related_event_ids", [])) or "无具体事件"
    return f"{user_name}与AI助手确认了周末家庭安排，相关事件包括{event_ids}。"


def extract_household_session_facts(profile, session, use_llm=True):
    try:
        if not use_llm:
            raise ValueError("LLM disabled")
        from global_methods import run_chatgpt

        logging.info("Calling LLM for session %s fact extraction", session.get("session_id"))
        current_user = get_member(profile, session["current_user_id"])
        current_events = [
            event for event in profile.get("graph", [])
            if event.get("id") in session.get("related_event_ids", [])
        ]
        prompt = FACT_EXTRACTION_PROMPT.format(
            context=format_fact_context_text(profile, current_user, current_events),
            conversation=format_conversation_for_facts(session),
        )
        logging.info("Session %s fact extraction prompt chars=%s", session.get("session_id"), len(prompt))
        response = run_chatgpt(prompt, num_gen=1, num_tokens_request=1800, temperature=0.5)
        logging.info("LLM fact extraction response received for session %s: chars=%s", session.get("session_id"), len(response or ""))
        facts = parse_json_value(response)
        if isinstance(facts, dict):
            logging.info("Session %s LLM facts parsed: speakers=%s", session.get("session_id"), list(facts.keys()))
            return facts
        raise ValueError("Facts response is not a JSON dict")
    except Exception as exc:
        logging.warning("LLM household fact extraction failed, using fallback facts: %s", exc)

    facts = {}
    event_map = {event["id"]: event for event in profile.get("graph", [])}
    for turn in session.get("turns", []):
        speaker = turn["speaker"]
        facts.setdefault(speaker, [])
        source = turn["dia_id"]
        facts[speaker].append([f"{speaker}说：{turn['clean_text']}", source])

    for event_id in session.get("related_event_ids", []):
        event = event_map.get(event_id)
        if not event:
            continue
        for person_id in event.get("participants", []):
            member = get_member(profile, person_id)
            facts.setdefault(member["name"], [])
            facts[member["name"]].append([event["sub-event"], event_id])
    return facts
