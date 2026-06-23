"""
设备事件生成相关工具函数。

根据场景和对话内容，使用模型生成设备行为记录。
支持连续多日场景事件生成（episodes）。
"""

import os
import json
import logging
from datetime import datetime, timedelta, date
import random

# 延迟导入 LLM 相关函数，避免在不需要时导入 openai
_run_json_trials = None

def get_run_json_trials():
    """延迟导入 run_json_trials 函数"""
    global _run_json_trials
    if _run_json_trials is None:
        try:
            from global_methods import run_json_trials
            _run_json_trials = run_json_trials
        except ImportError as e:
            logging.warning(f"Failed to import run_json_trials: {e}")
            _run_json_trials = None
    return _run_json_trials

logging.basicConfig(level=logging.INFO)

# ==================== 场景模板定义 ====================

SCENE_TEMPLATES = {
    "family_return": {
        "name": "家庭成员下班回家",
        "description": "男主人下班回家，开门进入，进行一系列居家活动",
        "default_subject": "dad",
        "default_home": "home_1",
        "time_window": {
            "normal": {"start": "17:00", "end": "22:30"},
            "late": {"start": "23:00", "end": "01:00"}
        },
        "core_events": [
            # 核心回家行为
            {"event_type": "enter_home", "predicate": "entered", "object_id": "door_main", 
             "description": "开门进入"},
            {"event_type": "light_on", "predicate": "activated", "object_id": "light_hallway", 
             "description": "打开玄关灯"},
            {"event_type": "light_on", "predicate": "activated", "object_id": "light_living_room", 
             "description": "打开客厅灯"},
            {"event_type": "ac_on", "predicate": "activated", "object_id": "ac_living_room", 
             "description": "打开客厅空调"},
            {"event_type": "tv_on", "predicate": "activated", "object_id": "tv_living_room", 
             "description": "打开电视"},
            {"event_type": "curtain_close", "predicate": "closed", "object_id": "curtain_living_room", 
             "description": "关闭窗帘"},
            {"event_type": "light_on", "predicate": "activated", "object_id": "light_bedroom", 
             "description": "打开卧室灯"},
            {"event_type": "door_lock", "predicate": "locked", "object_id": "door_main", 
             "description": "锁门"}
        ],
        "noise_events": [
            # 噪声事件
            {"event_type": "grandpa_sleeping", "predicate": "is", "object_id": "grandpa", 
             "description": "爷爷已睡"},
            {"event_type": "child_studying", "predicate": "is", "object_id": "child", 
             "description": "孩子在写作业"},
            {"event_type": "mom_cooking", "predicate": "is", "object_id": "mom", 
             "description": "妈妈在厨房"},
            {"event_type": "ac_already_on", "predicate": "is", "object_id": "ac_bedroom", 
             "description": "卧室空调已开"},
            {"event_type": "tv_unturned", "predicate": "is", "object_id": "tv_bedroom", 
             "description": "卧室电视未关"},
            {"event_type": "light_sensor_trigger", "predicate": "detected", "object_id": "sensor_light", 
             "description": "光照传感器触发"}
        ]
    },
    "male_leave_work": {
        "name": "男主人上班离家",
        "description": "男主人早上出门上班前的一系列准备活动",
        "default_subject": "dad",
        "default_home": "home_1",
        "time_window": {
            "normal": {"start": "07:00", "end": "09:00"}
        },
        "core_events": [
            {"event_type": "wake_up", "predicate": "woke_up", "object_id": "dad", 
             "description": "起床"},
            {"event_type": "light_on", "predicate": "activated", "object_id": "light_bedroom", 
             "description": "打开卧室灯"},
            {"event_type": "light_on", "predicate": "activated", "object_id": "light_bathroom", 
             "description": "打开卫生间灯"},
            {"event_type": "ac_off", "predicate": "deactivated", "object_id": "ac_bedroom", 
             "description": "关闭卧室空调"},
            {"event_type": "door_open", "predicate": "opened", "object_id": "door_main", 
             "description": "开门"},
            {"event_type": "light_off", "predicate": "deactivated", "object_id": "light_hallway", 
             "description": "关闭玄关灯"},
            {"event_type": "door_lock", "predicate": "locked", "object_id": "door_main", 
             "description": "锁门"}
        ],
        "noise_events": [
            {"event_type": "alarm_trigger", "predicate": "triggered", "object_id": "alarm_clock", 
             "description": "闹钟响起"},
            {"event_type": "coffee_making", "predicate": "making", "object_id": "coffee_machine", 
             "description": "咖啡机工作"},
            {"event_type": "child_still_sleeping", "predicate": "is", "object_id": "child", 
             "description": "孩子还在睡觉"},
            {"event_type": "grandpa_exercise", "predicate": "is", "object_id": "grandpa", 
             "description": "爷爷在锻炼"}
        ]
    },
    "child_return": {
        "name": "小孩放学回家",
        "description": "小孩放学回家后的活动",
        "default_subject": "child",
        "default_home": "home_1",
        "time_window": {
            "normal": {"start": "16:30", "end": "18:30"}
        },
        "core_events": [
            {"event_type": "enter_home", "predicate": "entered", "object_id": "door_main", 
             "description": "开门进入"},
            {"event_type": "backpack_drop", "predicate": "dropped", "object_id": "backpack", 
             "description": "放下书包"},
            {"event_type": "light_on", "predicate": "activated", "object_id": "light_study", 
             "description": "打开书房灯"},
            {"event_type": "desk_setup", "predicate": "started", "object_id": "desk", 
             "description": "开始写作业"}
        ],
        "noise_events": [
            {"event_type": "snack_time", "predicate": "eating", "object_id": "snack", 
             "description": "吃零食"},
            {"event_type": "tv_on", "predicate": "activated", "object_id": "tv_kids", 
             "description": "打开儿童频道"},
            {"event_type": "grandpa_watching", "predicate": "is", "object_id": "grandpa", 
             "description": "爷爷在看电视"}
        ]
    },
    "elderly_outdoor": {
        "name": "老人独自外出",
        "description": "老人准备外出活动",
        "default_subject": "grandpa",
        "default_home": "home_1",
        "time_window": {
            "normal": {"start": "08:30", "end": "11:30"}
        },
        "core_events": [
            {"event_type": "door_open", "predicate": "opened", "object_id": "door_main", 
             "description": "开门"},
            {"event_type": "door_close", "predicate": "closed", "object_id": "door_main", 
             "description": "关门"},
            {"event_type": "leave_home", "predicate": "left", "object_id": "home_1", 
             "description": "离开家"}
        ],
        "noise_events": [
            {"event_type": "walking_stick", "predicate": "using", "object_id": "walking_stick", 
             "description": "使用拐杖"},
            {"event_type": "weather_check", "predicate": "checked", "object_id": "weather", 
             "description": "查看天气"},
            {"event_type": "medicine_taken", "predicate": "taken", "object_id": "medicine", 
             "description": "已服药"}
        ]
    },
    "visitor_arrival": {
        "name": "访客到家",
        "description": "访客到达家中",
        "default_subject": "visitor",
        "default_home": "home_1",
        "time_window": {
            "normal": {"start": "10:00", "end": "21:00"}
        },
        "core_events": [
            {"event_type": "bell_ring", "predicate": "rang", "object_id": "door_bell", 
             "description": "门铃响起"},
            {"event_type": "door_open", "predicate": "opened", "object_id": "door_main", 
             "description": "开门"},
            {"event_type": "visitor_enter", "predicate": "entered", "object_id": "visitor", 
             "description": "访客进入"}
        ],
        "noise_events": [
            {"event_type": "dog_barking", "predicate": "barking", "object_id": "dog", 
             "description": "狗在叫"},
            {"event_type": "child_excited", "predicate": "is", "object_id": "child", 
             "description": "孩子很兴奋"},
            {"event_type": "tea_prepare", "predicate": "preparing", "object_id": "tea", 
             "description": "准备茶水"}
        ]
    },
    "all_leave_arm": {
        "name": "全员离家布防",
        "description": "全员离家时启动安防模式",
        "default_subject": "dad",
        "default_home": "home_1",
        "time_window": {
            "normal": {"start": "08:30", "end": "09:30"}
        },
        "core_events": [
            {"event_type": "light_off_all", "predicate": "deactivated", "object_id": "all_lights", 
             "description": "关闭所有灯光"},
            {"event_type": "ac_off_all", "predicate": "deactivated", "object_id": "all_ac", 
             "description": "关闭所有空调"},
            {"event_type": "security_on", "predicate": "activated", "object_id": "security_system", 
             "description": "启动安防系统"},
            {"event_type": "door_lock", "predicate": "locked", "object_id": "door_main", 
             "description": "锁门"},
            {"event_type": "window_close", "predicate": "closed", "object_id": "all_windows", 
             "description": "关闭所有窗户"}
        ],
        "noise_events": [
            {"event_type": "pet_feed", "predicate": "fed", "object_id": "pet", 
             "description": "喂宠物"},
            {"event_type": "plant_water", "predicate": "watered", "object_id": "plants", 
             "description": "浇水"},
            {"event_type": "garbage_take", "predicate": "taken", "object_id": "garbage", 
             "description": "倒垃圾"}
        ]
    },
    "anomaly_detection": {
        "name": "异常活动检测",
        "description": "检测到异常活动时AI助手与用户的对话",
        "default_subject": "system",
        "default_home": "home_1",
        "time_window": {
            "normal": {"start": "00:00", "end": "24:00"}
        },
        "core_events": [
            {"event_type": "motion_detected", "predicate": "detected", "object_id": "motion_sensor", 
             "description": "检测到移动"},
            {"event_type": "camera_record", "predicate": "recording", "object_id": "security_camera", 
             "description": "摄像头录制"},
            {"event_type": "alert_send", "predicate": "sent", "object_id": "alert", 
             "description": "发送警报"}
        ],
        "noise_events": [
            {"event_type": "pet_movement", "predicate": "is", "object_id": "pet", 
             "description": "宠物活动"},
            {"event_type": "wind_blowing", "predicate": "is", "object_id": "window", 
             "description": "风吹动窗户"},
            {"event_type": "delivery_arrival", "predicate": "arrived", "object_id": "delivery", 
             "description": "快递到达"}
        ]
    }
}

