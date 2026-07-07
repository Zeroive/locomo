"""
Generate staged LLM movie-scene dialogue cases from real memory CSV rows.

The flow mirrors the staged household generator at a smaller scope:
profile -> case plans -> iterative sessions -> facts/evidence -> answer.
"""

import argparse
import csv
import json
import logging
import random
import re
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


DEFAULT_INPUT_CSV = REPO_ROOT / "data" / "real_data_memory.csv"
DEFAULT_OUT_DIR = REPO_ROOT / "real_memory_movie_dialogues" / "output"
CASE_CATEGORIES = ["single_hop", "multi_hop", "temporal", "open_domain", "adversarial"]
HOUSEHOLD_STRUCTURES = {
    "single_person": {
        "household_type": "single_person",
        "household_size": "1人",
        "household_structure": "单人家庭",
        "members": [
            {"entity_id": "person_001", "person_name": "用户", "family_role_label": "本人", "can_chat_with_ai": True}
        ],
        "relations": [],
    },
    "couple_only": {
        "household_type": "couple_only",
        "household_size": "2人",
        "household_structure": "伴侣同住",
        "members": [
            {"entity_id": "person_001", "person_name": "用户", "family_role_label": "本人", "can_chat_with_ai": True},
            {"entity_id": "person_002", "person_name": "伴侣", "family_role_label": "伴侣", "can_chat_with_ai": False},
        ],
        "relations": [
            {"from": "person_001", "to": "person_002", "type": "SPOUSE_OF"},
            {"from": "person_002", "to": "person_001", "type": "SPOUSE_OF"},
        ],
    },
    "nuclear_family": {
        "household_type": "nuclear_family",
        "household_size": "3人",
        "household_structure": "双亲 + 1个孩子",
        "members": [
            {"entity_id": "person_001", "person_name": "用户", "family_role_label": "家长", "can_chat_with_ai": True},
            {"entity_id": "person_002", "person_name": "伴侣", "family_role_label": "家长", "can_chat_with_ai": False},
            {"entity_id": "person_003", "person_name": "孩子", "family_role_label": "孩子", "can_chat_with_ai": False},
        ],
        "relations": [
            {"from": "person_001", "to": "person_002", "type": "SPOUSE_OF"},
            {"from": "person_002", "to": "person_001", "type": "SPOUSE_OF"},
            {"from": "person_001", "to": "person_003", "type": "PARENT_OF"},
            {"from": "person_003", "to": "person_001", "type": "CHILD_OF"},
            {"from": "person_002", "to": "person_003", "type": "PARENT_OF"},
            {"from": "person_003", "to": "person_002", "type": "CHILD_OF"},
        ],
    },
    "single_parent_family": {
        "household_type": "single_parent_family",
        "household_size": "2人",
        "household_structure": "单亲 + 1个孩子",
        "members": [
            {"entity_id": "person_001", "person_name": "用户", "family_role_label": "单亲家长", "can_chat_with_ai": True},
            {"entity_id": "person_002", "person_name": "孩子", "family_role_label": "孩子", "can_chat_with_ai": False},
        ],
        "relations": [
            {"from": "person_001", "to": "person_002", "type": "PARENT_OF"},
            {"from": "person_002", "to": "person_001", "type": "CHILD_OF"},
        ],
    },
    "single_parent_two_children": {
        "household_type": "single_parent_two_children",
        "household_size": "3人",
        "household_structure": "单亲 + 2个孩子",
        "members": [
            {"entity_id": "person_001", "person_name": "用户", "family_role_label": "单亲家长", "can_chat_with_ai": True},
            {"entity_id": "person_002", "person_name": "孩子A", "family_role_label": "孩子", "can_chat_with_ai": False},
            {"entity_id": "person_003", "person_name": "孩子B", "family_role_label": "孩子", "can_chat_with_ai": False},
        ],
        "relations": [
            {"from": "person_001", "to": "person_002", "type": "PARENT_OF"},
            {"from": "person_002", "to": "person_001", "type": "CHILD_OF"},
            {"from": "person_001", "to": "person_003", "type": "PARENT_OF"},
            {"from": "person_003", "to": "person_001", "type": "CHILD_OF"},
            {"from": "person_002", "to": "person_003", "type": "SIBLING_OF"},
            {"from": "person_003", "to": "person_002", "type": "SIBLING_OF"},
        ],
    },
    "couple_with_grandparent": {
        "household_type": "couple_with_grandparent",
        "household_size": "3人",
        "household_structure": "夫妻 + 1个祖辈",
        "members": [
            {"entity_id": "person_001", "person_name": "用户", "family_role_label": "伴侣", "can_chat_with_ai": True},
            {"entity_id": "person_002", "person_name": "伴侣", "family_role_label": "伴侣", "can_chat_with_ai": False},
            {"entity_id": "person_003", "person_name": "长辈", "family_role_label": "祖辈", "can_chat_with_ai": False},
        ],
        "relations": [
            {"from": "person_001", "to": "person_002", "type": "SPOUSE_OF"},
            {"from": "person_002", "to": "person_001", "type": "SPOUSE_OF"},
            {"from": "person_003", "to": "person_001", "type": "PARENT_OF"},
            {"from": "person_001", "to": "person_003", "type": "CHILD_OF"},
            {"from": "person_003", "to": "person_002", "type": "IN_LAW_OF"},
            {"from": "person_002", "to": "person_003", "type": "IN_LAW_OF"},
        ],
    },
    "single_parent_child_grandparent": {
        "household_type": "single_parent_child_grandparent",
        "household_size": "3人",
        "household_structure": "单亲 + 1个孩子 + 1个祖辈",
        "members": [
            {"entity_id": "person_001", "person_name": "用户", "family_role_label": "单亲家长", "can_chat_with_ai": True},
            {"entity_id": "person_002", "person_name": "孩子", "family_role_label": "孩子", "can_chat_with_ai": False},
            {"entity_id": "person_003", "person_name": "长辈", "family_role_label": "祖辈", "can_chat_with_ai": False},
        ],
        "relations": [
            {"from": "person_001", "to": "person_002", "type": "PARENT_OF"},
            {"from": "person_002", "to": "person_001", "type": "CHILD_OF"},
            {"from": "person_003", "to": "person_001", "type": "PARENT_OF"},
            {"from": "person_001", "to": "person_003", "type": "CHILD_OF"},
            {"from": "person_003", "to": "person_002", "type": "GRANDPARENT_OF"},
            {"from": "person_002", "to": "person_003", "type": "GRANDCHILD_OF"},
        ],
    },
    "three_generation_family": {
        "household_type": "three_generation_family",
        "household_size": "4人",
        "household_structure": "祖辈 + 双亲 + 1个孩子",
        "members": [
            {"entity_id": "person_001", "person_name": "用户", "family_role_label": "家长", "can_chat_with_ai": True},
            {"entity_id": "person_002", "person_name": "伴侣", "family_role_label": "家长", "can_chat_with_ai": False},
            {"entity_id": "person_003", "person_name": "孩子", "family_role_label": "孩子", "can_chat_with_ai": False},
            {"entity_id": "person_004", "person_name": "长辈", "family_role_label": "祖辈", "can_chat_with_ai": False},
        ],
        "relations": [
            {"from": "person_001", "to": "person_002", "type": "SPOUSE_OF"},
            {"from": "person_002", "to": "person_001", "type": "SPOUSE_OF"},
            {"from": "person_001", "to": "person_003", "type": "PARENT_OF"},
            {"from": "person_003", "to": "person_001", "type": "CHILD_OF"},
            {"from": "person_004", "to": "person_001", "type": "PARENT_OF"},
            {"from": "person_001", "to": "person_004", "type": "CHILD_OF"},
            {"from": "person_004", "to": "person_003", "type": "GRANDPARENT_OF"},
            {"from": "person_003", "to": "person_004", "type": "GRANDCHILD_OF"},
        ],
    },
}
HOUSEHOLD_STRUCTURE_ORDER = list(HOUSEHOLD_STRUCTURES)
MULTI_PERSON_STRUCTURE_ORDER = [
    "nuclear_family",
    "single_parent_two_children",
    "couple_with_grandparent",
    "single_parent_child_grandparent",
]


logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(message)s")


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-csv", type=Path, default=DEFAULT_INPUT_CSV)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--num-cases",
        type=int,
        default=None,
        help="Number of final cases to generate. In row mode this limits CSV rows; in sampled-household mode this sets household count.",
    )
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--temperature", type=float, default=0.8)
    parser.add_argument("--max-turns-per-session", type=int, default=4)
    parser.add_argument("--max-workers", type=int, default=1, help="Parallel ability workers. 1 keeps serial generation.")
    parser.add_argument(
        "--num-sampled-households",
        type=int,
        default=0,
        help="Generate this many multi-person households by randomly sampling one CSV memory row per member.",
    )
    parser.add_argument(
        "--sample-without-replacement",
        action="store_true",
        help="When generating sampled households, avoid reusing CSV rows until all rows are exhausted.",
    )
    parser.add_argument(
        "--household-structure",
        choices=["cycle", *HOUSEHOLD_STRUCTURE_ORDER],
        default="cycle",
        help="Prebuilt household structure to use. Default cycles through the structure pool by CSV row.",
    )
    return parser.parse_args()


def save_json(data, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_csv_rows(path, limit=None):
    path = Path(path)
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if limit is not None:
        rows = rows[:limit]
    return rows


def resolve_num_cases(args):
    if args.num_cases is not None and args.num_cases < 1:
        raise ValueError("--num-cases must be a positive integer")
    if args.num_sampled_households > 0:
        return args.num_cases or args.num_sampled_households
    return args.num_cases or args.limit


def call_llm(prompt, temperature=0.8, num_tokens_request=256):
    from global_methods import run_chatgpt

    return run_chatgpt(
        prompt,
        num_gen=1,
        num_tokens_request=num_tokens_request,
        temperature=temperature,
    ).strip()


def parse_json_value(text):
    text = (text or "").strip().replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(1))


def clean_turn_text(text, speaker_name):
    text = (text or "").strip()
    text = text.replace("```", "").replace("“", "").replace("”", "").strip()
    text = re.sub(r"^(用户|AI助手|助手|User|Assistant|%s)\s*[：:]\s*" % re.escape(speaker_name), "", text)
    text = re.sub(r"\s+", " ", text).strip()
    if "\n" in text:
        text = text.splitlines()[0].strip()
    return text[:80]


def classify_ability(memory_content, user_input):
    memory_text = memory_content or ""
    input_text = user_input or ""
    if "小品" in memory_text or "相声" in memory_text:
        return "play_sketch"
    if "影片" in memory_text or "电影" in memory_text or "播放了《" in memory_text or "观看" in memory_text:
        return "play_movie"
    if "歌" in memory_text or "听" in memory_text or "换一首" in memory_text:
        return "play_music"
    if "自述" in memory_text or "意味着什么" in memory_text or "坏人" in memory_text:
        return "chat_common"
    if "小品" in input_text or "相声" in input_text:
        return "play_sketch"
    if "歌" in input_text or "听" in input_text or "换一首" in input_text or "成都" in input_text:
        return "play_music"
    if "影片" in input_text or "电影" in input_text or "播放" in input_text or "观看" in input_text:
        return "play_movie"
    return "assistant_common"


def split_memory_lines(memory_content):
    return [line.strip() for line in (memory_content or "").splitlines() if line.strip()]


def extract_memory_keywords(memory_content):
    keywords = []
    for quoted in re.findall(r"《([^》]+)》", memory_content or ""):
        keywords.append(quoted)
    for token in re.findall(r"[\u4e00-\u9fa5A-Za-z0-9]{2,}", memory_content or ""):
        if token in {"用户", "播放", "观看", "喜欢", "要求", "自述"}:
            continue
        if token not in keywords:
            keywords.append(token)
    return keywords[:8]


def row_value(row, key):
    return (row.get(key) or "").strip()


def select_household_structure(row_index, requested="cycle"):
    if requested == "cycle":
        requested = HOUSEHOLD_STRUCTURE_ORDER[(row_index - 1) % len(HOUSEHOLD_STRUCTURE_ORDER)]
    template = HOUSEHOLD_STRUCTURES[requested]
    return json.loads(json.dumps(template, ensure_ascii=False))


