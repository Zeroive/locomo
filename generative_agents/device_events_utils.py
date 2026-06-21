"""
设备事件生成相关工具函数。

根据场景和对话内容，使用模型生成设备行为记录。
"""

import os
import json
import logging
from datetime import datetime, timedelta
from global_methods import run_json_trials

logging.basicConfig(level=logging.INFO)


# 设备事件生成 Prompt 模板
DEVICE_EVENTS_GENERATION_PROMPT = """你是一个智能家居系统分析师。根据给定的场景描述和对话内容，分析用户的设备操作行为，生成符合智能家居场景的设备事件记录。

场景类型: {scene_type}
场景描述: {scene_desc}

用户设备列表:
{user_devices}

对话内容:
{dialogue_content}

参考格式（你需要生成的输出格式）:
{{
    "episode_id": "ep_001",
    "scene": "场景名称",
    "confidence": 0.92,
    "annotated_events": [
        {{
            "event": {{
                "subject_id": "用户ID",
                "predicate": "操作类型（如：entered, activated, closed）",
                "object_id": "对象（如：entrance, away_mode, door_main）"
            }},
            "state_snapshot": {{
                "timestamp": "ISO8601格式时间戳",
                "persons": {{
                    "用户ID": {{
                        "status": "用户状态（如：moving_to_entrance, leaving, left_home）",
                        "location": "位置（如：entrance, outside）"
                    }}
                }},
                "devices": {{
                    "设备ID": {{
                        "state": "设备状态"
                    }}
                }}
            }}
        }}
    ]
}}

生成规则:
1. 根据场景类型和对话内容，生成3-5个连贯的设备事件
2. 每个事件包含 event（事件描述）和 state_snapshot（状态快照）
3. state_snapshot 需要包含 timestamp、persons（用户状态）、devices（设备状态）
4. 设备状态需要根据场景合理变化，如离家时关闭灯光、锁门等
5. 事件之间需要有因果关系和时间顺序
6. 输出必须是合法的JSON格式，不要包含其他解释文字

重要：
- timestamp 使用 ISO8601 格式，如 "2022-03-16T07:57:30+08:00"
- 只需要生成用户相关的设备事件，不需要包含AI助手
- 场景中涉及的设备必须来自用户设备列表

请生成设备事件记录："""


def get_dialogue_content(agent_a, agent_b, sess_id):
    """
    获取指定会话的对话内容。
    
    Args:
        agent_a: AI助手对象
        agent_b: 用户对象
        sess_id: 会话ID
        
    Returns:
        str: 格式化的对话内容字符串
    """
    dialogue = ""
    if 'session_%s_date_time' % sess_id in agent_a:
        dialogue += agent_a['session_%s_date_time' % sess_id] + '\n'
    
    if 'session_%s' % sess_id in agent_a:
        for dialog in agent_a['session_%s' % sess_id]:
            try:
                speaker = dialog.get('speaker', 'Unknown')
                text = dialog.get('clean_text', dialog.get('text', ''))
                dialogue += f"{speaker}: {text}\n"
            except Exception as e:
                logging.warning(f"Error processing dialog: {e}")
    
    return dialogue


