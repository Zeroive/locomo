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

logging.basicConfig(level=logging.INFO)


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
    parser.add_argument('--scenario', type=str, default='family_return', 
                        choices=['male_leave_work', 'elderly_outdoor', 'child_return', 'family_return', 
                                 'visitor_arrival', 'all_leave_arm', 'anomaly_detection'],
                        help="指定场景类型，默认为 family_return（男主人下班回家）\n"
                             "场景说明：\n"
                             "  male_leave_work    - 男主人上班离家\n"
                             "  elderly_outdoor     - 老人独自外出\n"
                             "  child_return        - 小孩放学回家\n"
                             "  family_return       - 家庭成员下班回家\n"
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
    parser.add_argument('--device-file', type=str, default='./data/devices/home_devices.json',
                        help="家庭设备库文件路径")
    
    # Agent文件参数（用于兼容旧模式）
    parser.add_argument('--agent-a-file', type=str, default=None,
                        help="AI助手Agent文件路径（可选）")
    parser.add_argument('--agent-b-file', type=str, default=None,
                        help="用户Agent文件路径（可选）")

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
    
    # 加载家庭画像
    logging.info("Loading household profile...")
    household_profile = load_household_profile(args.household_profile)
    
    if not household_profile:
        logging.warning("No household profile found, will use default templates")
    
    # 加载场景模板
    scene_templates = get_scene_templates(args.device_file)
    
    # 生成连续多日的设备事件episodes
    generation_method = "LLM" if use_llm else "rule-based"
    logging.info(f"Generating {args.device_event_days} days of device episodes for scenario: {args.scenario} using {generation_method} method")
    
    # 获取输出文件路径
    device_events_path = os.path.join(args.out_dir, 'device_events.json')
    
    # 检查是否已存在设备事件
    if os.path.exists(device_events_path) and not args.overwrite_events:
        logging.info(f"Device events already exist at {device_events_path}, skipping. Use --overwrite-events to regenerate.")
        return
    
    # 生成设备事件episodes
    episodes = generate_scenario_device_episodes(
        scenario=args.scenario,
        num_days=args.device_event_days,
        household_profile=household_profile,
        scene_templates=scene_templates,
        device_file=args.device_file,
        use_llm=use_llm
    )
    
    if episodes:
        # 保存设备事件到文件
        save_device_events_to_file(episodes, device_events_path)
        
        # 如果提供了agent文件路径，同时保存到agent对象
        if args.agent_a_file and args.agent_b_file:
            try:
                agent_a = json.load(open(args.agent_a_file, 'r', encoding='utf-8'))
                agent_b = json.load(open(args.agent_b_file, 'r', encoding='utf-8'))
                
                # 将设备事件保存到agent_b（保持兼容性）
                agent_b['session_1_device_events'] = {
                    'sessions': {
                        'session_1': {
                            'episodes': episodes
                        }
                    }
                }
                
                # 保存更新的agent文件
                json.dump(agent_a, open(args.agent_a_file, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
                json.dump(agent_b, open(args.agent_b_file, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
                logging.info("Device events saved to agent files")
            except Exception as e:
                logging.warning(f"Failed to save to agent files: {e}")
        
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
    output = {
        'version': '2.0',
        'scenario': episodes[0]['scene'] if episodes else 'unknown',
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
