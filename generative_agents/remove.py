"""
已移除的代码备份文件。

此文件包含从 device_events_utils.py 中移除的未使用代码，以备后续可能需要使用。
这些代码当前没有被外部调用，可以根据需要重新引入。

注意：由于这些代码依赖于原始文件中的某些依赖（如 random, datetime, logging 等），
如果需要使用，请确保这些依赖已经正确导入。
"""

import os
import json
import logging
import random
from datetime import datetime

logging.basicConfig(level=logging.INFO)


# ==================== 暂未使用的函数和常量 ====================


def canonicalize_scenario(scenario):
    """
    规范化场景名称。
    
    注意：此函数目前仍被使用，请勿删除！
    
    Args:
        scenario: 场景名称
        
    Returns:
        str: 规范化后的场景名称
    """
    return scenario


def should_skip_scene_by_calendar(scenario, episode_date):
    """
    规则兜底下的日历约束：周末不生成工作日/上学日强绑定场景。
    LLM 路径会在状态描述阶段做更细判断。
    
    注意：此函数目前仍被使用，请勿删除！
    
    Args:
        scenario: 场景类型
        episode_date: episode日期
        
    Returns:
        bool: 是否应该跳过该场景
    """
    if episode_date.weekday() >= 5 and scenario in {'leave_work', 'family_return', 'child_return'}:
        return True
    return False


# 家庭画像驱动的噪声事件模板
HOUSEHOLD_NOISE_TEMPLATES = {
    # 根据家庭成员角色生成的噪声事件
    "grandpa": [
        {"event_type": "grandpa_sleeping", "predicate": "is", "object_id": "grandpa", 
         "description": "爷爷已睡", "probability": 0.6},
        {"event_type": "grandpa_watching_tv", "predicate": "is", "object_id": "grandpa", 
         "description": "爷爷在看电视", "probability": 0.3},
        {"event_type": "grandpa_exercise", "predicate": "is", "object_id": "grandpa", 
         "description": "爷爷在锻炼", "probability": 0.1},
        {"event_type": "medicine_taken", "predicate": "taken", "object_id": "medicine", 
         "description": "爷爷已服药", "probability": 0.4},
    ],
    "grandma": [
        {"event_type": "grandma_cooking", "predicate": "is", "object_id": "grandma", 
         "description": "奶奶在做饭", "probability": 0.4},
        {"event_type": "grandma_sewing", "predicate": "is", "object_id": "grandma", 
         "description": "奶奶在缝纫", "probability": 0.2},
        {"event_type": "grandma_napping", "predicate": "is", "object_id": "grandma", 
         "description": "奶奶在午睡", "probability": 0.3},
    ],
    "mom": [
        {"event_type": "mom_cooking", "predicate": "is", "object_id": "mom", 
         "description": "妈妈在厨房", "probability": 0.5},
        {"event_type": "mom_cleaning", "predicate": "is", "object_id": "mom", 
         "description": "妈妈在打扫", "probability": 0.2},
        {"event_type": "mom_watching_kid", "predicate": "is", "object_id": "mom", 
         "description": "妈妈在照看孩子", "probability": 0.2},
        {"event_type": "mom_on_phone", "predicate": "is", "object_id": "mom", 
         "description": "妈妈在打电话", "probability": 0.1},
    ],
    "child": [
        {"event_type": "child_studying", "predicate": "is", "object_id": "child", 
         "description": "孩子在写作业", "probability": 0.6},
        {"event_type": "child_playing", "predicate": "is", "object_id": "child", 
         "description": "孩子在玩耍", "probability": 0.2},
        {"event_type": "child_watching_tv", "predicate": "is", "object_id": "child", 
         "description": "孩子在看电视", "probability": 0.15},
        {"event_type": "child_eating", "predicate": "is", "object_id": "child", 
         "description": "孩子在吃东西", "probability": 0.1},
    ],
    "pet": [
        {"event_type": "pet_sleeping", "predicate": "is", "object_id": "pet", 
         "description": "宠物在睡觉", "probability": 0.5},
        {"event_type": "pet_playing", "predicate": "is", "object_id": "pet", 
         "description": "宠物在玩耍", "probability": 0.3},
        {"event_type": "pet_barking", "predicate": "is", "object_id": "pet", 
         "description": "宠物在叫", "probability": 0.1},
    ],
    
    # 根据设备状态生成的噪声事件
    "device_status": [
        {"event_type": "ac_already_on", "predicate": "is", "object_id": "ac_bedroom", 
         "description": "卧室空调已开", "probability": 0.2},
        {"event_type": "tv_unturned", "predicate": "is", "object_id": "tv_bedroom", 
         "description": "卧室电视未关", "probability": 0.15},
        {"event_type": "light_on", "predicate": "is", "object_id": "light_bedroom", 
         "description": "卧室灯已开", "probability": 0.1},
        {"event_type": "curtain_open", "predicate": "is", "object_id": "curtain_bedroom", 
         "description": "卧室窗帘开着", "probability": 0.1},
    ],
    
    # 根据时间和场景生成的环境噪声事件
    "environment": [
        {"event_type": "light_sensor_trigger", "predicate": "detected", "object_id": "sensor_light", 
         "description": "光照传感器触发", "probability": 0.2},
        {"event_type": "motion_detected", "predicate": "detected", "object_id": "motion_sensor", 
         "description": "移动传感器触发", "probability": 0.1},
        {"event_type": "door_bell", "predicate": "rang", "object_id": "door_bell", 
         "description": "门铃响起", "probability": 0.05},
        {"event_type": "delivery_arrival", "predicate": "arrived", "object_id": "delivery", 
         "description": "快递到达", "probability": 0.05},
    ],
}


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


