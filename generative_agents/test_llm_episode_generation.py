#!/usr/bin/env python
"""
测试设备事件生成功能。

验证 generate_single_day_episode_rule_based 函数是否正常工作。
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
from datetime import date, timedelta, datetime
from generative_agents.device_events_utils import (
    generate_single_day_episode_rule_based,
    generate_scenario_device_episodes,
    SCENE_TEMPLATES,
    PERSON_ID_MAPPING,
    get_person_ids_from_household
)

logging.basicConfig(level=logging.INFO)


def test_rule_based_generation():
    """测试规则模板生成"""
    logging.info("Testing rule-based episode generation...")
    
    # 准备测试参数
    scenario = 'family_return'
    episode_date = datetime.now().date()
    day_offset = 0
    template = SCENE_TEMPLATES.get(scenario)
    core_events = template.get('core_events', [])
    noise_events = template.get('noise_events', [])
    time_window = template.get('time_window', {})
    default_subject = template.get('default_subject', 'dad')
    default_home = template.get('default_home', 'home_1')
    
    # 准备家庭画像
    household_profile = {
        'members': {
            'dad': {'name': '父亲', 'role': '男主人', 'age': 40},
            'mom': {'name': '母亲', 'role': '女主人', 'age': 38},
            'child': {'name': '孩子', 'role': '子女', 'age': 10}
        }
    }
    
    person_ids = get_person_ids_from_household(household_profile)
    
    # 生成 episode
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
        logging.info("✓ Rule-based episode generation successful!")
        logging.info(f"  Episode ID: {episode.get('episode_id')}")
        logging.info(f"  Daily State Description: {episode.get('daily_state_description', 'N/A')[:100]}...")
        logging.info(f"  Number of Events: {len(episode.get('annotated_events', []))}")
        
        # 验证必需字段
        required_fields = ['episode_id', 'home_id', 'scene', 'subject_id', 'confidence', 
                          'date', 'daily_state_description', 'annotated_events']
        missing_fields = [field for field in required_fields if field not in episode]
        
        if missing_fields:
            logging.warning(f"  Missing fields: {missing_fields}")
        else:
            logging.info("  ✓ All required fields present")
        
        # 验证事件格式
        events = episode.get('annotated_events', [])
        if events:
            first_event = events[0]
            if 'event' in first_event and 'state_snapshot' in first_event:
                logging.info("  ✓ Event format correct")
                
                # 检查 state_snapshot 是否包含 space_occupancy
                if 'space_occupancy' in first_event['state_snapshot']:
                    logging.info("  ✓ space_occupancy field present")
                else:
                    logging.warning("  ✗ space_occupancy field missing")
            else:
                logging.warning("  ✗ Event format incorrect")
        
        return episode
    else:
        logging.error("✗ Rule-based episode generation failed!")
        return None


def test_multi_day_generation():
    """测试连续多日生成"""
    logging.info("\nTesting multi-day episode generation...")
    
    # 准备测试参数
    scenario = 'family_return'
    num_days = 3  # 只生成3天用于测试
    
    household_profile = {
        'members': {
            'dad': {'name': '父亲', 'role': '男主人', 'age': 40},
            'mom': {'name': '母亲', 'role': '女主人', 'age': 38},
            'child': {'name': '孩子', 'role': '子女', 'age': 10}
        }
    }
    
    device_file = './data/devices/home_devices.json'
    
    # 生成 episodes（使用规则模板）
    episodes = generate_scenario_device_episodes(
        scenario=scenario,
        num_days=num_days,
        household_profile=household_profile,
        device_file=device_file,
        use_llm=False  # 使用规则模板
    )
    
    if episodes:
        logging.info(f"✓ Multi-day generation successful! Generated {len(episodes)} episodes")
        
        # 验证每个 episode
        for i, episode in enumerate(episodes):
            logging.info(f"\n  Episode {i+1}:")
            logging.info(f"    ID: {episode.get('episode_id')}")
            logging.info(f"    Date: {episode.get('date')}")
            logging.info(f"    Events: {len(episode.get('annotated_events', []))}")
            
            if 'daily_state_description' in episode:
                logging.info(f"    State: {episode.get('daily_state_description', '')[:50]}...")
        
        return episodes
    else:
        logging.error("✗ Multi-day generation failed!")
        return None


if __name__ == '__main__':
    logging.info("=" * 60)
    logging.info("Device Events Generation Test")
    logging.info("=" * 60)
    
    # 测试规则模板生成
    rule_episode = test_rule_based_generation()
    
    # 测试连续多日生成
    multi_episodes = test_multi_day_generation()
    
    logging.info("\n" + "=" * 60)
    logging.info("Test Summary")
    logging.info("=" * 60)
    
    results = {
        'Rule-based Single Day': rule_episode is not None,
        'Multi-day Generation': multi_episodes is not None
    }
    
    for test_name, passed in results.items():
        status = "✓ PASSED" if passed else "✗ FAILED"
        logging.info(f"{test_name}: {status}")
    
    all_passed = all(results.values())
    if all_passed:
        logging.info("\n✓ All tests passed!")
        sys.exit(0)
    else:
        logging.error("\n✗ Some tests failed!")
        sys.exit(1)