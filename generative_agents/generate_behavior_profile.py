"""
行为画像生成主程序。

根据家庭画像和场景模板，生成连续多日的设备事件episodes。
支持多种场景：男主人下班回家、老人外出、小孩放学回家等。
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import logging
import argparse
import os, json, random, re
from datetime import date, timedelta, datetime

# 导入相关模块
from generative_agents.file_utils import save_agents, load_agents
from generative_agents.time_utils import get_random_time, datetimeObj2Str
from generative_agents.device_events_utils import (
    generate_scenario_device_episodes, 
    save_device_events, 
    get_device_events_summary,
    load_household_profile,
    get_scene_templates
)
from generative_agents.household_utils import (
    HOUSEHOLD_TYPES,
    sample_household_profile,
    save_json,
    strip_generation_prompts,
    validate_household,
)

logging.basicConfig(level=logging.INFO)

DEFAULT_PERSONA_SOURCE = str(Path(__file__).parent.parent / "data" / "msc_speakers_single.json")


def household_profile_path(out_dir):
    return os.path.join(out_dir, "household_profile.json")


def members_dir(out_dir):
    return os.path.join(out_dir, "members")


def save_profile(profile, out_dir):
    profile = strip_generation_prompts(profile)
    validate_household(profile)
    save_json(profile, household_profile_path(out_dir))
    target_dir = members_dir(out_dir)
    os.makedirs(target_dir, exist_ok=True)
    for member in profile.get("members", []):
        save_json(strip_generation_prompts(member), os.path.join(target_dir, f"{member['person_id']}.json"))
    logging.info("Saved household profile and %s member files under %s", len(profile.get("members", [])), out_dir)


def ensure_household_profile(args):
    candidates = [
        args.household_profile,
        household_profile_path(args.out_dir),
    ]
    for path in candidates:
        if path and os.path.exists(path) and not args.overwrite_persona:
            logging.info("Loading existing household profile: %s", path)
            return strip_generation_prompts(load_household_profile(path))

    logging.info(
        "Sampling household profile: household_type=%s, with_pet=%s, use_llm=%s",
        args.household_type,
        args.with_pet,
        not args.no_llm,
    )

    def autosave_profile(profile, reason):
        save_profile(profile, args.out_dir)
        logging.info("Autosaved household profile during sampling: reason=%s", reason)

    profile = sample_household_profile(
        household_type=args.household_type,
        persona_source=args.persona_source,
        family_id="family_001",
        with_pet=args.with_pet,
        use_llm=not args.no_llm,
        on_profile_updated=autosave_profile,
    )
    save_profile(profile, args.out_dir)
    return profile


def normalize_members(household_profile):
    members = household_profile.get('members') if household_profile else None
    if isinstance(members, list) and members:
        return members
    if isinstance(members, dict) and members:
        normalized = []
        for person_id, member in members.items():
            item = member.copy() if isinstance(member, dict) else {}
            item.setdefault('person_id', person_id)
            normalized.append(item)
        return normalized
    return []


def scenarios_for_member(member):
    role = member.get('family_role') or member.get('role') or ''
    if role in {'father', 'mother'}:
        return ['leave_work', 'family_return']
    if role in {'grandfather', 'grandmother'}:
        return ['elderly_outdoor']
    return []


def build_generation_plan(household_profile, scenario_filter=None):
    plan = []
    for member in normalize_members(household_profile):
        person_id = member.get('person_id') or member.get('id') or member.get('name')
        if not person_id:
            continue
        for scenario in scenarios_for_member(member):
            if scenario_filter and scenario != scenario_filter:
                continue
            plan.append({
                'person_id': person_id,
                'scenario': scenario,
                'member': member
            })
    if scenario_filter == 'all_leave_arm':
        plan.append({'person_id': 'home_system', 'scenario': 'all_leave_arm', 'member': {'person_id': 'home_system', 'name': '全屋系统'}})
    if scenario_filter == 'anomaly_detection':
        plan.append({'person_id': 'home_system', 'scenario': 'anomaly_detection', 'member': {'person_id': 'home_system', 'name': '全屋系统'}})
    if scenario_filter == 'visitor_arrival':
        plan.append({'person_id': 'visitor', 'scenario': 'visitor_arrival', 'member': {'person_id': 'visitor', 'name': '访客'}})
    if scenario_filter == 'child_return':
        for member in normalize_members(household_profile):
            role = member.get('family_role') or member.get('role') or ''
            if role in {'child', 'teenager'}:
                plan.append({'person_id': member.get('person_id'), 'scenario': 'child_return', 'member': member})
    return plan


def parse_args():
    """
    解析命令行参数。
    
    Returns:
        argparse.Namespace: 解析后的参数对象
    """
    parser = argparse.ArgumentParser(description="生成连续多日的设备事件行为画像")

    # 基础参数
    parser.add_argument('--out-dir', required=True, type=str, 
                        help="输出目录路径，用于保存生成的设备事件")
    parser.add_argument('--prompt-dir', type=str, default='./data/prompts',
                        help="Prompt模板目录路径")
    
    # 场景参数
    parser.add_argument('--scenario', type=str, default=None, 
                        choices=['family_return', 'leave_work', 'elderly_outdoor', 'child_return',
                                 'visitor_arrival', 'all_leave_arm', 'anomaly_detection'],
                        help="指定场景类型；不指定时根据家庭画像为每个成员生成其适用场景\n"
                             "场景说明：\n"
                             "  family_return       - 家庭成员下班回家\n"
                             "  leave_work          - 上班离家\n"
                             "  elderly_outdoor     - 老人独自外出\n"
                             "  child_return        - 小孩放学回家\n"
                             "  visitor_arrival     - 访客到家\n"
                             "  all_leave_arm       - 全员离家布防\n"
                             "  anomaly_detection   - 异常活动检测")
    
    # 时间参数
    parser.add_argument('--num-days', type=int, default=7, 
                        help="生成连续天数，默认为7天")
    parser.add_argument('--device-event-days', type=int, default=None, 
                        help="设备事件生成天数，未指定时使用--num-days")
    
    # 输出控制
    parser.add_argument('--overwrite-events', action='store_true', 
                        help="覆盖已存在的设备事件")
    parser.add_argument('--use-llm', action='store_true', default=True,
                        help="使用LLM生成设备事件（默认启用）")
    parser.add_argument('--use-rule-based', action='store_true',
                        help="使用规则模板生成设备事件（不使用LLM）")
    
    # 家庭画像参数
    parser.add_argument('--household-profile', type=str, 
                        default='./data/household/household_profile.json',
                        help="家庭画像文件路径")
    parser.add_argument('--persona-source', type=str, default=DEFAULT_PERSONA_SOURCE,
                        help="人物persona采样源，默认使用 msc_speakers_single.json")
    parser.add_argument('--household-type', type=str, default='three_generation_family',
                        choices=HOUSEHOLD_TYPES,
                        help="家庭类型，默认三代同堂，便于覆盖父母和祖父母行为场景")
    parser.add_argument('--with-pet', '--with-pets', dest='with_pet', action='store_true',
                        help="生成带宠物的家庭画像")
    parser.add_argument('--no-llm', action='store_true',
                        help="家庭画像采样不使用LLM增强")
    parser.add_argument('--overwrite-persona', action='store_true',
                        help="覆盖已有 household_profile.json 并重新采样家庭画像")
    parser.add_argument('--device-file', type=str, default='./data/devices/home_devices.json',
                        help="家庭设备库文件路径")
    
    args = parser.parse_args()
    
    # 如果未指定device-event-days，使用num-days
    if args.device_event_days is None:
        args.device_event_days = args.num_days
    
    return args


def main():
    """
    主函数：生成连续多日的设备事件行为画像
    """
    args = parse_args()
    
    # 确定是否使用LLM生成
    use_llm = args.use_llm and not args.use_rule_based
    
    # 创建输出目录
    if not os.path.exists(args.out_dir):
        os.makedirs(args.out_dir)
    
    # 加载或采样家庭画像
    household_profile = ensure_household_profile(args)
    
    # 加载场景模板
    scene_templates = get_scene_templates(args.device_file)
    
    generation_plan = build_generation_plan(household_profile, args.scenario)
    if not generation_plan:
        logging.warning("No member/scenario generation plan found. Nothing to generate.")
        return
    
    # 生成连续多日的设备事件episodes
    generation_method = "LLM" if use_llm else "rule-based"
    logging.info(
        "Generating %s days of device episodes for %s member-scenario plans using %s method",
        args.device_event_days,
        len(generation_plan),
        generation_method,
    )
    
    # 获取输出文件路径
    device_events_path = os.path.join(args.out_dir, 'device_events.json')
    
    # 检查是否已存在设备事件
    if os.path.exists(device_events_path) and not args.overwrite_events:
        logging.info(f"Device events already exist at {device_events_path}, skipping. Use --overwrite-events to regenerate.")
        return
    
    episodes = []
    for plan_item in generation_plan:
        logging.info(
            "Generating behavior episodes: person_id=%s scenario=%s",
            plan_item['person_id'],
            plan_item['scenario'],
        )
        episodes.extend(generate_scenario_device_episodes(
            scenario=plan_item['scenario'],
            num_days=args.device_event_days,
            household_profile=household_profile,
            scene_templates=scene_templates,
            device_file=args.device_file,
            use_llm=use_llm,
            subject_id=plan_item['person_id'],
            subject_profile=plan_item['member'],
        ))
    
    if episodes:
        # 保存设备事件到文件
        save_device_events_to_file(episodes, device_events_path)
        
        # 输出摘要
        summary = get_device_events_summary({'episodes': episodes})
        logging.info(f"Device episodes generation complete:\n{summary}")
    else:
        logging.warning("No device episodes were generated.")


def save_device_events_to_file(episodes, file_path):
    """
    将设备事件保存到文件。
    
    Args:
        episodes: episodes列表
        file_path: 输出文件路径
    """
    subjects = sorted({episode.get('subject_id', 'unknown') for episode in episodes})
    scenarios = sorted({episode.get('scene', 'unknown') for episode in episodes})
    output = {
        'version': '2.0',
        'dataset_type': 'household_behavior_profile',
        'scenarios': scenarios,
        'subjects': subjects,
        'generated_at': datetime.now().isoformat(),
        'generation_method': 'LLM' if episodes and 'daily_state_description' in episodes[0] else 'rule-based',
        'total_episodes': len(episodes),
        'episodes': episodes
    }
    
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    logging.info(f"Device events saved to {file_path}")


if __name__ == '__main__':
    main()