# ==================== 以下代码需要完整的依赖才能使用 ====================


def generate_dynamic_noise_events(household_profile, scene, episode_date, day_offset):
    """
    根据家庭画像动态生成噪声事件。
    
    Args:
        household_profile: 家庭画像字典
        scene: 当前场景
        episode_date: episode日期
        day_offset: 天数偏移
        
    Returns:
        list: 动态生成的噪声事件列表
    """
    dynamic_noise_events = []
    
    # 获取家庭画像信息
    members = household_profile.get('members', {})
    relations = household_profile.get('relations', {})
    family_info = household_profile.get('family', {})
    role_responsibilities = household_profile.get('role_responsibilities', {})
    
    # 1. 根据家庭成员角色生成噪声事件
    for member_id, member_info in members.items():
        # 获取成员角色
        role = member_info.get('role', '')
        
        # 根据角色选择噪声事件模板
        role_noise_templates = HOUSEHOLD_NOISE_TEMPLATES.get(role, [])
        
        # 根据概率选择噪声事件
        for template in role_noise_templates:
            if random.random() < template.get('probability', 0.5):
                # 创建噪声事件副本并添加成员信息
                noise_event = template.copy()
                noise_event['subject_id'] = member_id
                dynamic_noise_events.append(noise_event)
    
    # 2. 如果家庭有宠物，添加宠物相关噪声
    has_pet = family_info.get('has_pet', False) or any(
        member.get('type') == 'pet' for member in members.values()
    )
    
    if has_pet:
        pet_templates = HOUSEHOLD_NOISE_TEMPLATES.get('pet', [])
        for template in pet_templates:
            if random.random() < template.get('probability', 0.5):
                noise_event = template.copy()
                noise_event['subject_id'] = 'pet'
                dynamic_noise_events.append(noise_event)
    
    # 3. 根据角色职责生成噪声事件
    for member_id, responsibilities in role_responsibilities.items():
        for responsibility in responsibilities:
            if random.random() < 0.1:  # 10%概率生成职责相关噪声
                responsibility_event = generate_responsibility_event(member_id, responsibility)
                if responsibility_event:
                    dynamic_noise_events.append(responsibility_event)
    
    # 4. 根据时间特征生成环境噪声
    hour = datetime.now().hour
    if hour < 7 or hour >= 22:
        # 早晚时段更可能有环境噪声
        env_templates = HOUSEHOLD_NOISE_TEMPLATES.get('environment', [])
        for template in env_templates:
            if random.random() < template.get('probability', 0.5) * 1.5:  # 增加50%概率
                noise_event = template.copy()
                dynamic_noise_events.append(noise_event)
    else:
        env_templates = HOUSEHOLD_NOISE_TEMPLATES.get('environment', [])
        for template in env_templates:
            if random.random() < template.get('probability', 0.5):
                noise_event = template.copy()
                dynamic_noise_events.append(noise_event)
    
    # 5. 根据场景特性生成特定噪声
    if scene == 'family_return':
        # 下班回家场景可能有额外的厨房相关噪声
        if random.random() < 0.3:
            dynamic_noise_events.append({
                "event_type": "cooking_smell", "predicate": "detected", 
                "object_id": "kitchen_sensor", "description": "厨房飘来饭菜香",
                "probability": 0.3
            })
    
    # 去重（避免重复的噪声事件）
    unique_events = []
    seen_events = set()
    for event in dynamic_noise_events:
        event_key = (event.get('event_type'), event.get('object_id'))
        if event_key not in seen_events:
            seen_events.add(event_key)
            unique_events.append(event)
    
    return unique_events