def summarize_household_context(household):
    members = [
        f"{member['entity_id']}={member['person_name']}({member.get('family_role_label', '')})"
        for member in household.get("members", [])
    ]
    relations = [
        f"{rel['from']}-{rel['type']}-{rel['to']}"
        for rel in household.get("relations", [])
    ]
    return "；".join([
        f"结构={household.get('household_structure', '')}",
        f"成员={','.join(members)}",
        f"关系={','.join(relations) if relations else '无'}",
    ])


def get_household_member(household, entity_id):
    for member in household.get("members", []):
        if member.get("entity_id") == entity_id:
            return member
    raise ValueError(f"unknown household member: {entity_id}")


def make_source(row, row_index):
    memory_content = row_value(row, "记忆内容")
    user_input = row_value(row, "用户输入")
    return {
        "row_index": row_index,
        "timestamp": row_value(row, "时间戳"),
        "user_id": row_value(row, "用户ID"),
        "user_input": user_input,
        "memory_content": memory_content,
    }


def make_profile_from_source(profile_id, source, household, current_user_id="person_001"):
    current_user = get_household_member(household, current_user_id)
    return {
        "row_id": profile_id,
        "source": source,
        "household": {**household, "current_user_id": current_user_id},
        "current_user_id": current_user_id,
        "current_user_name": current_user.get("person_name", current_user_id),
        "memory_lines": split_memory_lines(source["memory_content"]),
        "memory_keywords": extract_memory_keywords(source["memory_content"]),
        "ability": classify_ability(source["memory_content"], source["user_input"]),
    }


def make_profile(row, row_index, household_structure="cycle"):
    row_id = f"RMR-{row_index:03d}"
    household_template = select_household_structure(row_index, household_structure)
    household = {
        "family_id": f"family_{row_index:03d}",
        "family_name": f"家庭{row_index:03d}",
        "household_type": household_template["household_type"],
        "household_size": household_template["household_size"],
        "household_structure": household_template["household_structure"],
        "current_user_id": "person_001",
        "members": household_template["members"],
        "relations": household_template["relations"],
        "assistant": {"entity_id": "agent_a", "person_name": "AI助手"},
    }
    return make_profile_from_source(row_id, make_source(row, row_index), household, "person_001")


def build_memory_points_prompt(profile):
    return f"""
请根据真实记忆内容，总结后续生成用户与AI助手对话时必须体现的相关记忆点。

行时间戳：{profile['source']['timestamp']}
记忆内容：
{profile['source']['memory_content']}
能力类型：{profile['ability']}

输出 JSON：
{{
  "memory_points": ["记忆点1", "记忆点2"],
  "required_keywords": ["关键词1", "关键词2"],
  "scene_hint": "一句话说明适合生成的观影/娱乐助手上下文"
}}

要求：
- 只输出 JSON。
- memory_points 必须覆盖记忆内容里的所有事实，不要新增未知事实。
- required_keywords 应包含片名、歌曲名、小品名或关键自述内容。
- scene_hint 必须适合家庭观影/客厅娱乐/AI助手操作场景。
""".strip()


def normalize_memory_points(profile, data):
    memory_points = data.get("memory_points") if isinstance(data, dict) else []
    required_keywords = data.get("required_keywords") if isinstance(data, dict) else []
    if memory_points is None:
        memory_points = []
    if required_keywords is None:
        required_keywords = []
    if not isinstance(memory_points, list):
        memory_points = [str(memory_points)]
    if not isinstance(required_keywords, list):
        required_keywords = [str(required_keywords)]
    memory_points = [str(item).strip() for item in memory_points if str(item).strip()]
    required_keywords = [str(item).strip() for item in required_keywords if str(item).strip()]
    if not memory_points:
        memory_points = profile["memory_lines"] or [profile["source"]["memory_content"]]
    if not required_keywords:
        required_keywords = profile["memory_keywords"]
    scene_hint = str(data.get("scene_hint", "") if isinstance(data, dict) else "").strip()
    return {
        "memory_points": memory_points,
        "required_keywords": required_keywords,
        "scene_hint": scene_hint or "围绕家庭客厅里的观影、听歌、播放节目或AI助手日常操作生成对话。",
    }


def generate_memory_points(profile, args):
    last_error = None
    for attempt in range(1, args.max_retries + 1):
        try:
            logging.info("%s summarizing memory points attempt %s", profile["row_id"], attempt)
            prompt = build_memory_points_prompt(profile)
            assert_dialogue_prompt_has_no_question(profile, prompt)
            response = call_llm(prompt, temperature=0.4, num_tokens_request=600)
            return normalize_memory_points(profile, parse_json_value(response))
        except Exception as exc:
            last_error = exc
            logging.warning("%s memory point summary failed on attempt %s: %s", profile["row_id"], attempt, exc)
            time.sleep(min(attempt, 3))
    logging.warning("%s using fallback memory points after failures: %s", profile["row_id"], last_error)
    return normalize_memory_points(profile, {})


def build_dialogue_topics_prompt(profile):
    category_lines = "\n".join([f"- {category}: {case_instruction(category)}" for category in CASE_CATEGORIES])
    return f"""
请根据模型总结的记忆点、当前能力类型和五类测评要求，先规划后续对话主题。

能力类型：{profile['ability']}
家庭结构：{summarize_household_context(profile['household'])}
记忆内容：{profile['source']['memory_content']}
模型总结的相关记忆点：{json.dumps(profile.get('memory_points', []), ensure_ascii=False)}
必须出现的关键词：{json.dumps(profile.get('required_keywords', []), ensure_ascii=False)}
场景提示：{profile.get('scene_hint', '')}

五类测评要求：
{category_lines}

输出 JSON，格式：
{{
  "dialogue_topics": {{
    "single_hop": {{"topic": "一句话主题", "session_goals": ["S1目标"]}},
    "multi_hop": {{"topic": "一句话主题", "session_goals": ["S1目标", "S2目标"]}},
    "temporal": {{"topic": "一句话主题", "session_goals": ["S1目标", "S2目标"]}},
    "open_domain": {{"topic": "一句话主题", "session_goals": ["S1目标", "S2目标"]}},
    "adversarial": {{"topic": "一句话主题", "session_goals": ["S1目标"]}}
  }}
}}

要求：
- 只输出 JSON。
- 主题必须符合能力类型：影片播放、听歌、小品播放、闲聊或通用AI助手功能。
- 每个主题都要适合家庭客厅/观影/娱乐助手场景。
- session_goals 要说明每个会话应该提供什么上下文证据。
- adversarial 的目标要自然提到相关记忆，但不能提供回答问题所需的缺失信息。
- 不要新增记忆内容之外的具体片源、歌手、演员、年份、平台等细节。
""".strip()


