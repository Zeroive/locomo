"""
设备操作行为轨迹生成模块

使用大语言模型逐轮模拟用户与AI助手在场景下的工具交互，生成包含工具调用的对话轨迹。

轨迹格式：
[
    {"role": "user", "content": "帮我检查空调状态"},
    {"role": "assistant", "content": "好的，我来帮你查询。"},
    {"role": "tool", "content": "调用工具 air_conditioner.get_status(device_id=\"living_room_ac\")"},
    {"role": "assistant", "content": "空调当前温度26°C，制冷模式。"}
]
"""
import json
import random
import os
import re
from typing import Dict, List, Any

# 导入模型调用函数
from global_methods import run_chatgpt



def generate_simulated_response(prompt: str) -> str:
    """
    模拟生成单轮响应（当无法调用真实模型时使用）
    """
    # 根据prompt中包含的角色决定生成什么响应
    if "你是用户" in prompt:
        # 生成用户响应
        user_responses = [
            "帮我检查一下空调状态",
            "把客厅的灯打开",
            "今天天气怎么样？",
            "帮我把空调调到24度",
            "检查一下门锁",
            "播放音乐",
            "打开窗帘",
            "关闭电视",
            "查看一下室内温度"
        ]
        return random.choice(user_responses)
    elif "你是一个家庭智能助手" in prompt or "家庭智能助手" in prompt:
        # 生成助手响应（JSON格式）
        assistant_responses = [
            {"thought": "用户想查询空调状态，需要调用 air_conditioner.get_status 工具", "action": "tool", "tool_name": "air_conditioner.get_status", "tool_params": {"device_id": "living_room_ac"}},
            {"thought": "用户想打开灯光，需要调用 smart_light.set_power 工具", "action": "tool", "tool_name": "smart_light.set_power", "tool_params": {"device_id": "living_room_light", "power": "on"}},
            {"thought": "用户询问天气，这是一个简单问题，可以直接回答", "action": "answer", "content": "今天天气晴朗，气温28°C。"},
            {"thought": "用户想调整空调温度，需要调用 air_conditioner.set_target_temperature 工具", "action": "tool", "tool_name": "air_conditioner.set_target_temperature", "tool_params": {"device_id": "living_room_ac", "target_temp_c": 24}},
            {"thought": "用户想检查门锁状态，需要调用 smart_lock.get_status 工具", "action": "tool", "tool_name": "smart_lock.get_status", "tool_params": {"lock_id": "front_door_lock"}},
            {"thought": "用户想播放音乐，需要调用 smart_speaker.play_media 工具", "action": "tool", "tool_name": "smart_speaker.play_media", "tool_params": {"device_id": "living_room_speaker", "media_type": "music"}},
            {"thought": "用户想关闭灯光，需要调用 smart_light.set_power 工具", "action": "tool", "tool_name": "smart_light.set_power", "tool_params": {"device_id": "living_room_light", "power": "off"}}
        ]
        return json.dumps(random.choice(assistant_responses), ensure_ascii=False)
    else:
        return "帮我检查一下空调状态"