def generate_responsibility_event(member_id, responsibility):
    """
    根据角色职责生成噪声事件。
    
    Args:
        member_id: 成员ID
        responsibility: 职责描述
        
    Returns:
        dict: 噪声事件，或None
    """
    # 根据职责类型生成不同的事件
    if '做饭' in responsibility or '烹饪' in responsibility:
        return {
            "event_type": "cooking", "predicate": "is", 
            "object_id": member_id, "description": f"{member_id}在做饭",
            "subject_id": member_id, "probability": 0.3
        }
    elif '打扫' in responsibility or '清洁' in responsibility:
        return {
            "event_type": "cleaning", "predicate": "is", 
            "object_id": member_id, "description": f"{member_id}在打扫卫生",
            "subject_id": member_id, "probability": 0.2
        }
    elif '照顾' in responsibility or '看护' in responsibility:
        return {
            "event_type": "caregiving", "predicate": "is", 
            "object_id": member_id, "description": f"{member_id}在照顾家人",
            "subject_id": member_id, "probability": 0.2
        }
    elif '采购' in responsibility or '购物' in responsibility:
        return {
            "event_type": "shopping", "predicate": "is", 
            "object_id": member_id, "description": f"{member_id}在购物",
            "subject_id": member_id, "probability": 0.1
        }
    
    return None


# ==================== 以下代码需要完整的 DEVICE_EVENTS_GENERATION_PROMPT 和其他依赖 ====================


def generate_device_events_for_session(agent_a, agent_b, args, sess_id):
    """
    为单个会话生成设备事件记录。
    
    根据对话内容和场景，使用模型生成设备行为记录。
    
    注意：此函数需要以下依赖：
    - DEVICE_EVENTS_GENERATION_PROMPT 常量
    - get_run_json_trials 函数
    - canonicalize_scenario 函数
    - get_dialogue_content 函数
    - get_user_devices_info 函数
    
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
    scenario = canonicalize_scenario(args.scenario if hasattr(args, 'scenario') else 'leave_work')
    scenario_config = None
    
    if hasattr(args, 'scenario_file') and os.path.exists(args.scenario_file):
        with open(args.scenario_file, 'r', encoding='utf-8') as f:
            scenarios_data = json.load(f)
            scenarios = scenarios_data.get('scenarios', {})
            scenario_config = scenarios.get(scenario, {}) or scenarios.get('male_leave_work', {})
    
    scene_type = scenario
    scene_desc = scenario_config.get('description', scenario) if scenario_config else scenario
    
    # 获取会话时间
    session_datetime = ""
    if 'session_%s_date_time' % sess_id in agent_a:
        session_datetime = agent_a['session_%s_date_time' % sess_id]
    
    # 构建 prompt（需要 DEVICE_EVENTS_GENERATION_PROMPT）
    # 注意：此函数需要完整的 DEVICE_EVENTS_GENERATION_PROMPT 常量
    # 如果需要使用，请从 device_events_utils.py 中恢复该常量
    # prompt = DEVICE_EVENTS_GENERATION_PROMPT.format(
    #     scene_type=scene_type,
    #     scene_desc=scene_desc,
    #     user_devices=user_devices_info,
    #     dialogue_content=dialogue_content
    # )
    
    logging.info(f"Generating device events for session {sess_id} with scenario: {scene_type}")
    
    # 检查 LLM 是否可用
    run_json_trials_func = None
    try:
        from global_methods import run_json_trials
        run_json_trials_func = run_json_trials
    except ImportError:
        logging.warning("LLM not available, skipping device events generation")
        return None
    
    # 调用模型生成设备事件
    # 注意：由于 prompt 被注释，此功能暂不可用
    # 如果需要使用，请取消上面的 prompt 构建代码的注释
    # try:
    #     result = run_json_trials_func(
    #         prompt, 
    #         num_gen=1, 
    #         num_tokens_request=2000, 
    #         use_16k=False
    #     )
    #     
    #     # 确保输出格式正确
    #     if isinstance(result, dict) and 'annotated_events' in result:
    #         # 添加 episode_id 和 scene 信息
    #         result['episode_id'] = f"ep_{sess_id:03d}"
    #         result['scene'] = scene_desc
    #         if 'confidence' not in result:
    #             result['confidence'] = 0.85
    #         
    #         logging.info(f"Generated {len(result.get('annotated_events', []))} device events for session {sess_id}")
    #         return result
    #     else:
    #         logging.warning(f"Unexpected result format from model: {type(result)}")
    #         return None
    # except Exception as e:
    #     logging.error(f"Error generating device events for session {sess_id}: {e}")
    #     return None
    
    return None