def fallback_dialogue_topics(profile):
    memory_points = "；".join(profile.get("memory_points", [])) or profile["source"]["memory_content"]
    ability = profile["ability"]
    return {
        "single_hop": {
            "topic": f"围绕{ability}能力，在一次客厅娱乐请求中自然体现记忆点。",
            "session_goals": [f"S1直接包含可回答问题的记忆信息：{memory_points}"],
        },
        "multi_hop": {
            "topic": f"围绕{ability}能力，把用户偏好和播放请求拆到两次会话中。",
            "session_goals": ["S1提供记忆中的偏好或历史行为", "S2提供当前播放/切换请求"],
        },
        "temporal": {
            "topic": f"围绕{ability}能力，用两个不同时间的会话体现先后顺序。",
            "session_goals": ["S1提供较早发生的娱乐操作", "S2提供较晚发生的娱乐操作或延续请求"],
        },
        "open_domain": {
            "topic": f"围绕{ability}能力，提供实体或场景，让答案需要结合常识。",
            "session_goals": ["S1提供相关实体或节目类型", "S2提供日常播放场景"],
        },
        "adversarial": {
            "topic": f"围绕{ability}能力自然聊天，但避开问题所需的关键答案。",
            "session_goals": ["S1只体现相关记忆点，不补充缺失细节"],
        },
    }


def normalize_dialogue_topics(profile, data):
    raw_topics = data.get("dialogue_topics") if isinstance(data, dict) else {}
    if not isinstance(raw_topics, dict):
        raw_topics = {}
    fallback = fallback_dialogue_topics(profile)
    topics = {}
    for category in CASE_CATEGORIES:
        item = raw_topics.get(category, {})
        if not isinstance(item, dict):
            item = {}
        topic = str(item.get("topic", "")).strip() or fallback[category]["topic"]
        session_goals = item.get("session_goals", [])
        if not isinstance(session_goals, list):
            session_goals = [str(session_goals)]
        session_goals = [str(goal).strip() for goal in session_goals if str(goal).strip()]
        if not session_goals:
            session_goals = fallback[category]["session_goals"]
        topics[category] = {
            "topic": topic,
            "session_goals": session_goals,
        }
    return topics


def generate_dialogue_topics(profile, args):
    last_error = None
    for attempt in range(1, args.max_retries + 1):
        try:
            logging.info("%s generating dialogue topics attempt %s", profile["row_id"], attempt)
            prompt = build_dialogue_topics_prompt(profile)
            assert_dialogue_prompt_has_no_question(profile, prompt)
            response = call_llm(prompt, temperature=0.5, num_tokens_request=1000)
            return normalize_dialogue_topics(profile, parse_json_value(response))
        except Exception as exc:
            last_error = exc
            logging.warning("%s dialogue topic generation failed on attempt %s: %s", profile["row_id"], attempt, exc)
            time.sleep(min(attempt, 3))
    logging.warning("%s using fallback dialogue topics after failures: %s", profile["row_id"], last_error)
    return fallback_dialogue_topics(profile)


def build_case_plan(profile, category):
    session_count = 1
    if category in {"multi_hop", "temporal", "open_domain"}:
        session_count = 2
    topic_plan = profile.get("dialogue_topics", {}).get(category, {})
    return {
        "case_id": f"{profile['row_id']}-{category}",
        "category": category,
        "ability": profile["ability"],
        "session_count": session_count,
        "question": profile["source"]["user_input"],
        "dialogue_topic": topic_plan.get("topic", ""),
        "session_goals": topic_plan.get("session_goals", []),
    }


def case_instruction(category):
    instructions = {
        "single_hop": "单跳：只让一个会话直接提供回答问题所需的信息。",
        "multi_hop": "多跳：把回答问题所需信息拆到至少两个会话里，必须结合多个会话才能回答。",
        "temporal": "时间推理：安排至少两个有明确先后时间的会话，答案依赖时间顺序。",
        "open_domain": "开放领域：上下文只给相关实体或场景，答案还需要结合日常常识。",
        "adversarial": "对抗性：上下文不要提供回答问题所需的信息，答案应无法从对话中确定。",
    }
    return instructions[category]


def format_dialogue(session):
    lines = []
    for pair in session.get("QA_details", []):
        lines.append(f"用户：{pair.get('user', '')}")
        lines.append(f"AI助手：{pair.get('assistant', '')}")
    return "\n".join(lines)


def previous_sessions_text(sessions):
    if not sessions:
        return "无"
    blocks = []
    for session in sessions:
        blocks.append(f"{session['session_id']} {session['date_time']}\n{format_dialogue(session)}")
    return "\n\n".join(blocks)


def build_turn_context(profile, plan, session, prior_sessions, conv_so_far):
    household_context = summarize_household_context(profile["household"])
    memory_lines = "；".join(profile["memory_lines"]) or "无"
    memory_points = "；".join(profile.get("memory_points", [])) or memory_lines
    keywords = "、".join(profile.get("required_keywords") or profile["memory_keywords"]) or "无"
    scene_hint = profile.get("scene_hint") or "围绕家庭客厅里的观影、听歌、播放节目或AI助手日常操作生成对话。"
    session_idx = int(session["session_id"].replace("S", "")) - 1
    session_goals = plan.get("session_goals") or []
    session_goal = session_goals[session_idx] if session_idx < len(session_goals) else (session_goals[-1] if session_goals else "围绕主题自然生成本会话。")
    return f"""
你在为家庭观影/客厅娱乐场景生成用户与AI助手的短对话，每次只生成一个说话方的一句话。

家庭：{profile['household']['family_name']}
家庭结构上下文：{household_context}
行时间戳：{profile['source']['timestamp']}
记忆内容：{memory_lines}
模型总结的相关记忆点：{memory_points}
记忆关键词：{keywords}
场景提示：{scene_hint}
能力类型：{plan['ability']}
对话主题：{plan.get('dialogue_topic') or '围绕记忆点生成客厅娱乐助手对话。'}
当前会话目标：{session_goal}
测评类别：{plan['category']}，{case_instruction(plan['category'])}
当前会话：{session['session_id']}，时间：{session['date_time']}
之前会话：
{previous_sessions_text(prior_sessions)}
当前会话已有对话：
{conv_so_far or "无"}
""".strip(), keywords


