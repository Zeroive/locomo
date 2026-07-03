"""设备库读取与展示服务。"""

import json
import logging
import os

from generative_agents.device_event_domain import DEVICE_STATES

DEFAULT_DEVICE_NAMES = {
    "wifi_router": "WiFi路由器",
    "door_camera": "门口摄像头",
    "door_main": "主门（智能门锁）",
    "door_bell": "门铃",
    "temp_humidity_sensor": "温湿度传感器",
    "light_sensor": "光照传感器",
    "air_quality_sensor": "空气质量传感器",
    "light_hallway": "玄关灯",
    "light_living_room": "客厅灯",
    "light_bedroom": "卧室灯",
    "light_study": "书房灯",
    "light_kitchen": "厨房灯",
    "light_bathroom": "卫生间灯",
    "ac_living_room": "客厅空调",
    "ac_bedroom": "卧室空调",
    "tv_living_room": "客厅电视",
    "tv_bedroom": "卧室电视",
    "curtain_living_room": "客厅窗帘",
    "curtain_bedroom": "卧室窗帘",
    "fresh_air_system": "新风系统",
    "security_system": "安防系统",
    "motion_sensor": "移动传感器",
    "security_camera": "安防摄像头",
    "coffee_machine": "咖啡机",
    "smart_speaker": "智能音箱",
    "tv_kids": "儿童房电视",
}


def format_devices_info(device_file, device_ids=None):
    """
    格式化设备信息，只显示家庭存在的设备。
    
    Args:
        device_file: 设备配置文件路径
        device_ids: 需要显示的设备ID列表，为None时显示所有设备
        
    Returns:
        str: 格式化的设备信息字符串
    """
    allowed_ids = set(device_ids or [])
    filter_devices = device_ids is not None

    if not device_file or not os.path.exists(device_file):
        lines = [
            f"- {device_id}: {name}"
            for device_id, name in DEFAULT_DEVICE_NAMES.items()
            if not filter_devices or device_id in allowed_ids
        ]
        return '\n'.join(lines)
    
    try:
        with open(device_file, 'r', encoding='utf-8') as f:
            devices_config = json.load(f)
        
        info_lines = []
        device_categories = devices_config.get('device_categories', {})
        config_device_names = {}
        
        for category_name, category_data in device_categories.items():
            devices = category_data.get('devices', {})
            for device_id, device_info in devices.items():
                config_device_names[device_id] = device_info.get('name', device_id)
        
        for device_id in (device_ids or []):
            if filter_devices and device_id not in allowed_ids:
                continue
            name = config_device_names.get(device_id, DEFAULT_DEVICE_NAMES.get(device_id, device_id))
            info_lines.append(f"- {device_id}: {name}")
        
        return '\n'.join(info_lines) if info_lines else "- door_main: 主门\n- light_hallway: 玄关灯"
        
    except Exception as e:
        logging.warning(f"Failed to load device config: {e}, using default devices")
        lines = [
            f"- {device_id}: {name}"
            for device_id, name in DEFAULT_DEVICE_NAMES.items()
            if not filter_devices or device_id in allowed_ids
        ]
        return '\n'.join(lines)


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
        return list(DEVICE_STATES.keys())
    
    try:
        with open(device_file, 'r', encoding='utf-8') as f:
            devices_config = json.load(f)
        
        device_ids = []
        device_categories = devices_config.get('device_categories', {})
        
        for category_data in device_categories.values():
            devices = category_data.get('devices', {})
            device_ids.extend(devices.keys())
        
        return device_ids if device_ids else list(DEVICE_STATES.keys())
        
    except Exception as e:
        logging.warning(f"Failed to load device IDs: {e}, using default devices")
        return list(DEVICE_STATES.keys())