def load_devices_config(device_file):
    """
    加载设备配置文件。
    
    Args:
        device_file: 设备配置文件路径
        
    Returns:
        dict: 设备配置字典
    """
    if os.path.exists(device_file):
        with open(device_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def get_user_devices_info(agent_b, device_file):
    """
    获取用户相关设备的详细信息。
    
    Args:
        agent_b: 用户对象
        device_file: 设备配置文件路径
        
    Returns:
        str: 格式化的设备信息字符串
    """
    devices_info = ""
    
    # 如果 agent_b 中有预选的设备列表
    if 'devices' in agent_b and agent_b['devices']:
        devices_config = load_devices_config(device_file)
        device_categories = devices_config.get('device_categories', {})
        
        for device_id, device_data in agent_b['devices'].items():
            # 查找设备的详细信息
            device_name = device_data.get('name', device_id)
            device_desc = ""
            
            # 在设备库中查找设备描述
            for category_name, category_data in device_categories.items():
                if device_id in category_data.get('devices', {}):
                    device_info = category_data['devices'][device_id]
                    device_name = device_info.get('name', device_id)
                    device_desc = device_info.get('description', '')
                    typical_events = device_info.get('typical_events', [])
                    capabilities = device_info.get('capabilities', {})
                    
                    capabilities_str = ""
                    if 'control' in capabilities:
                        capabilities_str += f"  可控制操作: {', '.join(capabilities['control'][:3])}\n"
                    if 'query' in capabilities:
                        capabilities_str += f"  可查询状态: {', '.join(capabilities['query'][:3])}"
                    
                    device_desc = f"""- {device_name}: {device_desc}
  典型事件: {', '.join([e.get('description', e.get('event_type', '')) for e in typical_events[:3]])}
{capabilities_str}
"""
                    break
            
            if device_desc:
                devices_info += device_desc
            else:
                devices_info += f"- {device_name}\n"
    
    return devices_info if devices_info else "未指定特定设备"


def generate_device_events_for_session(agent_a, agent_b, args, sess_id):
    """
    为单个会话生成设备事件记录。
    
    根据对话内容和场景，使用模型生成设备行为记录。
    
    Args:
        agent_a: AI助手对象
        agent_b: 用户对象
        args: 命令行参数
        sess_id: 会话ID
        
    Returns:
        dict: 设备事件记录字典
    """
    # 获取对话内容
    dialogue_content = get_dialogue_content(agent_a, agent_b, sess_id)
    
    if not dialogue_content.strip():
        logging.warning(f"Session {sess_id} has no dialogue content")
        return None
    
    # 获取用户设备信息
    device_file = args.device_file if hasattr(args, 'device_file') else './data/devices/home_devices.json'
    user_devices_info = get_user_devices_info(agent_b, device_file)
    
    # 获取场景信息
    scenario = args.scenario if hasattr(args, 'scenario') else 'male_leave_work'
    scenario_config = None
    
    if hasattr(args, 'scenario_file') and os.path.exists(args.scenario_file):
        with open(args.scenario_file, 'r', encoding='utf-8') as f:
            scenarios_data = json.load(f)
            scenario_config = scenarios_data.get('scenarios', {}).get(scenario, {})
    
    scene_type = scenario
    scene_desc = scenario_config.get('description', scenario) if scenario_config else scenario
    
    # 获取会话时间
    session_datetime = ""
    if 'session_%s_date_time' % sess_id in agent_a:
        session_datetime = agent_a['session_%s_date_time' % sess_id]
    
    # 构建 prompt
    prompt = DEVICE_EVENTS_GENERATION_PROMPT.format(
        scene_type=scene_type,
        scene_desc=scene_desc,
        user_devices=user_devices_info,
        dialogue_content=dialogue_content
    )
    
    logging.info(f"Generating device events for session {sess_id} with scenario: {scene_type}")
    
    # 调用模型生成设备事件
    try:
        result = run_json_trials(
            prompt, 
            num_gen=1, 
            num_tokens_request=2000, 
            use_16k=False
        )
        
        # 确保输出格式正确
        if isinstance(result, dict) and 'annotated_events' in result:
            # 添加 episode_id 和 scene 信息
            result['episode_id'] = f"ep_{sess_id:03d}"
            result['scene'] = scene_desc
            if 'confidence' not in result:
                result['confidence'] = 0.85
            
            logging.info(f"Generated {len(result.get('annotated_events', []))} device events for session {sess_id}")
            return result
        else:
            logging.warning(f"Unexpected result format from model: {type(result)}")
            return None
            
    except Exception as e:
        logging.error(f"Error generating device events for session {sess_id}: {e}")
        return None


def generate_all_device_events(agents, args):
    """
    为所有会话生成设备事件记录。
    
    Args:
        agents: 包含 agent_a 和 agent_b 的列表
        args: 命令行参数
        
    Returns:
        dict: 所有会话的设备事件记录
    """
    agent_a, agent_b = agents[0], agents[1]
    
    all_device_events = {
        "scenario": args.scenario if hasattr(args, 'scenario') else 'unknown',
        "sessions": {}
    }
    
    # 确定需要处理的会话数量
    num_sessions = args.num_sessions if hasattr(args, 'num_sessions') else 20
    
    for sess_id in range(1, num_sessions + 1):
        # 检查会话是否存在
        if 'session_%s' % sess_id not in agent_b:
            break
        
        # 检查是否已有设备事件且不需要覆盖
        if 'device_events' in agent_b and f'session_{sess_id}_device_events' in agent_b:
            if not hasattr(args, 'overwrite_events') or not args.overwrite_events:
                logging.info(f"Device events for session {sess_id} already exist, skipping")
                all_device_events['sessions'][f'session_{sess_id}'] = agent_b[f'session_{sess_id}_device_events']
                continue
        
        # 生成设备事件
        device_events = generate_device_events_for_session(agent_a, agent_b, args, sess_id)
        
        if device_events:
            all_device_events['sessions'][f'session_{sess_id}'] = device_events
            
            # 保存到 agent 对象
            agent_b[f'session_{sess_id}_device_events'] = device_events
    
    return all_device_events


def save_device_events(agents, args, device_events):
    """
    保存设备事件记录到文件。
    
    Args:
        agents: 包含 agent_a 和 agent_b 的列表
        args: 命令行参数
        device_events: 设备事件字典
        
    Returns:
        str: 保存的文件路径
    """
    output_dir = args.out_dir
    
    # 保存到 JSON 文件
    output_file = os.path.join(output_dir, 'device_events.json')
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(device_events, f, ensure_ascii=False, indent=2)
    
    logging.info(f"Device events saved to: {output_file}")
    return output_file


def get_device_events_summary(device_events):
    """
    获取设备事件的摘要信息。
    
    Args:
        device_events: 设备事件字典
        
    Returns:
        str: 摘要信息字符串
    """
    summary = []
    summary.append(f"场景: {device_events.get('scenario', 'unknown')}")
    
    sessions = device_events.get('sessions', {})
    summary.append(f"会话数量: {len(sessions)}")
    
    total_events = 0
    for session_name, session_data in sessions.items():
        events = session_data.get('annotated_events', [])
        total_events += len(events)
    
    summary.append(f"总事件数量: {total_events}")
    
    return "\n".join(summary)