def build_user_turn_prompt(profile, plan, session, prior_sessions, conv_so_far, turn_idx):
    context, keywords = build_turn_context(profile, plan, session, prior_sessions, conv_so_far)
    current_user_id = profile.get("current_user_id", "person_001")
    current_user_name = profile.get("current_user_name", "用户")
    first_turn_hint = ""
    if turn_idx == 1 and plan["category"] != "adversarial":
        first_turn_hint = f"- 首轮或本会话中要自然带出至少一个记忆关键词：{keywords}。\n"
    if plan["category"] == "adversarial":
        first_turn_hint = (
            f"- 仍要自然带出至少一个记忆关键词：{keywords}。\n"
            "- 但不要补充记忆内容之外的片源、歌手、演员、年份、平台、具体含义等额外细节，保持问题无法从上下文确定。\n"
        )
    return f"""
{context}

要求：
- 当前说话方：用户。
- 你只能扮演 {current_user_id}（{current_user_name}），生成该用户接下来对AI助手说的一句自然口语。
- 用户说话要日常、随意，可以像在客厅里随口吩咐。
- 用户可以表达播放影片、听歌、小品、切换内容、调音量、开关投影等需求。
- 用户可以自然提到其他家庭成员，但其他家庭成员不能直接发言。
- 只输出一句话，不要输出说话人名字，不要输出JSON。
- 内容要建立在行时间戳下，并自然包含相关记忆点里的信息。
- 优先服务“对话主题”和“当前会话目标”，不要偏离到无关家庭闲聊。
- 语气轻松、随意、日常，不超过15个中文字。
{first_turn_hint}
""".strip()


def build_assistant_turn_prompt(profile, plan, session, prior_sessions, conv_so_far):
    context, _ = build_turn_context(profile, plan, session, prior_sessions, conv_so_far)
    current_user_id = profile.get("current_user_id", "person_001")
    current_user_name = profile.get("current_user_name", "用户")
    return f"""
{context}

要求：
- 当前说话方：AI助手。
- 你只能扮演AI助手，回复用户上一句话。
- 回复要简短正式，以确认操作、说明已执行、简单询问必要信息为主。
- 不主动扩展事实，不补充用户没有说过的片源、歌手、演员、年份、平台、剧情、家庭安排或个人评价。
- 不主动制造新记忆，不解释测评类别、证据、推理过程或内部目标。
- 如果用户请求明确，直接确认执行；如果缺少必要信息，只问一个简短澄清问题。
- 只输出一句话，不要输出说话人名字，不要输出JSON。
- 本段对话只有 {current_user_id}（{current_user_name}）和AI助手两个说话方，其他家庭成员只能被提及，不能直接发言。
- 语气稳妥、克制，不超过30个中文字。
""".strip()


def build_turn_prompt(profile, plan, session, prior_sessions, conv_so_far, speaker_role, turn_idx):
    if speaker_role == "user":
        return build_user_turn_prompt(profile, plan, session, prior_sessions, conv_so_far, turn_idx)
    return build_assistant_turn_prompt(profile, plan, session, prior_sessions, conv_so_far)


def assert_dialogue_prompt_has_no_question(profile, prompt):
    question = profile.get("source", {}).get("user_input", "")
    if question and question in prompt:
        raise ValueError("dialogue-generation prompt must not include CSV user_input question")


def generate_session(profile, plan, session_id, date_time, prior_sessions, args):
    session = {"session_id": session_id, "date_time": date_time, "QA_details": []}
    conv_so_far = ""
    pending_user = None
    max_turns = max(2, args.max_turns_per_session)
    if max_turns % 2 == 1:
        max_turns -= 1

    for turn_idx in range(1, max_turns + 1):
        speaker_role = "user" if turn_idx % 2 == 1 else "assistant"
        prompt = build_turn_prompt(profile, plan, session, prior_sessions, conv_so_far, speaker_role, turn_idx)
        assert_dialogue_prompt_has_no_question(profile, prompt)
        output = clean_turn_text(call_llm(prompt, temperature=args.temperature, num_tokens_request=140), "用户" if speaker_role == "user" else "AI助手")
        if not output:
            raise ValueError(f"empty {speaker_role} turn")
        conv_so_far += f"{'用户' if speaker_role == 'user' else 'AI助手'}：{output}\n"
        if speaker_role == "user":
            pending_user = output
        else:
            session["QA_details"].append({"user": pending_user or "", "assistant": output})
            pending_user = None
    return session


def session_dates(row_timestamp, count):
    try:
        base = datetime.fromisoformat(row_timestamp.replace("Z", "+00:00"))
    except ValueError:
        base = datetime(2026, 6, 29, 19, 0)
    if count == 1:
        return [base.strftime("%Y-%m-%d %H:%M")]
    start = base - timedelta(minutes=15 * (count - 1))
    return [
        (start + timedelta(minutes=15 * idx)).strftime("%Y-%m-%d %H:%M")
        for idx in range(count)
    ]


def generate_sessions(profile, plan, args):
    sessions = []
    dates = session_dates(profile["source"]["timestamp"], plan["session_count"])
    for idx, date_time in enumerate(dates, start=1):
        session = generate_session(profile, plan, f"S{idx}", date_time, sessions, args)
        sessions.append(session)
    return sessions


def build_fact_prompt(profile, plan, sessions):
    return f"""
请从下面观影/娱乐助手对话中抽取结构化事实，并标出能支撑测评问题答案的证据会话。

测评问题（来自CSV，不能改写）：{profile['source']['user_input']}
行时间戳：{profile['source']['timestamp']}
记忆内容：{profile['source']['memory_content']}
相关记忆点：{json.dumps(profile.get('memory_points', []), ensure_ascii=False)}
测评类别：{plan['category']}，{case_instruction(plan['category'])}

会话：
{previous_sessions_text(sessions)}

输出 JSON，格式：
{{
  "facts": ["事实1", "事实2"],
  "evidence_session_ids": ["S1"],
  "evidence_note": "一句话说明证据如何支持或为什么不支持回答"
}}

要求：
- 只输出 JSON。
- single_hop 的 evidence_session_ids 只能有 1 个。
- multi_hop 至少 2 个。
- temporal 至少 2 个且事实要体现时间先后。
- adversarial 如果上下文没有答案，evidence_session_ids 输出 []。
""".strip()


