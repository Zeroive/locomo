"""
设备操作行为轨迹生成模块

生成用户与AI助手对话过程中的设备操作轨迹，包含工具调用记录。
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
from typing import Dict, List, Any


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


def get_relevant_tools_for_intent(intent: str, user_devices: List[str], tools_schema: Dict[str, dict]) -> List[str]:
    """
    根据用户意图和可用设备获取相关工具
    
    Args:
        intent: 用户意图描述
        user_devices: 用户拥有的设备列表
        tools_schema: 工具 schema
    
    Returns:
        相关工具名称列表
    """
    relevant_tools = []
    
    # 根据意图关键词匹配工具
    intent_keywords = intent.lower()
    
    # 定义意图到工具的映射规则
    intent_tool_map = {
        '温度': ['temp_humidity_sensor.get_reading', 'air_conditioner.get_status', 'air_conditioner.set_target_temperature'],
        '空调': ['air_conditioner.get_status', 'air_conditioner.set_power', 'air_conditioner.set_mode', 'air_conditioner.set_target_temperature', 'air_conditioner.set_fan_speed'],
        '灯': ['smart_light.set_power', 'smart_light.set_brightness', 'smart_light.set_color_temperature', 'smart_light.activate_scene'],
        '窗帘': ['smart_curtain.get_position', 'smart_curtain.set_position', 'smart_curtain.stop'],
        '门锁': ['smart_lock.get_status', 'smart_lock.lock', 'smart_lock.unlock', 'smart_lock.get_unlock_logs'],
        '摄像头': ['door_camera.get_recent_events', 'door_camera.take_snapshot', 'door_camera.start_recording'],
        '空气质量': ['air_quality_sensor.get_reading', 'fresh_air_system.get_status', 'fresh_air_system.set_power', 'fresh_air_system.set_speed'],
        '新风': ['fresh_air_system.get_status', 'fresh_air_system.set_power', 'fresh_air_system.set_speed'],
        '电视': ['tv_projector.set_power', 'tv_projector.set_volume', 'tv_projector.set_input_source', 'tv_projector.media_control'],
        '音箱': ['smart_speaker.announce', 'smart_speaker.set_volume', 'smart_speaker.play_media', 'smart_speaker.stop_media'],
        '离家': ['smart_lock.lock', 'scene.activate'],
        '回家': ['smart_lock.unlock', 'scene.activate'],
        '睡觉': ['smart_light.set_power', 'smart_lock.lock', 'scene.activate'],
        '起床': ['smart_light.set_power', 'scene.activate'],
        '查看': ['temp_humidity_sensor.get_reading', 'air_quality_sensor.get_reading', 'smart_lock.get_status', 'door_camera.get_recent_events'],
        '打开': ['smart_light.set_power', 'air_conditioner.set_power', 'smart_curtain.set_position', 'fresh_air_system.set_power', 'tv_projector.set_power', 'smart_speaker.play_media'],
        '关闭': ['smart_light.set_power', 'air_conditioner.set_power', 'smart_curtain.set_position', 'fresh_air_system.set_power', 'tv_projector.set_power', 'smart_speaker.stop_media'],
        '设置': ['smart_light.set_brightness', 'smart_light.set_color_temperature', 'air_conditioner.set_target_temperature', 'air_conditioner.set_fan_speed', 'smart_curtain.set_position'],
        '网络': ['wifi_router.list_connected_devices', 'wifi_router.get_presence_by_user'],
    }
    
    # 根据关键词匹配工具
    for keyword, tools in intent_tool_map.items():
        if keyword in intent_keywords:
            for tool in tools:
                # 检查工具是否属于用户的设备
                tool_device_id = tool.split('.')[0]
                if tool_device_id in user_devices or tool.startswith('home.') or tool.startswith('scene.') or tool.startswith('automation.'):
                    relevant_tools.append(tool)
    
    return list(set(relevant_tools))


def generate_tool_call_response(tool_name: str, tools_schema: Dict[str, dict]) -> str:
    """
    生成工具调用后的响应
    
    Args:
        tool_name: 工具名称
        tools_schema: 工具 schema
    
    Returns:
        工具执行后的响应文本
    """
    tool_def = tools_schema.get(tool_name, {})
    category = tool_def.get('category', 'query')
    
    responses = {
        'wifi_router.list_connected_devices': '已查询到当前连接的设备有：手机、电脑和智能音箱。',
        'wifi_router.get_presence_by_user': '检测到家人目前都在家中。',
        'wifi_router.block_device': '已将该设备加入黑名单，禁止连接网络。',
        'wifi_router.set_guest_network': '访客网络已成功开启，有效期2小时。',
        
        'door_camera.get_recent_events': '门口摄像头最近10分钟没有异常事件。',
        'door_camera.take_snapshot': '已完成抓拍，图片已保存到相册。',
        'door_camera.start_recording': '开始录制短视频，预计15秒后完成。',
        'door_camera.play_preset_voice': '已播放预设语音提醒。',
        
        'smart_lock.get_status': '门锁当前状态：已上锁。',
        'smart_lock.lock': '已成功上锁。',
        'smart_lock.unlock': '已成功解锁，请及时进门。',
        'smart_lock.create_temp_password': '临时密码已生成：886622，有效期至今晚10点。',
        'smart_lock.get_unlock_logs': '最近24小时有3次开锁记录。',
        
        'temp_humidity_sensor.get_reading': '当前温度25°C，湿度60%。',
        'temp_humidity_sensor.set_threshold': '温湿度阈值已设置完成。',
        
        'light_sensor.get_lux': '当前光照强度为300勒克斯。',
        'light_sensor.set_dark_threshold': '暗光阈值已设置。',
        
        'air_quality_sensor.get_reading': '空气质量良好，PM2.5指数为15。',
        'air_quality_sensor.set_threshold': '空气质量阈值已设置。',
        
        'smart_light.set_power': '灯光已打开。',
        'smart_light.set_brightness': '亮度已调整至70%。',
        'smart_light.set_color_temperature': '色温已调整为暖光模式。',
        'smart_light.activate_scene': '已激活阅读场景灯光。',
        
        'air_conditioner.get_status': '空调当前温度26°C，制冷模式。',
        'air_conditioner.set_power': '空调已打开。',
        'air_conditioner.set_mode': '已切换为制热模式。',
        'air_conditioner.set_target_temperature': '目标温度已设置为24°C。',
        'air_conditioner.set_fan_speed': '风速已调整为中档。',
        
        'smart_curtain.get_position': '窗帘当前位置：50%。',
        'smart_curtain.set_position': '窗帘已调整到指定位置。',
        'smart_curtain.stop': '窗帘已停止移动。',
        
        'fresh_air_system.get_status': '新风系统正在运行，风量为高档。',
        'fresh_air_system.set_power': '新风系统已开启。',
        'fresh_air_system.set_speed': '新风风速已调整为中档。',
        'fresh_air_system.reset_filter_reminder': '滤网提醒已重置。',
        
        'tv_projector.set_power': '电视已打开。',
        'tv_projector.set_volume': '音量已调整至50%。',
        'tv_projector.set_input_source': '已切换到HDMI1输入源。',
        'tv_projector.media_control': '已暂停播放。',
        
        'smart_speaker.announce': '已播报消息给家人。',
        'smart_speaker.set_volume': '音量已调整至适中。',
        'smart_speaker.play_media': '开始播放音乐。',
        'smart_speaker.stop_media': '已停止播放。',
        
        'home.get_mode': '当前家庭模式为：居家模式。',
        'home.set_mode': '已切换为离家模式，所有设备已自动关闭。',
        'home.get_occupancy': '检测到家中有2人。',
        
        'scene.activate': '场景已激活，相关设备已按预设配置调整。',
        'scene.preview': '场景预览完成，将执行5个设备动作。',
    }
    
    return responses.get(tool_name, '操作已完成。')


def generate_trajectory_for_session(session_dialog: List[dict], user_devices: List[str], tools_schema: Dict[str, dict], assistant_name: str, user_name: str) -> List[dict]:
    """
    为单个会话生成设备操作轨迹
    
    Args:
        session_dialog: 会话对话列表
        user_devices: 用户拥有的设备列表
        tools_schema: 工具 schema
        assistant_name: 助手名称
        user_name: 用户名称
    
    Returns:
        设备操作轨迹列表
    """
    trajectory = []
    
    for turn in session_dialog:
        speaker = turn.get('speaker', '')
        clean_text = turn.get('clean_text', '')
        
        # 跳过空内容和结束标记
        if not clean_text or clean_text.strip() == '[END]':
            continue
        
        if speaker == user_name:  # 用户发言
            trajectory.append({
                "role": "user",
                "content": clean_text
            })
            
            # 分析用户意图，生成工具调用
            relevant_tools = get_relevant_tools_for_intent(clean_text, user_devices, tools_schema)
            
            if relevant_tools:
                # 随机选择一个相关工具
                selected_tool = random.choice(relevant_tools)
                
                # 生成助手响应
                trajectory.append({
                    "role": "assistant",
                    "content": "好的，我来帮你操作。"
                })
                
                # 生成工具调用
                trajectory.append({
                    "role": "tool",
                    "content": f"调用工具 {selected_tool}"
                })
                
                # 生成工具执行结果
                response = generate_tool_call_response(selected_tool, tools_schema)
                trajectory.append({
                    "role": "assistant",
                    "content": response
                })
        
        elif speaker == assistant_name:  # 助手发言（非工具响应）
            # 检查是否已经有对应的工具调用响应
            if trajectory and trajectory[-1].get('role') != 'tool':
                trajectory.append({
                    "role": "assistant",
                    "content": clean_text
                })
    
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
    
    # 获取名称
    assistant_name = agent_a.get('name', 'AI助手')
    user_name = agent_b.get('name', '用户')
    
    # 加载工具 schema
    schema_path = args.device_file.replace('home_devices.json', 'tools_schema.json')
    tools_schema = load_tools_schema(schema_path)
    
    # 获取用户设备列表
    user_devices = agent_b.get('devices', [])
    
    # 获取会话数量
    num_sessions = args.num_sessions
    
    trajectories = {}
    
    for sess_id in range(1, num_sessions + 1):
        session_key = f'session_{sess_id}'
        session_dialog = agent_b.get(session_key, [])
        
        if not session_dialog:
            continue
        
        # 生成轨迹
        trajectory = generate_trajectory_for_session(session_dialog, user_devices, tools_schema, assistant_name, user_name)
        
        if trajectory:
            trajectories[sess_id] = trajectory
    
    return trajectories