# 家庭成员映射
PERSON_ID_MAPPING = {
    "dad": {"name": "父亲", "role": "男主人", "age_range": "35-50"},
    "mom": {"name": "母亲", "role": "女主人", "age_range": "35-50"},
    "grandpa": {"name": "爷爷", "role": "祖父", "age_range": "65-85"},
    "grandma": {"name": "奶奶", "role": "祖母", "age_range": "65-85"},
    "child": {"name": "孩子", "role": "子女", "age_range": "6-18"},
    "visitor": {"name": "访客", "role": "访客", "age_range": "unknown"}
}

# 设备状态机
DEVICE_STATES = {
    "door_main": ["open", "closed", "locked"],
    "door_bedroom": ["open", "closed", "locked"],
    "light_hallway": ["on", "off"],
    "light_living_room": ["on", "off"],
    "light_bedroom": ["on", "off"],
    "light_study": ["on", "off"],
    "light_bathroom": ["on", "off"],
    "ac_living_room": ["on", "off"],
    "ac_bedroom": ["on", "off"],
    "tv_living_room": ["on", "off"],
    "tv_bedroom": ["on", "off"],
    "tv_kids": ["on", "off"],
    "curtain_living_room": ["open", "closed"],
    "curtain_bedroom": ["open", "closed"],
    "security_system": ["armed", "disarmed"],
    "door_bell": ["ringing", "silent"],
    "motion_sensor": ["detected", "clear"],
    "security_camera": ["recording", "idle"],
    "coffee_machine": ["brewing", "idle"]
}