def normalize_facts_evidence(profile, plan, data):
    facts = data.get("facts") if isinstance(data, dict) else []
    evidence_ids = data.get("evidence_session_ids") if isinstance(data, dict) else []
    if not isinstance(facts, list):
        facts = [str(facts)]
    facts = [str(item).strip() for item in facts if str(item).strip()]
    if not isinstance(evidence_ids, list):
        evidence_ids = [str(evidence_ids)]
    evidence_ids = [str(item).strip() for item in evidence_ids if str(item).strip()]
    if plan["category"] == "single_hop":
        evidence_ids = evidence_ids[:1] or ["S1"]
    elif plan["category"] in {"multi_hop", "temporal"} and len(evidence_ids) < 2:
        evidence_ids = ["S1", "S2"]
    elif plan["category"] == "adversarial":
        evidence_ids = []
    return {
        "facts": facts,
        "evidence_session_ids": evidence_ids,
        "evidence_note": str(data.get("evidence_note", "") if isinstance(data, dict) else "").strip(),
    }


def extract_facts_evidence(profile, plan, sessions, args):
    prompt = build_fact_prompt(profile, plan, sessions)
    response = call_llm(prompt, temperature=0.4, num_tokens_request=700)
    return normalize_facts_evidence(profile, plan, parse_json_value(response))


def build_answer_prompt(profile, plan, sessions, facts_data):
    return f"""
请基于给定会话、事实和测评类别回答问题。问题来自CSV，必须原样使用，不要改写。

问题：{profile['source']['user_input']}
行时间戳：{profile['source']['timestamp']}
测评类别：{plan['category']}，{case_instruction(plan['category'])}
记忆内容：{profile['source']['memory_content']}
相关记忆点：{json.dumps(profile.get('memory_points', []), ensure_ascii=False)}
事实：{json.dumps(facts_data.get('facts', []), ensure_ascii=False)}
证据会话ID：{json.dumps(facts_data.get('evidence_session_ids', []), ensure_ascii=False)}

会话：
{previous_sessions_text(sessions)}

输出 JSON：
{{
  "answer": "简短答案",
  "answer_note": "一句话说明答案依据"
}}

要求：
- 只输出 JSON。
- adversarial 类别必须回答“无法从对话中确定”或同义表达。
- open_domain 类别需要结合常识回答，不能只复述对话。
- 其他类别必须基于证据会话回答。
""".strip()


def generate_answer(profile, plan, sessions, facts_data, args):
    prompt = build_answer_prompt(profile, plan, sessions, facts_data)
    response = call_llm(prompt, temperature=0.5, num_tokens_request=500)
    data = parse_json_value(response)
    answer = str(data.get("answer", "")).strip()
    if plan["category"] == "adversarial" and "无法" not in answer and "不能确定" not in answer:
        answer = "无法从对话中确定。"
    return {
        "answer": answer,
        "answer_note": str(data.get("answer_note", "")).strip(),
    }


def all_dialogue_text(sessions):
    return "\n".join(previous_sessions_text(sessions).splitlines())


def memory_covered(profile, sessions, category):
    keywords = profile.get("required_keywords") or profile.get("memory_keywords", [])
    if not keywords:
        return True
    text = all_dialogue_text(sessions)
    return any(keyword in text for keyword in keywords)


def validate_case(profile, case):
    category = case.get("category")
    if category not in CASE_CATEGORIES:
        raise ValueError(f"unknown category: {category}")
    if case.get("question") != profile["source"]["user_input"]:
        raise ValueError("question must equal CSV user_input")
    sessions = case.get("sessions") or []
    if not sessions:
        raise ValueError("missing sessions")
    for session in sessions:
        pairs = session.get("QA_details") or []
        if not pairs:
            raise ValueError(f"{session.get('session_id')} missing QA_details")
        for pair in pairs:
            if not pair.get("user") or not pair.get("assistant"):
                raise ValueError(f"{session.get('session_id')} has incomplete pair")
    evidence_ids = case.get("evidence_session_ids") or []
    if category == "single_hop" and len(evidence_ids) != 1:
        raise ValueError("single_hop must have exactly one evidence session")
    if category == "multi_hop" and len(evidence_ids) < 2:
        raise ValueError("multi_hop must have at least two evidence sessions")
    if category == "temporal":
        if len(sessions) < 2 or len(evidence_ids) < 2:
            raise ValueError("temporal must have at least two evidence sessions")
    if category == "adversarial":
        if evidence_ids:
            raise ValueError("adversarial must not have evidence sessions")
        if "无法" not in case.get("answer", "") and "不能确定" not in case.get("answer", ""):
            raise ValueError("adversarial answer must be unanswerable")
    if not memory_covered(profile, sessions, category):
        raise ValueError("memory keywords not covered in dialogue")


def generate_case(profile, plan, args):
    sessions = generate_sessions(profile, plan, args)
    facts_data = extract_facts_evidence(profile, plan, sessions, args)
    answer_data = generate_answer(profile, plan, sessions, facts_data, args)
    case = {
        "case_id": plan["case_id"],
        "category": plan["category"],
        "current_user_id": profile.get("current_user_id", "person_001"),
        "current_user_name": profile.get("current_user_name", "用户"),
        "dimension_tags": {
            "scene": "观影场景",
            "ability": plan["ability"],
            "generation_method": "llm_staged",
        },
        "dialogue_topic": plan.get("dialogue_topic", ""),
        "session_goals": plan.get("session_goals", []),
        "sessions": sessions,
        "facts": facts_data["facts"],
        "question": plan["question"],
        "answer": answer_data["answer"],
        "answer_note": answer_data["answer_note"],
        "evidence_session_ids": facts_data["evidence_session_ids"],
        "evidence_note": facts_data["evidence_note"],
    }
    validate_case(profile, case)
    return case