def load_tools_schema(schema_path: str) -> Dict[str, dict]:
    """加载工具 schema"""
    if not os.path.exists(schema_path):
        return {}
    
    with open(schema_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 将所有工具合并到一个字典中
    all_tools = {}
    
    # 添加全局工具
    for tool_name, tool_def in data.get('global_tools', {}).items():
        all_tools[tool_name] = tool_def
    
    # 添加设备工具
    for device_id, device_tools in data.get('device_tools', {}).items():
        for action, tool_def in device_tools.items():
            all_tools[tool_def['tool_name']] = tool_def
    
    return all_tools


def get_tools_list_for_prompt(user_devices: List[str], tools_schema: Dict[str, dict]) -> str:
    """
    生成工具列表的prompt格式（包含参数信息）
    
    Args:
        user_devices: 用户拥有的设备列表
        tools_schema: 工具 schema
    
    Returns:
        工具列表的字符串描述
    """
    tools_list = []
    
    for tool_name, tool_def in tools_schema.items():
        # 检查是否是全局工具
        if tool_name.startswith('home.') or tool_name.startswith('scene.') or tool_name.startswith('automation.'):
            params = tool_def.get('parameters', {})
            params_str = ", ".join([f"{k}: {v.get('description', '')}" for k, v in params.items()])
            tools_list.append(f"- {tool_name}: {tool_def.get('description', '')} (参数: {params_str})")
            continue
        
        # 检查设备工具是否属于用户设备
        device_id = tool_name.split('.')[0] if '.' in tool_name else ''
        if device_id in user_devices:
            params = tool_def.get('parameters', {})
            params_str = ", ".join([f"{k}: {v.get('description', '')}" for k, v in params.items()])
            tools_list.append(f"- {tool_name}: {tool_def.get('description', '')} (参数: {params_str})")
    
    return '\n'.join(tools_list)


def build_user_prompt(scenario: str, user_profile: str, user_devices: List[str], tools_schema: Dict[str, dict], conversation_history: str) -> str:
    """
    构建生成用户响应的prompt
    
    Args:
        scenario: 场景描述
        user_profile: 用户画像
        user_devices: 用户拥有的设备列表
        tools_schema: 工具 schema
        conversation_history: 对话历史
    
    Returns:
        完整的prompt字符串
    """
    tools_list = get_tools_list_for_prompt(user_devices, tools_schema)
    
    prompt = f"""
你是用户{user_profile}，正在与家庭智能助手对话。

## 场景描述
{scenario}

## 可用设备和工具
{tools_list}

## 对话历史
{conversation_history}

## 你的任务
根据场景和对话历史，生成下一句用户的话。用户可以：
1. 询问问题（如天气、设备状态）
2. 下达命令（如打开空调、关闭灯光）
3. 继续对话

## 输出要求
只输出用户说的话，不要包含其他内容。
"""
    
    return prompt.strip()


def build_assistant_prompt(scenario: str, user_message: str, user_devices: List[str], tools_schema: Dict[str, dict], conversation_history: str) -> str:
    """
    构建生成助手响应的prompt（包含工具调用决策）
    
    Args:
        scenario: 场景描述
        user_message: 用户当前消息
        user_devices: 用户拥有的设备列表
        tools_schema: 工具 schema
        conversation_history: 对话历史
    
    Returns:
        完整的prompt字符串
    """
    tools_list = get_tools_list_for_prompt(user_devices, tools_schema)
    
    prompt = f"""
你是一个家庭智能助手，正在与用户对话。

## 场景描述
{scenario}

## 用户消息
{user_message}

## 可用工具
{tools_list}

## 对话历史
{conversation_history}

## 你的任务
分析用户的消息，决定是直接回答还是调用工具。

## 输出格式
请输出JSON格式，包含以下字段：
- thought: 思考过程，说明为什么选择直接回答或调用工具
- action: "answer" 或 "tool"
- content: 如果action是"answer"，这里是直接回答的内容
- tool_name: 如果action是"tool"，这里是工具名称
- tool_params: 如果action是"tool"，这里是工具参数（JSON对象）

## 输出示例
直接回答:
{{"thought": "用户询问天气，这是一个简单问题，可以直接回答", "action": "answer", "content": "今天天气晴朗，气温28°C。"}}

调用工具:
{{"thought": "用户想查询空调状态，需要调用 air_conditioner.get_status 工具", "action": "tool", "tool_name": "air_conditioner.get_status", "tool_params": {{"device_id": "living_room_ac"}}}}
"""
    
    return prompt.strip()


def generate_tool_result(tool_name: str, tool_params: Dict[str, Any], tools_schema: Dict[str, dict]) -> str:
    """
    生成工具调用后的结果
    
    Args:
        tool_name: 工具名称
        tool_params: 工具参数
        tools_schema: 工具 schema
    
    Returns:
        工具执行结果描述
    """
    results = {
        'wifi_router.list_connected_devices': f'已查询到当前连接的设备：{", ".join(["手机", "电脑", "智能音箱"])}',
        'wifi_router.get_presence_by_user': f'检测到{tool_params.get("user_id", "家人")}目前{"在家" if random.choice([True, False]) else "不在家"}',
        'wifi_router.block_device': f'已将设备{tool_params.get("device_id", "")}加入黑名单',
        'wifi_router.set_guest_network': '访客网络已成功开启',
        
        'door_camera.get_recent_events': '门口摄像头最近没有异常事件',
        'door_camera.take_snapshot': '已完成抓拍，图片已保存',
        'door_camera.start_recording': '开始录制短视频',
        'door_camera.play_preset_voice': '已播放预设语音提醒',
        
        'smart_lock.get_status': '门锁当前状态：已上锁',
        'smart_lock.lock': '已成功上锁',
        'smart_lock.unlock': '已成功解锁，请及时进门',
        'smart_lock.create_temp_password': '临时密码已生成：886622',
        'smart_lock.get_unlock_logs': '最近24小时有3次开锁记录',
        
        'temp_humidity_sensor.get_reading': f'当前温度{random.randint(20, 30)}°C，湿度{random.randint(40, 70)}%',
        'temp_humidity_sensor.set_threshold': '温湿度阈值已设置完成',
        
        'light_sensor.get_lux': f'当前光照强度为{random.randint(100, 1000)}勒克斯',
        'light_sensor.set_dark_threshold': '暗光阈值已设置',
        
        'air_quality_sensor.get_reading': '空气质量良好，PM2.5指数为15',
        'air_quality_sensor.set_threshold': '空气质量阈值已设置',
        
        'smart_light.set_power': f'灯光已{"打开" if tool_params.get("power") == "on" else "关闭"}',
        'smart_light.set_brightness': f'亮度已调整至{tool_params.get("brightness", 50)}%',
        'smart_light.set_color_temperature': '色温已调整为暖光模式',
        'smart_light.activate_scene': '已激活阅读场景灯光',
        
        'air_conditioner.get_status': f'空调当前温度{random.randint(22, 28)}°C，制冷模式',
        'air_conditioner.set_power': f'空调已{"打开" if tool_params.get("power") == "on" else "关闭"}',
        'air_conditioner.set_mode': f'已切换为{tool_params.get("mode", "制冷")}模式',
        'air_conditioner.set_target_temperature': f'目标温度已设置为{tool_params.get("target_temp_c", 24)}°C',
        'air_conditioner.set_fan_speed': f'风速已调整为{tool_params.get("fan_speed", "中档")}',
        
        'smart_curtain.get_position': f'窗帘当前位置：{random.randint(0, 100)}%',
        'smart_curtain.set_position': f'窗帘已调整到{tool_params.get("position", 50)}%',
        'smart_curtain.stop': '窗帘已停止移动',
        
        'fresh_air_system.get_status': '新风系统正在运行',
        'fresh_air_system.set_power': '新风系统已开启',
        'fresh_air_system.set_speed': '新风风速已调整',
        'fresh_air_system.reset_filter_reminder': '滤网提醒已重置',
        
        'tv_projector.set_power': f'电视已{"打开" if tool_params.get("power") == "on" else "关闭"}',
        'tv_projector.set_volume': f'音量已调整至{tool_params.get("volume", 50)}%',
        'tv_projector.set_input_source': '已切换输入源',
        'tv_projector.media_control': f'已{tool_params.get("action", "暂停")}播放',
        
        'smart_speaker.announce': '已播报消息',
        'smart_speaker.set_volume': '音量已调整',
        'smart_speaker.play_media': '开始播放音乐',
        'smart_speaker.stop_media': '已停止播放',
        
        'home.get_mode': '当前家庭模式为：居家模式',
        'home.set_mode': '已切换为离家模式',
        'home.get_occupancy': '检测到家中有2人',
        
        'scene.activate': '场景已激活，相关设备已按预设配置调整',
        'scene.preview': '场景预览完成，将执行5个设备动作',
    }
    
    return results.get(tool_name, '操作已完成')


def parse_assistant_response(response: str) -> dict:
    """
    解析助手响应
    
    Args:
        response: 模型返回的字符串
    
    Returns:
        解析后的响应字典
    """
    try:
        # 首先尝试直接解析
        result = json.loads(response)
        return result
    except json.JSONDecodeError:
        pass
    
    # 尝试提取JSON部分
    match = re.search(r'\{.*\}', response, re.DOTALL)
    if match:
        try:
            result = json.loads(match.group())
            return result
        except json.JSONDecodeError:
            pass
    
    # 返回默认响应
    return {
        "thought": "解析失败，使用默认响应",
        "action": "answer",
        "content": "好的，我来处理。"
    }


def generate_trajectory_for_scenario(scenario: str, user_profile: str, user_devices: List[str], tools_schema: Dict[str, dict], num_turns: int = 3) -> List[dict]:
    """
    使用模型逐轮生成设备操作轨迹
    
    Args:
        scenario: 场景描述
        user_profile: 用户画像
        user_devices: 用户拥有的设备列表
        tools_schema: 工具 schema
        num_turns: 对话轮数
    
    Returns:
        设备操作轨迹列表
    """
    trajectory = []
    conversation_history = ""
    
    for _ in range(num_turns):
        # 1. 生成用户消息
        user_prompt = build_user_prompt(scenario, user_profile, user_devices, tools_schema, conversation_history)
        user_response = run_chatgpt(user_prompt, temperature=0.8)
        
        try:
            user_data = json.loads(user_response)
            user_message = user_data['choices'][0]['message']['content']
        except (json.JSONDecodeError, KeyError, IndexError):
            user_message = user_response
        
        # 添加用户消息到轨迹
        trajectory.append({"role": "user", "content": user_message})
        
        # 更新对话历史
        conversation_history += f"用户: {user_message}\n"
        
        # 2. 生成助手响应（包含工具调用决策）
        assistant_prompt = build_assistant_prompt(scenario, user_message, user_devices, tools_schema, conversation_history)
        assistant_response = run_chatgpt(assistant_prompt, temperature=0.8)
        
        # 解析助手响应
        try:
            assistant_data = json.loads(assistant_response)
            assistant_content = assistant_data['choices'][0]['message']['content']
        except (json.JSONDecodeError, KeyError, IndexError):
            assistant_content = assistant_response
        
        parsed_response = parse_assistant_response(assistant_content)
        
        if parsed_response.get("action") == "tool":
            # 调用工具
            tool_name = parsed_response.get("tool_name", "")
            tool_params = parsed_response.get("tool_params", {})
            
            # 添加助手思考
            trajectory.append({"role": "assistant", "content": "好的，我来帮你操作。"})
            
            # 生成工具调用字符串（包含参数）
            params_str = ", ".join([f'{k}="{v}"' for k, v in tool_params.items()])
            trajectory.append({"role": "tool", "content": f"调用工具 {tool_name}({params_str})"})
            
            # 生成工具执行结果
            tool_result = generate_tool_result(tool_name, tool_params, tools_schema)
            trajectory.append({"role": "assistant", "content": tool_result})
            
            # 更新对话历史
            conversation_history += f"助手: 调用工具 {tool_name}\n"
            conversation_history += f"助手: {tool_result}\n"
            
        else:
            # 直接回答
            answer = parsed_response.get("content", "好的，我知道了。")
            trajectory.append({"role": "assistant", "content": answer})
            
            # 更新对话历史
            conversation_history += f"助手: {answer}\n"
    
    return trajectory


def generate_all_device_trajectories(agents: List[dict], args) -> Dict[int, List[dict]]:
    """
    为所有会话生成设备操作轨迹
    
    Args:
        agents: 包含 agent_a 和 agent_b 的列表
        args: 命令行参数
    
    Returns:
        会话ID到轨迹的映射
    """
    agent_a, agent_b = agents
    
    # 获取用户信息
    user_profile = agent_b.get('persona', {}).get('description', '一位普通用户')
    
    # 获取场景信息
    scenario_id = getattr(args, 'scenario', 'male_leave_work')
    scenario_file = getattr(args, 'scenario_file', './data/scenarios/scenarios.json')
    
    # 加载场景配置
    scenario_description = ""
    if os.path.exists(scenario_file):
        with open(scenario_file, 'r', encoding='utf-8') as f:
            scenarios = json.load(f)
            scenario_description = scenarios.get(scenario_id, {}).get('description', scenario_id)
    
    # 加载工具 schema
    schema_path = args.device_file.replace('home_devices.json', 'tools_schema.json')
    tools_schema = load_tools_schema(schema_path)
    
    # 获取用户设备列表
    user_devices = agent_b.get('devices', [])
    
    if not user_devices:
        return {}
    
    # 获取会话数量
    num_sessions = args.num_sessions
    
    trajectories = {}
    
    for sess_id in range(1, num_sessions + 1):
        # 生成轨迹
        trajectory = generate_trajectory_for_scenario(
            scenario=scenario_description,
            user_profile=user_profile,
            user_devices=user_devices,
            tools_schema=tools_schema,
            num_turns=3  # 每会话3轮对话
        )
        
        if trajectory:
            trajectories[sess_id] = trajectory
    
    return trajectories