DEVICE_TRANSITIONS = {
    # (from_state, event, to_state)
    ("closed", "opened", "open"),
    ("open", "closed", "closed"),
    ("closed", "locked", "locked"),
    ("locked", "opened", "open"),
    ("off", "activated", "on"),
    ("on", "deactivated", "off"),
    ("open", "closed", "closed"),
    ("closed", "opened", "open"),
    ("disarmed", "activated", "armed"),
    ("armed", "deactivated", "disarmed"),
    ("idle", "recording", "recording"),
    ("recording", "idle", "idle"),
    ("idle", "brewing", "brewing"),
    ("brewing", "idle", "idle"),
    ("clear", "detected", "detected"),
    ("detected", "clear", "clear"),
    ("silent", "ringing", "ringing"),
    ("ringing", "silent", "silent")
}


# ==================== LLM 单日 Episode 生成 Prompt 模板 ====================

LLM_EPISODE_GENERATION_PROMPT = """你是一个智能家居系统分析师。根据给定的家庭画像和场景，生成当天的家庭状态描述和设备事件记录。

## 场景信息
场景类型: {scenario}
场景描述: {scenario_desc}
日期: {episode_date}

## 家庭成员
{members_info}

## 可控设备
{devices_info}

## 随机抽样上下文
本日重点人物: {sampled_persons}
本日重点设备: {sampled_devices}

## 任务要求
1. 首先生成当天的家庭状态自然语言描述（daily_state_description），描述家庭在当前时间点的状态，包括：
   - 家庭成员的位置和活动状态
   - 主要设备的当前状态
   - 环境氛围（如安静、热闹、温馨等）
   - 任何特殊情况（如有人加班、有访客等）

2. 然后基于家庭状态描述，生成围绕"男主人下班回家"场景的结构化设备事件：
   - 核心事件：开门进入、回到玄关、开灯、调空调、锁门、进入客厅/卧室等
   - 噪声事件：来自家庭状态，如家人在厨房、孩子写作业、老人休息、某个设备已开、传感器触发等
   - 事件数量：核心事件 2-5 条，噪声事件 0-3 条

3. 事件必须围绕"男主人下班回家"场景，所有设备 ID 必须来自可控设备列表

4. 每个事件包含：
   - event: subject_id（人物ID）、predicate（操作类型）、object_id（对象ID）、attributes（事件类型和描述）
   - state_snapshot: timestamp（时间戳）、persons（人物状态）、devices（设备状态）、space_occupancy（空间占用）

## 输出格式
请严格按照以下 JSON 格式输出，不要包含其他解释文字：

{{
    "daily_state_description": "当天的家庭状态自然语言描述，50-100字",
    "sampled_context": {{
        "persons": ["本日重点人物ID列表"],
        "devices": ["本日重点设备ID列表"]
    }},
    "annotated_events": [
        {{
            "event": {{
                "subject_id": "dad",
                "predicate": "entered",
                "object_id": "door_main",
                "attributes": {{
                    "event_type": "enter_home",
                    "description": "开门进入"
                }}
            }},
            "state_snapshot": {{
                "timestamp": "2022-03-16T18:30:00+08:00",
                "persons": {{
                    "dad": {{"status": "entering", "location": "entrance"}},
                    "mom": {{"status": "at_home", "location": "kitchen"}},
                    "child": {{"status": "at_home", "location": "study"}}
                }},
                "devices": {{
                    "door_main": {{"state": "open"}},
                    "light_hallway": {{"state": "off"}},
                    "ac_living_room": {{"state": "off"}}
                }},
                "space_occupancy": {{
                    "entrance": ["dad"],
                    "kitchen": ["mom"],
                    "study": ["child"],
                    "living_room": [],
                    "bedroom": []
                }}
            }}
        }}
    ]
}}

## 重要约束
- timestamp 使用 ISO8601 格式，时间必须连续递增
- 所有设备 ID 必须来自可控设备列表
- state_snapshot 必须包含 persons、devices、space_occupancy 三个字段
- 人物 ID 必须来自家庭成员列表
- 事件之间需要有因果关系和时间顺序
- 输出必须是合法的 JSON 格式

请生成家庭状态描述和设备事件记录："""