def generate_case_with_retries(profile, plan, args):
    last_error = None
    for attempt in range(1, args.max_retries + 1):
        try:
            logging.info("%s generating %s attempt %s", profile["row_id"], plan["category"], attempt)
            return generate_case(profile, plan, args)
        except Exception as exc:
            last_error = exc
            logging.warning("%s %s failed on attempt %s: %s", profile["row_id"], plan["category"], attempt, exc)
            time.sleep(min(attempt, 3))
    raise RuntimeError(f"{plan['case_id']} failed after {args.max_retries} retries: {last_error}")


def build_row_output(profile, cases):
    return {
        "row_id": profile["row_id"],
        "source": profile["source"],
        "household": profile["household"],
        "memory_points": profile.get("memory_points", []),
        "required_keywords": profile.get("required_keywords", []),
        "scene_hint": profile.get("scene_hint", ""),
        "dialogue_topics": profile.get("dialogue_topics", {}),
        "cases": cases,
    }


def validate_row_output(row_output):
    categories = [case.get("category") for case in row_output.get("cases", [])]
    if categories != CASE_CATEGORIES:
        raise ValueError(f"case categories mismatch: {categories}")
    source = row_output.get("source", {})
    if "memory_token" in source or "total_token" in source:
        raise ValueError("source must not include memory_token or total_token")
    household = row_output.get("household", {})
    for key in ("household_type", "household_size", "household_structure", "members", "relations"):
        if key not in household:
            raise ValueError(f"household missing {key}")
    chat_members = [member for member in household.get("members", []) if member.get("can_chat_with_ai")]
    if [member.get("entity_id") for member in chat_members] != ["person_001"]:
        raise ValueError("only person_001 should be marked as chat user")


def generate_row(row, row_index, args):
    profile = make_profile(row, row_index, args.household_structure)
    memory_summary = generate_memory_points(profile, args)
    profile["memory_points"] = memory_summary["memory_points"]
    profile["required_keywords"] = memory_summary["required_keywords"]
    profile["scene_hint"] = memory_summary["scene_hint"]
    profile["dialogue_topics"] = generate_dialogue_topics(profile, args)
    cases = []
    failures = []
    for category in CASE_CATEGORIES:
        plan = build_case_plan(profile, category)
        try:
            cases.append(generate_case_with_retries(profile, plan, args))
        except Exception as exc:
            failures.append({"case_id": plan["case_id"], "category": category, "error": str(exc)})
    row_output = build_row_output(profile, cases)
    if not failures:
        validate_row_output(row_output)
    return row_output, failures


def select_multi_person_structure(household_index, requested="cycle"):
    if requested == "cycle":
        requested = MULTI_PERSON_STRUCTURE_ORDER[(household_index - 1) % len(MULTI_PERSON_STRUCTURE_ORDER)]
    return select_household_structure(household_index, requested)


def make_sampled_household(household_index, args):
    household_template = select_multi_person_structure(household_index, args.household_structure)
    members = []
    for member in household_template["members"]:
        member_data = dict(member)
        member_data["can_chat_with_ai"] = True
        members.append(member_data)
    return {
        "family_id": f"sampled_family_{household_index:03d}",
        "family_name": f"采样家庭{household_index:03d}",
        "household_type": household_template["household_type"],
        "household_size": household_template["household_size"],
        "household_structure": household_template["household_structure"],
        "members": members,
        "relations": household_template["relations"],
        "assistant": {"entity_id": "agent_a", "person_name": "AI助手"},
    }


def make_member_profile(household_id, household, member, source):
    profile_id = f"{household_id}-{member['entity_id']}"
    return make_profile_from_source(profile_id, source, household, member["entity_id"])


def sample_sources_for_members(indexed_rows, member_count, rng, sample_without_replacement=False):
    if not indexed_rows:
        raise ValueError("cannot sample member memories from an empty CSV")
    if sample_without_replacement and member_count <= len(indexed_rows):
        sampled = rng.sample(indexed_rows, member_count)
    elif sample_without_replacement:
        shuffled = list(indexed_rows)
        rng.shuffle(shuffled)
        sampled = [shuffled[idx % len(shuffled)] for idx in range(member_count)]
    else:
        sampled = [rng.choice(indexed_rows) for _ in range(member_count)]
    return [make_source(row, row_index) for row_index, row in sampled]


def generate_member_cases(member_profile, args):
    memory_summary = generate_memory_points(member_profile, args)
    member_profile["memory_points"] = memory_summary["memory_points"]
    member_profile["required_keywords"] = memory_summary["required_keywords"]
    member_profile["scene_hint"] = memory_summary["scene_hint"]
    member_profile["dialogue_topics"] = generate_dialogue_topics(member_profile, args)

    cases = []
    failures = []
    for category in CASE_CATEGORIES:
        plan = build_case_plan(member_profile, category)
        try:
            cases.append(generate_case_with_retries(member_profile, plan, args))
        except Exception as exc:
            failures.append({"case_id": plan["case_id"], "category": category, "error": str(exc)})
    return {
        "profile_id": member_profile["row_id"],
        "entity_id": member_profile["current_user_id"],
        "person_name": member_profile["current_user_name"],
        "source": member_profile["source"],
        "ability": member_profile["ability"],
        "memory_points": member_profile.get("memory_points", []),
        "required_keywords": member_profile.get("required_keywords", []),
        "scene_hint": member_profile.get("scene_hint", ""),
        "dialogue_topics": member_profile.get("dialogue_topics", {}),
        "cases": cases,
    }, failures


def generate_sampled_household(household_index, indexed_rows, args):
    household_id = f"HMR-{household_index:03d}"
    household = make_sampled_household(household_index, args)
    sources = sample_sources_for_members(
        indexed_rows,
        len(household["members"]),
        random.Random(args.seed + household_index),
        sample_without_replacement=args.sample_without_replacement,
    )
    member_tasks = []
    for member, source in zip(household["members"], sources):
        member_tasks.append((member, make_member_profile(household_id, household, member, source)))

    generated_members = []
    failures = []
    for member, member_profile in member_tasks:
        try:
            member_output, member_failures = generate_member_cases(member_profile, args)
            member_output["family_role_label"] = member.get("family_role_label", "")
            generated_members.append(member_output)
            if member_failures:
                failures.append({"entity_id": member["entity_id"], "failures": member_failures})
        except Exception as exc:
            failures.append({"entity_id": member["entity_id"], "error": str(exc)})

    household_output = {
        "household_id": household_id,
        "household": household,
        "members": generated_members,
    }
    if not failures:
        validate_sampled_household_output(household_output)
    return household_output, failures


