"""
Household multi-user session generation utilities.

Each session keeps the original interaction shape: one current household user
talks with the AI assistant, grounded in current time and relevant events.
"""

import json
import logging
import random
import re

from generative_agents.household_utils import get_member, summarize_relations


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
    speaker_name = current_user["name"] if speaker_role == "user" else assistant["name"]
    role_instruction = (
        f"请扮演当前用户{current_user['name']}，生成你接下来对AI助手说的一句话。"
        if speaker_role == "user"
        else f"请扮演AI助手{assistant['name']}，生成你接下来对{current_user['name']}说的一句话。"
    )
    stop_instruction = "如果对话已经自然完成，可以只输出“再见！”。" if instruct_stop else ""
    return f"""
你正在生成家庭多用户与AI助手的逐轮对话。每次只生成一位说话人的下一句话。

当前时间：{curr_date_time}
上次会话时间：{prev_date_time or "无"}
AI助手：{assistant["persona_summary"]}
当前用户：{current_user["name"]}，{current_user["persona_summary"]}
家庭背景：{profile["family"]["shared_background"]}
家庭关系：
{summarize_relations(profile)}
历史摘要：{previous_summary or "无"}
当前相关事件：{event_brief(relevant_events)}
已有对话：
{conv_so_far or "无"}

要求：
- 当前应该发言的人是：{speaker_name}
- {role_instruction}
- 只输出一句话，不要输出 JSON，不要输出说话人名字。
- 当前用户可以自然提及其他家庭成员。
- 宠物只能作为照护对象，不能作为发言人。
- 对话必须围绕当前事件、时间和周末/休闲任务特征。
- 每句自然口语化，不要超过 40 个中文字。
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

家庭背景：
{profile}

当前会话：
{session}
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


def clean_turn_text(text, speaker_name):
    text = text.strip().split("\n")[0].strip()
    text = text.replace("```", "").strip()
    for prefix in [f"{speaker_name}：", f"{speaker_name}:", "用户：", "用户:", "AI助手：", "AI助手:", "助手：", "助手:"]:
        if text.startswith(prefix):
            text = text[len(prefix):].strip()
    return text.strip('"“” ')


def user_opening(current_user, events):
    if not events:
        return f"小艾，帮我看一下这个周末家里有什么安排。"
    event = events[0]
    return f"小艾，{event['sub-event']}你帮我记一下。"


def assistant_response(profile, current_user, events):
    if not events:
        return f"好的，{current_user['name']}，我会帮你整理周末安排。"
    event = events[0]
    dims = "、".join(event.get("memory_dimensions", [])[:2])
    return f"好的，我记下了。这件事主要涉及{dims}。"


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
        return "没问题，我会按家庭成员的责任分工提醒。"
    event = events[0]
    if event["scenario_type"] == "changed_weekend_plan":
        return "好的，我会把这次变更放到最新安排里。"
    if event["scenario_type"] == "conflicting_plans":
        return "我会标记成计划冲突，提醒大家再确认一次。"
    if event["scenario_type"] == "pet_weekend_care":
        return "我会把宠物照护事项单独提醒。"
    return "没问题，我会按周末计划提醒相关家人。"


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


def generate_household_session(profile, assistant, sess_id, curr_date_time, prev_date_time="", previous_summary="", max_turns=8, use_llm=True):
    events = profile.get(f"events_session_{sess_id}", [])
    current_user_id = choose_current_user(profile, events, sess_id)
    current_user = get_member(profile, current_user_id)
    related_event_ids = [event["id"] for event in events]

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
            output = clean_turn_text(
                run_chatgpt(turn_prompt, num_gen=1, num_tokens_request=120, temperature=1.1),
                speaker_name,
            )
            if not output:
                output = "再见！" if turn_idx >= 4 else ("好的。" if curr_speaker == "assistant" else "我知道了。")

            session.append(make_turn(sess_id, turn_idx, speaker_name, speaker_id, output, current_user_id, profile, related_event_ids))
            conv_so_far += f"{speaker_name}: {output}\n"

            if output.endswith("再见！") and turn_idx >= 4:
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
            "generation_prompt": initial_prompt,
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
        "generation_prompt": initial_prompt,
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

        prompt = FACT_EXTRACTION_PROMPT.format(
            profile=json.dumps({
                "family": profile.get("family", {}),
                "members": profile.get("members", []),
                "relations": profile.get("relations", []),
                "pets": profile.get("pets", []),
            }, ensure_ascii=False, indent=2),
            session=json.dumps(session, ensure_ascii=False, indent=2),
        )
        response = run_chatgpt(prompt, num_gen=1, num_tokens_request=1800, temperature=0.5)
        facts = parse_json_value(response)
        if isinstance(facts, dict):
            session["fact_generation_prompt"] = prompt
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