# ==================== 设备事件生成 Prompt 模板 ====================

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
    
    # 检查 LLM 是否可用
    run_json_trials_func = get_run_json_trials()
    if run_json_trials_func is None:
        logging.warning("LLM not available, skipping device events generation")
        return None
    
    # 调用模型生成设备事件
    try:
        result = run_json_trials_func(
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


# ==================== 连续多日设备事件生成功能 ====================

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


def load_household_profile(household_profile_path):
    """
    加载家庭画像文件。
    
    Args:
        household_profile_path: 家庭画像文件路径
        
    Returns:
        dict: 家庭画像字典，如果文件不存在返回空字典
    """
    if os.path.exists(household_profile_path):
        try:
            with open(household_profile_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logging.warning(f"Failed to load household profile: {e}")
    return {}


def get_scene_templates(device_file=None):
    """
    获取场景模板。
    
    Args:
        device_file: 设备配置文件路径（可选）
        
    Returns:
        dict: 场景模板字典
    """
    # 基础场景模板
    templates = SCENE_TEMPLATES.copy()
    
    # 如果提供了设备文件，加载设备信息增强模板
    if device_file and os.path.exists(device_file):
        try:
            with open(device_file, 'r', encoding='utf-8') as f:
                device_config = json.load(f)
                # 可以在这里根据设备配置增强场景模板
                templates['device_config'] = device_config
        except Exception as e:
            logging.warning(f"Failed to load device config: {e}")
    
    return templates


def generate_single_day_episode_llm(scenario, episode_date, day_offset, template,
                                   household_profile, person_ids, device_file=None,
                                   max_retries=3):
    """
    使用 LLM 生成单日的设备事件episode。
    
    Args:
        scenario: 场景类型
        episode_date: episode日期
        day_offset: 天数偏移（从开始算起）
        template: 场景模板
        household_profile: 家庭画像
        person_ids: 可用的人员ID列表
        device_file: 设备配置文件路径（可选）
        max_retries: 最大重试次数
        
    Returns:
        dict: episode字典，包含 daily_state_description 和 annotated_events
    """
    # 检查 LLM 是否可用
    run_json_trials_func = get_run_json_trials()
    if run_json_trials_func is None:
        logging.warning("LLM not available, skipping LLM generation")
        return None
    
    # 获取默认参数
    default_subject = template.get('default_subject', 'dad')
    default_home = template.get('default_home', 'home_1')
    time_window = template.get('time_window', {})
    
    # 确定时间窗口（是否是晚归日）
    is_late_day = is_late_work_day(day_offset, num_days=7)
    time_range = time_window.get('late' if is_late_day else 'normal', time_window.get('normal'))
    
    # 准备家庭成员信息
    members_info = format_members_info(household_profile, person_ids)
    
    # 准备设备信息
    devices_info = format_devices_info(device_file)
    
    # 随机抽样部分人物和设备
    sampled_persons = random.sample(person_ids, min(3, len(person_ids)))
    available_devices = get_available_device_ids(device_file)
    sampled_devices = random.sample(available_devices, min(5, len(available_devices)))
    
    # 构建 prompt
    prompt = LLM_EPISODE_GENERATION_PROMPT.format(
        scenario=scenario,
        scenario_desc=template.get('description', ''),
        episode_date=episode_date.strftime('%Y-%m-%d'),
        members_info=members_info,
        devices_info=devices_info,
        sampled_persons=', '.join(sampled_persons),
        sampled_devices=', '.join(sampled_devices)
    )
    
    # 使用 LLM 生成 episode
    for attempt in range(max_retries):
        try:
            logging.info(f"Generating episode for {episode_date} (attempt {attempt + 1}/{max_retries})")
            
            # 调用 LLM
            llm_result = run_json_trials_func(prompt, num_gen=1, num_tokens_request=2000, temperature=0.8)
            
            if not llm_result:
                raise ValueError("LLM returned empty result")
            
            # 验证结果
            validated_result = validate_llm_episode_result(
                llm_result, 
                scenario, 
                episode_date, 
                default_subject, 
                default_home,
                person_ids,
                available_devices,
                time_range
            )
            
            # 添加 sampled_context
            validated_result['sampled_context'] = {
                'persons': sampled_persons,
                'devices': sampled_devices
            }
            
            logging.info(f"Successfully generated episode for {episode_date}")
            return validated_result
            
        except Exception as e:
            logging.warning(f"Attempt {attempt + 1} failed for {episode_date}: {e}")
            if attempt == max_retries - 1:
                logging.error(f"All {max_retries} attempts failed for {episode_date}, falling back to rule-based generation")
                return None
    
    return None


def format_members_info(household_profile, person_ids):
    """
    格式化家庭成员信息。
    
    Args:
        household_profile: 家庭画像
        person_ids: 人员ID列表
        
    Returns:
        str: 格式化的家庭成员信息字符串
    """
    members = household_profile.get('members', {})
    info_lines = []
    
    for person_id in person_ids:
        if person_id in members:
            member = members[person_id]
            name = member.get('name', person_id)
            role = member.get('role', '')
            age = member.get('age', '')
            info_lines.append(f"- {person_id}: {name}, 角色: {role}, 年龄: {age}")
        else:
            # 使用默认映射
            if person_id in PERSON_ID_MAPPING:
                mapping = PERSON_ID_MAPPING[person_id]
                info_lines.append(f"- {person_id}: {mapping['name']}, 角色: {mapping['role']}, 年龄范围: {mapping['age_range']}")
    
    return '\n'.join(info_lines) if info_lines else "- dad: 父亲, 角色: 男主人, 年龄范围: 35-50\n- mom: 母亲, 角色: 女主人, 年龄范围: 35-50"


def format_devices_info(device_file):
    """
    格式化设备信息。
    
    Args:
        device_file: 设备配置文件路径
        
    Returns:
        str: 格式化的设备信息字符串
    """
    if not device_file or not os.path.exists(device_file):
        # 返回默认设备列表
        default_devices = [
            "door_main: 主门（智能门锁）",
            "light_hallway: 玄关灯",
            "light_living_room: 客厅灯",
            "light_bedroom: 卧室灯",
            "ac_living_room: 客厅空调",
            "tv_living_room: 客厅电视",
            "curtain_living_room: 客厅窗帘"
        ]
        return '\n'.join(default_devices)
    
    try:
        with open(device_file, 'r', encoding='utf-8') as f:
            devices_config = json.load(f)
        
        info_lines = []
        device_categories = devices_config.get('device_categories', {})
        
        for category_name, category_data in device_categories.items():
            devices = category_data.get('devices', {})
            for device_id, device_info in devices.items():
                name = device_info.get('name', device_id)
                description = device_info.get('description', '')
                info_lines.append(f"- {device_id}: {name} ({description})")
        
        return '\n'.join(info_lines) if info_lines else "- door_main: 主门\n- light_hallway: 玄关灯"
        
    except Exception as e:
        logging.warning(f"Failed to load device config: {e}, using default devices")
        return "- door_main: 主门\n- light_hallway: 玄关灯"


def get_available_device_ids(device_file):
    """
    获取可用的设备ID列表。
    
    Args:
        device_file: 设备配置文件路径
        
    Returns:
        list: 设备ID列表
    """
    if not device_file or not os.path.exists(device_file):
        # 返回默认设备ID列表
        return ['door_main', 'light_hallway', 'light_living_room', 'light_bedroom', 
                'ac_living_room', 'tv_living_room', 'curtain_living_room']
    
    try:
        with open(device_file, 'r', encoding='utf-8') as f:
            devices_config = json.load(f)
        
        device_ids = []
        device_categories = devices_config.get('device_categories', {})
        
        for category_data in device_categories.values():
            devices = category_data.get('devices', {})
            device_ids.extend(devices.keys())
        
        return device_ids if device_ids else ['door_main', 'light_hallway']
        
    except Exception as e:
        logging.warning(f"Failed to load device IDs: {e}, using default devices")
        return ['door_main', 'light_hallway']


def validate_llm_episode_result(result, scenario, episode_date, default_subject, 
                                 default_home, person_ids, available_devices, time_range):
    """
    验证 LLM 生成的 episode 结果。
    
    Args:
        result: LLM 返回的结果
        scenario: 场景类型
        episode_date: episode日期
        default_subject: 默认主体ID
        default_home: 默认家庭ID
        person_ids: 可用的人员ID列表
        available_devices: 可用的设备ID列表
        time_range: 时间范围
        
    Returns:
        dict: 验证后的 episode
        
    Raises:
        ValueError: 验证失败时抛出异常
    """
    # 检查必需字段
    if 'daily_state_description' not in result:
        raise ValueError("Missing daily_state_description")
    
    if 'annotated_events' not in result:
        raise ValueError("Missing annotated_events")
    
    annotated_events = result['annotated_events']
    
    # 检查事件数量
    if len(annotated_events) < 2 or len(annotated_events) > 8:
        raise ValueError(f"Invalid number of events: {len(annotated_events)}, expected 2-8")
    
    # 验证每个事件
    prev_timestamp = None
    for i, event_data in enumerate(annotated_events):
        # 检查 event 字段
        if 'event' not in event_data:
            raise ValueError(f"Event {i} missing 'event' field")
        
        event = event_data['event']
        
        # 检查必需的 event 字段
        if 'subject_id' not in event:
            raise ValueError(f"Event {i} missing subject_id")
        if 'predicate' not in event:
            raise ValueError(f"Event {i} missing predicate")
        if 'object_id' not in event:
            raise ValueError(f"Event {i} missing object_id")
        
        # 验证 subject_id 在可用人员列表中
        if event['subject_id'] not in person_ids:
            raise ValueError(f"Event {i} has invalid subject_id: {event['subject_id']}")
        
        # 验证 object_id 在可用设备列表中
        if event['object_id'] not in available_devices:
            raise ValueError(f"Event {i} has invalid object_id: {event['object_id']}")
        
        # 检查 state_snapshot 字段
        if 'state_snapshot' not in event_data:
            raise ValueError(f"Event {i} missing state_snapshot")
        
        snapshot = event_data['state_snapshot']
        
        # 检查必需的 snapshot 字段
        if 'timestamp' not in snapshot:
            raise ValueError(f"Event {i} missing timestamp")
        if 'persons' not in snapshot:
            raise ValueError(f"Event {i} missing persons in state_snapshot")
        if 'devices' not in snapshot:
            raise ValueError(f"Event {i} missing devices in state_snapshot")
        if 'space_occupancy' not in snapshot:
            raise ValueError(f"Event {i} missing space_occupancy in state_snapshot")
        
        # 验证时间戳格式和递增性
        try:
            current_timestamp = datetime.fromisoformat(snapshot['timestamp'].replace('+08:00', ''))
            if prev_timestamp and current_timestamp <= prev_timestamp:
                raise ValueError(f"Event {i} timestamp is not increasing: {snapshot['timestamp']}")
            prev_timestamp = current_timestamp
        except ValueError as e:
            raise ValueError(f"Event {i} has invalid timestamp format: {e}")
    
    # 构建完整的 episode
    episode = {
        "episode_id": f"{scenario}_{episode_date.strftime('%Y%m%d')}",
        "home_id": default_home,
        "scene": scenario,
        "subject_id": default_subject,
        "confidence": round(0.85 + random.random() * 0.1, 2),
        "date": episode_date.isoformat(),
        "daily_state_description": result['daily_state_description'],
        "annotated_events": annotated_events
    }
    
    return episode


def generate_scenario_device_episodes(scenario, num_days=7, household_profile=None, 
                                      scene_templates=None, device_file=None, use_llm=True):
    """
    生成连续多日的设备事件episodes。
    
    Args:
        scenario: 场景类型（如 'family_return'）
        num_days: 生成天数，默认7天
        household_profile: 家庭画像字典（可选）
        scene_templates: 场景模板字典（可选）
        device_file: 设备配置文件路径（可选）
        use_llm: 是否使用LLM生成（默认True）
        
    Returns:
        list: episodes列表，每个episode包含annotated_events
    """
    if scene_templates is None:
        scene_templates = SCENE_TEMPLATES
    
    if household_profile is None:
        household_profile = {}
    
    # 获取场景模板
    template = scene_templates.get(scenario)
    if not template:
        logging.error(f"Unknown scenario: {scenario}")
        return []
    
    # 获取默认参数
    default_subject = template.get('default_subject', 'dad')
    default_home = template.get('default_home', 'home_1')
    core_events = template.get('core_events', [])
    noise_events = template.get('noise_events', [])
    time_window = template.get('time_window', {})
    
    episodes = []
    
    # 获取家庭画像信息
    members = household_profile.get('members', {})
    relations = household_profile.get('relations', {})
    family_info = household_profile.get('family', {})
    
    # 获取家庭成员映射（结合家庭画像和默认映射）
    person_ids = get_person_ids_from_household(household_profile)
    
    # 确定起始日期（从今天往前推num_days天）
    start_date = datetime.now().date() - timedelta(days=num_days - 1)
    
    # 为每一天生成一个episode
    for day_offset in range(num_days):
        episode_date = start_date + timedelta(days=day_offset)
        
        if use_llm:
            # 使用 LLM 生成 episode
            episode = generate_single_day_episode_llm(
                scenario=scenario,
                episode_date=episode_date,
                day_offset=day_offset,
                template=template,
                household_profile=household_profile,
                person_ids=person_ids,
                device_file=device_file
            )
            
            # 如果 LLM 生成失败，回退到规则模板生成
            if not episode:
                logging.warning(f"LLM generation failed for {episode_date}, falling back to rule-based generation")
                episode = generate_single_day_episode_rule_based(
                    scenario=scenario,
                    episode_date=episode_date,
                    day_offset=day_offset,
                    template=template,
                    core_events=core_events,
                    noise_events=noise_events,
                    time_window=time_window,
                    default_subject=default_subject,
                    default_home=default_home,
                    household_profile=household_profile,
                    person_ids=person_ids
                )
        else:
            # 使用规则模板生成
            episode = generate_single_day_episode_rule_based(
                scenario=scenario,
                episode_date=episode_date,
                day_offset=day_offset,
                template=template,
                core_events=core_events,
                noise_events=noise_events,
                time_window=time_window,
                default_subject=default_subject,
                default_home=default_home,
                household_profile=household_profile,
                person_ids=person_ids
            )
        
        if episode:
            episodes.append(episode)
    
    logging.info(f"Generated {len(episodes)} episodes for scenario '{scenario}'")
    return episodes


def generate_single_day_episode_rule_based(scenario, episode_date, day_offset, template,
                                           core_events, noise_events, time_window,
                                           default_subject, default_home,
                                           household_profile, person_ids):
    """
    使用规则模板生成单日的设备事件episode（原有逻辑）。
    
    Args:
        scenario: 场景类型
        episode_date: episode日期
        day_offset: 天数偏移（从开始算起）
        template: 场景模板
        core_events: 核心事件列表
        noise_events: 噪声事件列表
        time_window: 时间窗口配置
        default_subject: 默认主体ID
        default_home: 默认家庭ID
        household_profile: 家庭画像
        person_ids: 可用的人员ID列表
        
    Returns:
        dict: episode字典
    """
    # 确定时间窗口（是否是晚归日）
    is_late_day = is_late_work_day(day_offset, num_days=7)
    time_range = time_window.get('late' if is_late_day else 'normal', time_window.get('normal'))
    
    start_time = time_range.get('start', '17:00')
    end_time = time_range.get('end', '22:30')
    
    # 生成时间戳
    base_timestamp = generate_timestamp(episode_date, start_time, end_time)
    
    # 根据家庭画像生成动态噪声事件
    dynamic_noise_events = generate_dynamic_noise_events(
        household_profile=household_profile,
        scene=scenario,
        episode_date=episode_date,
        day_offset=day_offset
    )
    
    # 合并预定义噪声事件和动态噪声事件
    all_noise_events = noise_events + dynamic_noise_events
    
    # 选择核心事件数量（2-5条）
    num_core_events = random.randint(2, min(5, len(core_events)))
    
    # 随机选择核心事件（保持顺序）
    selected_core_events = select_core_events(core_events, num_core_events)
    
    # 选择噪声事件数量（0-3条）
    num_noise_events = random.randint(0, min(3, len(all_noise_events)))
    
    # 随机选择噪声事件
    selected_noise_events = random.sample(all_noise_events, num_noise_events) if num_noise_events > 0 else []
    
    # 合并并排序事件
    all_events = merge_and_sort_events(selected_core_events, selected_noise_events)
    
    # 生成annotated_events
    annotated_events = []
    current_state = initialize_state(person_ids)
    event_time = base_timestamp
    
    for event_data in all_events:
        # 创建事件前的状态快照
        state_snapshot = create_state_snapshot(
            timestamp=event_time.isoformat(),
            persons=current_state['persons'],
            devices=current_state['devices'].copy()
        )
        
        # 创建事件对象
        event_obj = {
            "event": {
                "subject_id": event_data.get('subject_id', default_subject),
                "predicate": event_data['predicate'],
                "object_id": event_data['object_id'],
                "attributes": {
                    "event_type": event_data.get('event_type', ''),
                    "description": event_data.get('description', '')
                }
            },
            "state_snapshot": state_snapshot
        }
        
        annotated_events.append(event_obj)
        
        # 更新状态机
        current_state = apply_event_to_state(current_state, event_data)
        
        # 增加时间（30秒到5分钟之间）
        time_increment = timedelta(seconds=random.randint(30, 300))
        event_time += time_increment
    
    # 生成episode
    episode = {
        "episode_id": f"{scenario}_{episode_date.strftime('%Y%m%d')}",
        "home_id": default_home,
        "scene": scenario,
        "subject_id": default_subject,
        "confidence": round(0.85 + random.random() * 0.1, 2),
        "date": episode_date.isoformat(),
        "daily_state_description": f"基于规则模板生成的{scenario}场景，包含{len(annotated_events)}个设备事件",
        "annotated_events": annotated_events
    }
    
    return episode


def get_person_ids_from_household(household_profile):
    """
    从家庭画像中提取人员ID列表。
    
    Args:
        household_profile: 家庭画像字典
        
    Returns:
        list: 人员ID列表
    """
    # 从家庭画像获取成员
    members = household_profile.get('members', {})
    person_ids = []
    
    # 如果有家庭成员定义，使用家庭画像中的成员
    if members:
        for member_id, member_info in members.items():
            person_ids.append(member_id)
    else:
        # 使用默认的人员映射
        person_ids = list(PERSON_ID_MAPPING.keys())
    
    return person_ids


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


def generate_single_day_episode(scenario, episode_date, day_offset, template,
                                core_events, noise_events, time_window,
                                default_subject, default_home,
                                household_profile, person_ids):
    """
    生成单日的设备事件episode。
    
    Args:
        scenario: 场景类型
        episode_date: episode日期
        day_offset: 天数偏移（从开始算起）
        template: 场景模板
        core_events: 核心事件列表
        noise_events: 噪声事件列表
        time_window: 时间窗口配置
        default_subject: 默认主体ID
        default_home: 默认家庭ID
        household_profile: 家庭画像
        person_ids: 可用的人员ID列表
        
    Returns:
        dict: episode字典
    """
    # 确定时间窗口（是否是晚归日）
    is_late_day = is_late_work_day(day_offset, num_days=7)
    time_range = time_window.get('late' if is_late_day else 'normal', time_window.get('normal'))
    
    start_time = time_range.get('start', '17:00')
    end_time = time_range.get('end', '22:30')
    
    # 生成时间戳
    base_timestamp = generate_timestamp(episode_date, start_time, end_time)
    
    # 选择核心事件数量（2-5条）
    num_core_events = random.randint(2, min(5, len(core_events)))
    
    # 随机选择核心事件（保持顺序）
    selected_core_events = select_core_events(core_events, num_core_events)
    
    # 选择噪声事件数量（0-3条）
    num_noise_events = random.randint(0, min(3, len(noise_events)))
    
    # 随机选择噪声事件
    selected_noise_events = random.sample(noise_events, num_noise_events) if num_noise_events > 0 else []
    
    # 合并并排序事件
    all_events = merge_and_sort_events(selected_core_events, selected_noise_events)
    
    # 生成annotated_events
    annotated_events = []
    current_state = initialize_state(person_ids)
    event_time = base_timestamp
    
    for event_data in all_events:
        # 创建事件前的状态快照
        state_snapshot = create_state_snapshot(
            timestamp=event_time.isoformat(),
            persons=current_state['persons'],
            devices=current_state['devices'].copy()
        )
        
        # 创建事件对象
        event_obj = {
            "event": {
                "subject_id": event_data.get('subject_id', default_subject),
                "predicate": event_data['predicate'],
                "object_id": event_data['object_id'],
                "attributes": {
                    "event_type": event_data.get('event_type', ''),
                    "description": event_data.get('description', '')
                }
            },
            "state_snapshot": state_snapshot
        }
        
        annotated_events.append(event_obj)
        
        # 更新状态机
        current_state = apply_event_to_state(current_state, event_data)
        
        # 增加时间（30秒到5分钟之间）
        time_increment = timedelta(seconds=random.randint(30, 300))
        event_time += time_increment
    
    # 生成episode
    episode = {
        "episode_id": f"{scenario}_{episode_date.strftime('%Y%m%d')}",
        "home_id": default_home,
        "scene": scenario,
        "subject_id": default_subject,
        "confidence": round(0.85 + random.random() * 0.1, 2),
        "date": episode_date.isoformat(),
        "annotated_events": annotated_events
    }
    
    return episode


def is_late_work_day(day_offset, num_days=7):
    """
    判断某天是否是晚归日（噪声日）。
    
    Args:
        day_offset: 天数偏移
        num_days: 总天数
        
    Returns:
        bool: True表示晚归日
    """
    # 大约20%的概率是晚归日
    if random.random() < 0.2:
        return True
    
    # 周五更容易晚归
    if (datetime.now().date() - timedelta(days=num_days - 1 - day_offset)).weekday() == 4:
        if random.random() < 0.4:
            return True
    
    return False


def generate_timestamp(episode_date, start_time, end_time):
    """
    在时间窗口内生成随机时间戳。
    
    Args:
        episode_date: 日期
        start_time: 开始时间字符串（如 '17:00'）
        end_time: 结束时间字符串（如 '22:30'）
        
    Returns:
        datetime: 生成的时间戳
    """
    # 解析开始和结束时间
    start_hour, start_min = map(int, start_time.split(':'))
    end_hour, end_min = map(int, end_time.split(':'))
    
    # 处理跨午夜的情况
    if end_hour < start_hour:
        end_hour += 24
    
    # 计算时间范围（分钟）
    start_total = start_hour * 60 + start_min
    end_total = end_hour * 60 + end_min
    
    # 随机选择时间
    random_total = random.randint(start_total, end_total)
    
    # 转换回小时和分钟
    hour = random_total // 60
    minute = random_total % 60
    
    # 处理跨天
    if hour >= 24:
        hour -= 24
        episode_date += timedelta(days=1)
    
    return datetime(episode_date.year, episode_date.month, episode_date.day, hour, minute, 0)


def select_core_events(core_events, num_events):
    """
    选择核心事件（保持顺序）。
    
    Args:
        core_events: 核心事件列表
        num_events: 需要选择的数量
        
    Returns:
        list: 选中的事件列表
    """
    if len(core_events) <= num_events:
        return core_events.copy()
    
    # 确保首尾事件被选中（保证完整性）
    selected = [core_events[0]]
    
    # 选择中间事件
    middle_indices = list(range(1, len(core_events) - 1))
    selected_indices = sorted(random.sample(middle_indices, min(num_events - 2, len(middle_indices))))
    
    for idx in selected_indices:
        selected.append(core_events[idx])
    
    # 添加最后一个事件
    if len(selected) < num_events and len(core_events) > 1:
        selected.append(core_events[-1])
    
    return selected


def merge_and_sort_events(core_events, noise_events):
    """
    合并核心事件和噪声事件，并保持合理的顺序。
    
    Args:
        core_events: 核心事件列表
        noise_events: 噪声事件列表
        
    Returns:
        list: 合并后的事件列表
    """
    # 噪声事件可以插入到核心事件之间
    if not noise_events:
        return core_events
    
    result = []
    noise_idx = 0
    
    for i, core_event in enumerate(core_events):
        result.append(core_event)
        
        # 有一定概率在核心事件之间插入噪声事件
        if noise_idx < len(noise_events) and random.random() < 0.4:
            result.append(noise_events[noise_idx])
            noise_idx += 1
    
    # 添加剩余的噪声事件
    result.extend(noise_events[noise_idx:])
    
    return result


def initialize_state(person_ids):
    """
    初始化状态（事件发生前的默认状态）。
    
    Args:
        person_ids: 人员ID列表
        
    Returns:
        dict: 初始状态
    """
    # 初始化人员状态
    persons = {}
    for person_id in person_ids:
        # 根据人员角色设置初始状态
        if person_id == 'dad':
            persons[person_id] = {"status": "outside", "location": "outside"}
        elif person_id == 'mom':
            persons[person_id] = {"status": "at_home", "location": "kitchen"}
        elif person_id == 'grandpa':
            persons[person_id] = {"status": "at_home", "location": "living_room"}
        elif person_id == 'grandma':
            persons[person_id] = {"status": "at_home", "location": "bedroom"}
        elif person_id == 'child':
            persons[person_id] = {"status": "at_home", "location": "study"}
        else:
            persons[person_id] = {"status": "unknown", "location": "unknown"}
    
    # 初始化设备状态
    devices = {
        "door_main": {"state": "locked"},
        "door_bedroom": {"state": "closed"},
        "light_hallway": {"state": "off"},
        "light_living_room": {"state": "off"},
        "light_bedroom": {"state": "off"},
        "light_study": {"state": "off"},
        "light_bathroom": {"state": "off"},
        "ac_living_room": {"state": "off"},
        "ac_bedroom": {"state": "off"},
        "tv_living_room": {"state": "off"},
        "tv_bedroom": {"state": "off"},
        "curtain_living_room": {"state": "open"},
        "curtain_bedroom": {"state": "closed"},
        "security_system": {"state": "disarmed"},
        "motion_sensor": {"state": "clear"}
    }
    
    return {
        "persons": persons,
        "devices": devices,
        "space_occupancy": {"entrance": 0, "living_room": 1, "bedroom": 1, "study": 1, "kitchen": 1, "bathroom": 0}
    }


def create_state_snapshot(timestamp, persons, devices):
    """
    创建状态快照。
    
    Args:
        timestamp: 时间戳字符串
        persons: 人员状态字典
        devices: 设备状态字典
        
    Returns:
        dict: 状态快照
    """
    return {
        "timestamp": timestamp,
        "persons": persons,
        "devices": devices
    }


def apply_event_to_state(current_state, event_data):
    """
    将事件应用到状态机，更新状态。
    
    Args:
        current_state: 当前状态
        event_data: 事件数据
        
    Returns:
        dict: 更新后的状态
    """
    new_state = {
        "persons": current_state['persons'].copy(),
        "devices": current_state['devices'].copy(),
        "space_occupancy": current_state['space_occupancy'].copy()
    }
    
    predicate = event_data['predicate']
    object_id = event_data['object_id']
    event_type = event_data.get('event_type', '')
    
    # 更新人员状态
    subject_id = event_data.get('subject_id', 'dad')
    if subject_id in new_state['persons']:
        if predicate == 'entered':
            new_state['persons'][subject_id]['status'] = 'at_home'
            new_state['persons'][subject_id]['location'] = 'entrance'
        elif predicate == 'left':
            new_state['persons'][subject_id]['status'] = 'outside'
            new_state['persons'][subject_id]['location'] = 'outside'
        elif predicate == 'is':
            # 状态描述类事件
            if object_id == 'grandpa':
                new_state['persons']['grandpa']['status'] = 'sleeping'
                new_state['persons']['grandpa']['location'] = 'bedroom'
            elif object_id == 'child':
                new_state['persons']['child']['status'] = 'studying'
                new_state['persons']['child']['location'] = 'study'
            elif object_id == 'mom':
                new_state['persons']['mom']['status'] = 'cooking'
                new_state['persons']['mom']['location'] = 'kitchen'
    
    # 更新设备状态
    if object_id in new_state['devices']:
        device = new_state['devices'][object_id]
        
        if predicate == 'activated':
            device['state'] = 'on'
        elif predicate == 'deactivated':
            device['state'] = 'off'
        elif predicate == 'opened':
            device['state'] = 'open'
        elif predicate == 'closed':
            device['state'] = 'closed'
        elif predicate == 'locked':
            device['state'] = 'locked'
        elif predicate == 'detected':
            device['state'] = 'detected'
        elif predicate == 'recording':
            device['state'] = 'recording'
    
    # 更新空间占用
    if event_type == 'enter_home':
        new_state['space_occupancy']['entrance'] += 1
    elif event_type == 'leave_home':
        new_state['space_occupancy']['entrance'] -= 1
    
    return new_state


def get_device_events_summary(device_events):
    """
    获取设备事件的摘要信息。
    
    Args:
        device_events: 设备事件字典（支持两种格式）
        
    Returns:
        str: 摘要信息字符串
    """
    summary = []
    
    # 支持两种格式：新格式（包含episodes）和旧格式（包含sessions）
    if 'episodes' in device_events:
        episodes = device_events.get('episodes', [])
        summary.append(f"场景: {device_events.get('scenario', 'unknown')}")
        summary.append(f"Episode数量: {len(episodes)}")
        
        total_events = 0
        for episode in episodes:
            events = episode.get('annotated_events', [])
            total_events += len(events)
        
        summary.append(f"总事件数量: {total_events}")
        
        if episodes:
            first_date = episodes[0].get('date', 'unknown')
            last_date = episodes[-1].get('date', 'unknown')
            summary.append(f"日期范围: {first_date} - {last_date}")
    
    else:
        # 旧格式
        summary.append(f"场景: {device_events.get('scenario', 'unknown')}")
        
        sessions = device_events.get('sessions', {})
        summary.append(f"会话数量: {len(sessions)}")
        
        total_events = 0
        for session_name, session_data in sessions.items():
            if isinstance(session_data, dict):
                events = session_data.get('annotated_events', [])
                total_events += len(events)
        
        summary.append(f"总事件数量: {total_events}")
    
    return "\n".join(summary)


# ==================== 旧版函数（保持向后兼容） ====================

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
