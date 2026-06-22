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
try:
    from global_methods import run_chatgpt
except (ImportError, ModuleNotFoundError) as e:
    # 如果无法导入，使用模拟函数
    print(f"Warning: Cannot import run_chatgpt from global_methods: {e}")
    print("Using simulated response function instead.")
    
    def run_chatgpt(query, num_gen=1, num_tokens_request=1000, 
                    model='chatgpt', use_16k=False, temperature=1.0, wait_time=1):
        """模拟模型响应"""
        return json.dumps({
            "choices": [{
                "message": {
                    "content": generate_simulated_response(query)
                }
            }]
        })



def generate_simulated_response(prompt: str) -> str:
    """
    模拟生成单轮响应（当无法调用真实模型时使用）
    """
    # 根据prompt中包含的角色决定生成什么响应
    if "你是一个家庭智能助手，刚刚执行了一个工具调用" in prompt:
        # 生成工具执行结果
        # 从prompt中提取工具名称
        tool_name_match = re.search(r'工具名称: ([\w.]+)', prompt)
        tool_name = tool_name_match.group(1) if tool_name_match else "unknown_tool"
        
        # 从prompt中提取工具参数
        params_match = re.search(r'工具参数: (.+)', prompt)
        params_str = params_match.group(1) if params_match else ""
        
        # 生成模拟结果
        if 'get_status' in tool_name or 'get_reading' in tool_name or 'get_position' in tool_name:
            return f"查询完成。当前状态正常，设备运行良好。"
        elif 'set_temperature' in tool_name or 'set_target_temperature' in tool_name:
            temp_match = re.search(r'target_temp_c="(\d+)"', params_str)
            temp = temp_match.group(1) if temp_match else "24"
            return f"已将目标温度设置为{temp}°C，设备正在调整中。"
        elif 'set_power' in tool_name:
            if 'power="on"' in params_str:
                return "设备已成功开启，正在运行中。"
            else:
                return "设备已成功关闭。"
        elif 'set_brightness' in tool_name:
            return "亮度已调整完成，当前亮度适中。"
        elif 'set_position' in tool_name:
            return "窗帘位置已调整完成。"
        elif 'play_media' in tool_name:
            return "开始播放音乐，音质良好。"
        elif 'lock' in tool_name or 'unlock' in tool_name:
            return "门锁操作已完成，安全状态良好。"
        else:
            return "操作已成功完成。"
    
    elif "你是用户" in prompt:
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


def build_tool_result_prompt(tool_name: str, tool_params: Dict[str, Any], tool_description: str, conversation_history: str) -> str:
    """
    构建生成工具执行结果的prompt
    
    Args:
        tool_name: 工具名称
        tool_params: 工具参数
        tool_description: 工具描述
        conversation_history: 对话历史
    
    Returns:
        完整的prompt字符串
    """
    params_str = ", ".join([f'{k}="{v}"' for k, v in tool_params.items()])
    
    prompt = f"""
你是一个家庭智能助手，刚刚执行了一个工具调用。请根据工具信息生成一个自然、友好的执行结果回复。

## 工具信息
- 工具名称: {tool_name}
- 工具参数: {params_str}
- 工具描述: {tool_description}

## 对话历史
{conversation_history}

## 你的任务
生成工具执行后的结果回复，要求：
1. 回复要自然友好，符合家庭智能助手的定位
2. 结果要符合工具的功能描述
3. 如果是查询类工具，返回具体的数值或状态
4. 如果是控制类工具，确认操作已完成
5. 只输出回复内容，不要包含其他信息

## 输出示例
- 查询空调状态: "空调当前温度26°C，制冷模式运行中。"
- 设置空调温度: "已将空调目标温度设置为24°C，空调正在调整中。"
- 打开灯光: "客厅灯光已打开，当前亮度为80%。"
- 查询门锁状态: "门锁当前状态：已上锁，安全状态良好。"
"""
    
    return prompt.strip()


def generate_tool_result(tool_name: str, tool_params: Dict[str, Any], tools_schema: Dict[str, dict], conversation_history: str = "") -> str:
    """
    使用模型生成工具调用后的结果
    
    Args:
        tool_name: 工具名称
        tool_params: 工具参数
        tools_schema: 工具 schema
        conversation_history: 对话历史
    
    Returns:
        工具执行结果描述
    """
    # 获取工具描述
    tool_def = tools_schema.get(tool_name, {})
    tool_description = tool_def.get('description', '执行设备操作')
    
    # 构建prompt
    prompt = build_tool_result_prompt(tool_name, tool_params, tool_description, conversation_history)
    
    # 调用模型生成结果
    response = run_chatgpt(prompt, temperature=0.7, num_tokens_request=300)
    
    # 解析响应
    try:
        result_data = json.loads(response)
        tool_result = result_data['choices'][0]['message']['content']
    except (json.JSONDecodeError, KeyError, IndexError):
        tool_result = response
    
    # 清理结果（移除可能的引号或多余空格）
    tool_result = tool_result.strip().strip('"').strip("'")
    
    return tool_result


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
        user_response = run_chatgpt(user_prompt, temperature=0.8, num_tokens_request=500)
        
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
        assistant_response = run_chatgpt(assistant_prompt, temperature=0.7, num_tokens_request=1000)
        
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
            tool_call_str = f"调用工具 {tool_name}({params_str})"
            trajectory.append({"role": "tool", "content": tool_call_str})
            
            # 生成工具执行结果（传入对话历史）
            tool_result = generate_tool_result(tool_name, tool_params, tools_schema, conversation_history)
            trajectory.append({"role": "assistant", "content": tool_result})
            
            # 更新对话历史（包含完整的工具调用信息）
            conversation_history += f"助手: {tool_call_str}\n"
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