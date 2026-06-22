"""
设备操作行为轨迹生成模块

使用大语言模型模拟用户与AI助手在场景下的工具交互，生成包含工具调用的对话轨迹。

轨迹格式：
[
    {"role": "user", "content": "查询苹果股价"},
    {"role": "assistant", "content": "正在查询..."},
    {"role": "tool", "content": "调用工具 get_stock_info"},
    {"role": "assistant", "content": "苹果股价是 $180"}
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
except ImportError:
    # 如果无法导入，使用模拟函数
    def run_chatgpt(prompt, model="gpt-4", temperature=0.7, max_tokens=2000, **kwargs):
        """模拟模型响应"""
        return json.dumps({
            "choices": [{
                "message": {
                    "content": generate_simulated_trajectory(prompt)
                }
            }]
        })


def generate_simulated_trajectory(prompt: str) -> str:
    """
    模拟生成工具交互轨迹（当无法调用真实模型时使用）
    """
    scenarios = [
        [
            {"role": "user", "content": "帮我检查一下空调状态"},
            {"role": "assistant", "content": "好的，我来帮你查询空调状态。"},
            {"role": "tool", "content": "调用工具 air_conditioner.get_status"},
            {"role": "assistant", "content": "空调当前温度26°C，制冷模式，已开启。"}
        ],
        [
            {"role": "user", "content": "打开客厅的灯"},
            {"role": "assistant", "content": "好的，正在为你打开客厅灯光。"},
            {"role": "tool", "content": "调用工具 smart_light.set_power"},
            {"role": "assistant", "content": "灯光已打开。"}
        ],
        [
            {"role": "user", "content": "今天天气怎么样？"},
            {"role": "assistant", "content": "今天天气晴朗，气温28°C。"},
            {"role": "user", "content": "帮我把空调调到24度"},
            {"role": "assistant", "content": "好的，正在调整空调温度。"},
            {"role": "tool", "content": "调用工具 air_conditioner.set_target_temperature"},
            {"role": "assistant", "content": "已将空调温度设置为24°C。"}
        ],
        [
            {"role": "user", "content": "检查一下门锁"},
            {"role": "assistant", "content": "好的，我来帮你查看门锁状态。"},
            {"role": "tool", "content": "调用工具 smart_lock.get_status"},
            {"role": "assistant", "content": "门锁当前状态：已上锁。"}
        ],
        [
            {"role": "user", "content": "帮我播放音乐"},
            {"role": "assistant", "content": "好的，正在为你播放音乐。"},
            {"role": "tool", "content": "调用工具 smart_speaker.play_media"},
            {"role": "assistant", "content": "开始播放音乐。"}
        ]
    ]
    return json.dumps(random.choice(scenarios), ensure_ascii=False)


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
    生成工具列表的prompt格式
    
    Args:
        user_devices: 用户拥有的设备列表
        tools_schema: 工具 schema
    
    Returns:
        工具列表的字符串描述
    """
    tools_list = []
    
    # 添加全局工具
    for tool_name, tool_def in tools_schema.items():
        if tool_name.startswith('home.') or tool_name.startswith('scene.') or tool_name.startswith('automation.'):
            tools_list.append(f"- {tool_name}: {tool_def.get('description', '')}")
            continue
        
        # 检查设备工具是否属于用户设备
        device_id = tool_name.split('.')[0] if '.' in tool_name else ''
        if device_id in user_devices:
            tools_list.append(f"- {tool_name}: {tool_def.get('description', '')}")
    
    return '\n'.join(tools_list)


def build_trajectory_prompt(scenario: str, user_profile: str, user_devices: List[str], tools_schema: Dict[str, dict], num_turns: int = 3) -> str:
    """
    构建生成工具交互轨迹的prompt
    
    Args:
        scenario: 场景描述
        user_profile: 用户画像
        user_devices: 用户拥有的设备列表
        tools_schema: 工具 schema
        num_turns: 对话轮数
    
    Returns:
        完整的prompt字符串
    """
    tools_list = get_tools_list_for_prompt(user_devices, tools_schema)
    
    prompt = f"""
你是一个家庭智能助手，正在与用户进行对话。请根据以下场景和可用工具，生成一段自然的对话轨迹。

## 场景描述
{scenario}

## 用户画像
{user_profile}

## 可用工具
{tools_list}

## 对话格式要求
请输出JSON格式的对话轨迹，包含以下角色类型：
- "user": 用户的问题或指令
- "assistant": AI助手的回答
- "tool": 工具调用，格式为"调用工具 <工具名称>"

## 输出格式示例
[
    {{"role": "user", "content": "帮我检查空调状态"}},
    {{"role": "assistant", "content": "好的，我来帮你查询。"}},
    {{"role": "tool", "content": "调用工具 air_conditioner.get_status"}},
    {{"role": "assistant", "content": "空调当前温度26°C，制冷模式。"}}
]

## 要求
1. 生成{num_turns}轮对话，包含至少1次工具调用
2. 对话要符合场景和用户画像
3. 工具调用必须是可用工具列表中的工具
4. 回答要自然友好，符合家庭智能助手的定位
5. 只输出JSON格式，不要包含其他内容
"""
    
    return prompt.strip()


def parse_model_response(response: str) -> List[dict]:
    """
    解析模型响应，提取对话轨迹
    
    Args:
        response: 模型返回的字符串
    
    Returns:
        对话轨迹列表
    """
    try:
        # 尝试直接解析JSON
        result = json.loads(response)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass
    
    # 尝试提取JSON部分
    match = re.search(r'\[.*\]', response, re.DOTALL)
    if match:
        try:
            result = json.loads(match.group())
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass
    
    # 返回默认轨迹
    return [
        {"role": "user", "content": "帮我打开空调"},
        {"role": "assistant", "content": "好的，正在为你打开空调。"},
        {"role": "tool", "content": "调用工具 air_conditioner.set_power"},
        {"role": "assistant", "content": "空调已打开。"}
    ]


def generate_trajectory_for_scenario(scenario: str, user_profile: str, user_devices: List[str], tools_schema: Dict[str, dict], num_turns: int = 3) -> List[dict]:
    """
    使用模型生成单个场景的设备操作轨迹
    
    Args:
        scenario: 场景描述
        user_profile: 用户画像
        user_devices: 用户拥有的设备列表
        tools_schema: 工具 schema
        num_turns: 对话轮数
    
    Returns:
        设备操作轨迹列表
    """
    # 构建prompt
    prompt = build_trajectory_prompt(scenario, user_profile, user_devices, tools_schema, num_turns)
    
    # 调用模型
    response = run_chatgpt(prompt, temperature=0.8, max_tokens=2000)
    
    # 解析响应
    try:
        response_data = json.loads(response)
        content = response_data['choices'][0]['message']['content']
    except (json.JSONDecodeError, KeyError, IndexError):
        content = response
    
    # 解析轨迹
    trajectory = parse_model_response(content)
    
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
    user_name = agent_b.get('name', '用户')
    
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