def validate_sampled_household_output(household_output):
    household = household_output.get("household", {})
    members = household_output.get("members", [])
    if len(members) != len(household.get("members", [])):
        raise ValueError("sampled household must include generated output for every member")
    for member in members:
        source = member.get("source", {})
        if "memory_token" in source or "total_token" in source:
            raise ValueError("member source must not include memory_token or total_token")
        categories = [case.get("category") for case in member.get("cases", [])]
        if categories and categories != CASE_CATEGORIES:
            raise ValueError(f"member case categories mismatch: {categories}")


def process_sampled_household(household_index, indexed_rows, args):
    household_id = f"HMR-{household_index:03d}"
    out_path = args.out_dir / f"{household_id}.json"
    if out_path.exists() and not args.overwrite:
        logging.info("%s exists, loading existing file", out_path)
        with out_path.open("r", encoding="utf-8") as f:
            existing = json.load(f)
        return household_index, existing, []
    logging.info("Generating sampled household %s", household_id)
    household_output, failures = generate_sampled_household(household_index, indexed_rows, args)
    save_json(household_output, out_path)
    return household_index, household_output, failures


def generate_sampled_households(rows, args):
    indexed_rows = list(enumerate(rows, start=1))
    household_count = resolve_num_cases(args)
    household_indices = list(range(1, household_count + 1))
    if args.max_workers <= 1 or len(household_indices) <= 1:
        return [
            process_sampled_household(household_index, indexed_rows, args)
            for household_index in household_indices
        ]

    max_workers = max(1, min(args.max_workers, len(household_indices)))
    logging.info("Parallel sampled household generation: households=%s, max_workers=%s", len(household_indices), max_workers)
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(process_sampled_household, household_index, indexed_rows, args): household_index
            for household_index in household_indices
        }
        for future in as_completed(futures):
            results.append(future.result())
    return sorted(results, key=lambda item: item[0])


def row_ability(row):
    return classify_ability(row_value(row, "记忆内容"), row_value(row, "用户输入"))


def grouped_rows_by_ability(rows):
    groups = defaultdict(list)
    for row_index, row in enumerate(rows, start=1):
        groups[row_ability(row)].append((row_index, row))
    return groups


def process_row(row_index, row, args):
    row_id = f"RMR-{row_index:03d}"
    out_path = args.out_dir / f"{row_id}.json"
    if out_path.exists() and not args.overwrite:
        logging.info("%s exists, loading existing file", out_path)
        with out_path.open("r", encoding="utf-8") as f:
            existing = json.load(f)
        return row_index, existing, []

    logging.info("Generating %s", row_id)
    row_output, failures = generate_row(row, row_index, args)
    save_json(row_output, out_path)
    if failures:
        logging.warning("%s saved with %s failed case(s)", row_id, len(failures))
    else:
        logging.info("%s saved with 5 cases", row_id)
    return row_index, row_output, failures


def process_ability_group(ability, indexed_rows, args):
    logging.info("Starting ability group %s with %s row(s)", ability, len(indexed_rows))
    results = []
    for row_index, row in indexed_rows:
        results.append(process_row(row_index, row, args))
    logging.info("Finished ability group %s", ability)
    return ability, results


def generate_rows_serial(rows, args):
    results = []
    for row_index, row in enumerate(rows, start=1):
        results.append(process_row(row_index, row, args))
    return results


def generate_rows_parallel_by_ability(rows, args):
    groups = grouped_rows_by_ability(rows)
    max_workers = max(1, min(args.max_workers, len(groups)))
    logging.info(
        "Parallel generation by ability: groups=%s, max_workers=%s",
        {ability: len(items) for ability, items in groups.items()},
        max_workers,
    )
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(process_ability_group, ability, indexed_rows, args): ability
            for ability, indexed_rows in groups.items()
        }
        for future in as_completed(futures):
            ability, group_results = future.result()
            logging.info("Collected ability group %s", ability)
            results.extend(group_results)
    return sorted(results, key=lambda item: item[0])


def main():
    args = parse_args()
    random.seed(args.seed)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    row_limit = None if args.num_sampled_households > 0 else resolve_num_cases(args)
    rows = load_csv_rows(args.input_csv, row_limit)

    if args.num_sampled_households > 0:
        logging.info("Sampled-household mode: generating %s household case(s)", resolve_num_cases(args))
        household_results = generate_sampled_households(rows, args)
        all_households = []
        failed_households = []
        for household_index, household_output, failures in household_results:
            household_id = f"HMR-{household_index:03d}"
            all_households.append(household_output)
            if failures:
                failed_households.append({"household_id": household_id, "failures": failures})
        save_json(all_households, args.out_dir / "all_households.json")
        if failed_households:
            save_json(failed_households, args.out_dir / "failed_households.json")
            logging.warning("Finished sampled households with failures: %s", args.out_dir / "failed_households.json")
        else:
            logging.info("Finished sampled households successfully: %s", args.out_dir / "all_households.json")
        return

    if args.max_workers > 1:
        logging.info("Row mode: generating %s row case(s)", len(rows))
        row_results = generate_rows_parallel_by_ability(rows, args)
    else:
        logging.info("Row mode: generating %s row case(s)", len(rows))
        row_results = generate_rows_serial(rows, args)

    all_rows = []
    failed_rows = []
    for row_index, row_output, failures in row_results:
        row_id = f"RMR-{row_index:03d}"
        all_rows.append(row_output)
        if failures:
            failed_rows.append({"row_id": row_id, "failures": failures})

    save_json(all_rows, args.out_dir / "all_rows.json")
    if failed_rows:
        save_json(failed_rows, args.out_dir / "failed_rows.json")
        logging.warning("Finished with failed cases: %s", args.out_dir / "failed_rows.json")
    else:
        logging.info("Finished successfully: %s", args.out_dir / "all_rows.json")


if __name__ == "__main__":
    main()
