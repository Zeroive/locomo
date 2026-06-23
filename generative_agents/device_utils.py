"""
设备选择相关工具函数。

根据用户特点和场景，使用模型智能选择相关的智能家居设备。
"""

import json
import logging
from global_methods import run_chatgpt


def select_devices_for_user(user_persona, scenario, scenario_desc="", device_file='./data/devices/home_devices.json'):
    """
    根据用户特点和场景，使用模型挑选相关的设备列表。
    
    分析用户的persona特征，结合当前场景，从设备库中挑选用户可能使用或关注的设备。
    使用LLM模型进行智能选择，考虑用户年龄、生活习惯、健康状况、场景需求等。
    
    Args:
        user_persona: 用户的persona描述字符串
        scenario: 当前场景ID
        scenario_desc: 场景详细描述（一段话描述场景背景和特点）
        device_file: 设备库文件路径
        
    Returns:
        dict: 用户相关的设备列表，包含设备ID、名称、类别和相关度评分
    """
    try:
        with open(device_file, 'r', encoding='utf-8') as f:
            devices_data = json.load(f)
    except Exception as e:
        logging.error(f"Failed to load device file: {e}")
        return {}
    
    # 获取场景相关设备
    scenario_key = 'male_leave_work' if scenario == 'leave_work' else scenario
    scenario_devices = devices_data.get('scenario_device_mapping', {}).get(scenario_key, [])
    
    # 构建设备信息摘要
    device_info_list = []
    for device_id in scenario_devices:
        category_key = devices_data.get('device_types', {}).get(device_id)
        if not category_key:
            continue
        
        category = devices_data.get('device_categories', {}).get(category_key, {})
        device_info = category.get('devices', {}).get(device_id, {})
        
        device_info_list.append({
            'device_id': device_id,
            'name': device_info.get('name', ''),
            'description': device_info.get('description', ''),
            'category': category.get('name', ''),
            'capabilities': device_info.get('capabilities', {})
        })
    
    # 构建场景描述和模型提示词
    scenario_context = f"场景ID: {scenario}"
    if scenario_desc:
        scenario_context += f"\n场景描述: {scenario_desc}"
    
    # 构建模型提示词
    prompt = f"""你是一个智能家居设备推荐专家。请根据用户特点和当前场景，从设备列表中选择最相关的设备。

## 用户特点
{user_persona}

## 当前场景
{scenario_context}

## 可选设备列表
{json.dumps(device_info_list, ensure_ascii=False, indent=2)}

## 任务要求
1. 分析用户的年龄、生活习惯、健康状况、兴趣偏好等特点
2. 结合当前场景（如上班离家、下班回家、访客来访等）
3. 从设备列表中选择用户最可能使用或关注的设备
4. 为每个选中的设备给出相关度评分（0.0-1.0）和选择理由

## 输出格式
请以JSON格式输出，包含以下字段：
{{
  "selected_devices": [
    {{
      "device_id": "设备ID",
      "relevance_score": 相关度评分(0.0-1.0),
      "reason": "选择理由"
    }}
  ]
}}

注意：
- 只选择相关度评分 >= 0.6 的设备
- 相关度评分要基于用户特点和场景合理性
- 最多选择5个设备
- 只输出JSON，不要有其他内容"""

    # 调用模型
    response = ""
    try:
        response = run_chatgpt(prompt, num_gen=1, num_tokens_request=1000, temperature=0.7)
        
        # 解析模型输出
        response = response.strip()
        # 移除可能的markdown代码块标记
        if response.startswith('```'):
            response = response.split('\n', 1)[1] if '\n' in response else response[3:]
        if response.endswith('```'):
            response = response.rsplit('```', 1)[0]
        
        result = json.loads(response)
        
        # 构建返回结果
        selected_devices = {}
        for item in result.get('selected_devices', []):
            device_id = item.get('device_id')
            if not device_id:
                continue
            
            # 从设备库中获取完整信息
            category_key = devices_data.get('device_types', {}).get(device_id)
            if category_key:
                category = devices_data.get('device_categories', {}).get(category_key, {})
                device_info = category.get('devices', {}).get(device_id, {})
                
                selected_devices[device_id] = {
                    'name': device_info.get('name', ''),
                    'category': category.get('name', ''),
                    'relevance_score': item.get('relevance_score', 0.6),
                    'reason': item.get('reason', ''),
                    'capabilities': device_info.get('capabilities', {}),
                    'typical_events': device_info.get('typical_events', [])
                }
        
        # 按相关度排序
        selected_devices = dict(sorted(selected_devices.items(), key=lambda x: x[1]['relevance_score'], reverse=True))
        
        logging.info(f"Selected {len(selected_devices)} devices for user based on persona and scenario: {list(selected_devices.keys())}")
        
        return selected_devices
        
    except json.JSONDecodeError as e:
        logging.error(f"Failed to parse model response as JSON: {e}")
        logging.error(f"Response was: {response}")
        return {}
    except Exception as e:
        logging.error(f"Error in device selection: {e}")
        return {}
