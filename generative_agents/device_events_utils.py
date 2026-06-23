"""
设备事件生成相关工具函数。

根据场景和对话内容，使用模型生成设备行为记录。
支持连续多日场景事件生成（episodes）。
"""

import os
import json
import logging
import copy
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

def canonicalize_scenario(scenario):
    return scenario


SCENE_TEMPLATES = {
    "family_return": {
        "name": "家庭成员下班回家",
        "description": "家庭成员下班回家，门锁、门口摄像头、灯光、空调、窗帘和影音设备根据当晚状态联动",
        "default_subject": "dad",
        "default_home": "home_1",
        "time_window": {
            "normal": {"start": "17:00", "end": "22:30"},
            "late": {"start": "23:00", "end": "01:00"}
        },
        "primary_events": [
            {"event_type": "unlock_main_door", "predicate": "opened", "object_id": "door_main",
             "description": "回家时打开大门"},
            {"event_type": "close_main_door", "predicate": "closed", "object_id": "door_main",
             "description": "进门后关上大门"}
        ],
        "related_events": [
            {"subject_id": "home_system", "event_type": "door_camera_face_recognized", "predicate": "recognized", "object_id": "door_camera",
             "description": "门口摄像头识别到回家的家庭成员"},
            {"event_type": "turn_on_living_room_light", "predicate": "activated", "object_id": "light_living_room",
             "description": "客厅光线较暗且准备进入客厅时打开客厅灯"},
            {"event_type": "turn_on_hallway_light", "predicate": "activated", "object_id": "light_hallway",
             "description": "玄关光线较暗时打开玄关灯"},
            {"event_type": "turn_on_living_room_ac", "predicate": "activated", "object_id": "ac_living_room",
             "description": "客厅温度不舒适时打开客厅空调"},
            {"event_type": "turn_on_living_room_tv", "predicate": "activated", "object_id": "tv_living_room",
             "description": "回到客厅休息时打开电视"},
            {"event_type": "close_living_room_curtain", "predicate": "closed", "object_id": "curtain_living_room",
             "description": "夜间回家后关闭客厅窗帘"},
            {"event_type": "start_fresh_air", "predicate": "activated", "object_id": "fresh_air_system",
             "description": "空气质量较差时启动新风系统"},
            {"event_type": "speaker_welcome", "predicate": "announced", "object_id": "smart_speaker",
             "description": "智能音箱播报回家欢迎或提醒"}
        ],
        "core_events": [
            {"subject_id": "home_system", "event_type": "door_camera_motion", "predicate": "detected", "object_id": "door_camera",
             "description": "门口摄像头检测到有人靠近"},
            {"event_type": "unlock_main_door", "predicate": "opened", "object_id": "door_main",
             "description": "打开大门"},
            {"event_type": "close_main_door", "predicate": "closed", "object_id": "door_main",
             "description": "关上大门"},
            {"subject_id": "home_system", "event_type": "lock_main_door", "predicate": "locked", "object_id": "door_main",
             "description": "进门后自动落锁"}
        ],
        "noise_events": [
            {"event_type": "living_room_occupied", "predicate": "detected", "object_id": "motion_sensor",
             "description": "客厅有人活动，影响是否打开客厅灯和电视"},
            {"event_type": "light_sensor_dark", "predicate": "detected", "object_id": "light_sensor",
             "description": "室内光照偏暗，可能触发开灯"},
            {"event_type": "bedroom_ac_already_on", "predicate": "activated", "object_id": "ac_bedroom",
             "description": "卧室空调已开启，回家后不重复控制"},
            {"event_type": "tv_bedroom_on", "predicate": "activated", "object_id": "tv_bedroom",
             "description": "卧室电视开着，说明卧室可能有人"}
        ]
    },
    "leave_work": {
        "name": "男主人上班离家",
        "description": "家庭成员早上上班离家，大门、灯光、空调、电视和安防设备根据房间占用状态联动",
        "default_subject": "dad",
        "default_home": "home_1",
        "time_window": {
            "normal": {"start": "07:00", "end": "09:00"}
        },
        "primary_events": [
            {"event_type": "open_main_door", "predicate": "opened", "object_id": "door_main",
             "description": "上班离家时打开大门"},
            {"event_type": "close_main_door", "predicate": "closed", "object_id": "door_main",
             "description": "上班离家后关上大门"}
        ],
        "related_events": [
            {"subject_id": "home_system", "event_type": "lock_main_door", "predicate": "locked", "object_id": "door_main",
             "description": "男主人离家后锁门"},
            {"subject_id": "home_system", "event_type": "turn_off_living_room_light", "predicate": "deactivated", "object_id": "light_living_room",
             "description": "客厅无人时关闭客厅灯"},
            {"subject_id": "home_system", "event_type": "turn_off_living_room_tv", "predicate": "deactivated", "object_id": "tv_living_room",
             "description": "客厅无人时关闭电视"},
            {"subject_id": "home_system", "event_type": "turn_off_living_room_ac", "predicate": "deactivated", "object_id": "ac_living_room",
             "description": "客厅无人时关闭客厅空调"},
            {"subject_id": "home_system", "event_type": "turn_off_bedroom_light", "predicate": "deactivated", "object_id": "light_bedroom",
             "description": "卧室无人时关闭卧室灯"},
            {"subject_id": "home_system", "event_type": "turn_off_bedroom_ac", "predicate": "deactivated", "object_id": "ac_bedroom",
             "description": "卧室无人时关闭卧室空调"},
            {"subject_id": "home_system", "event_type": "close_living_room_curtain", "predicate": "closed", "object_id": "curtain_living_room",
             "description": "离家前根据日晒或隐私需求关闭客厅窗帘"},
            {"subject_id": "home_system", "event_type": "speaker_commute_reminder", "predicate": "announced", "object_id": "smart_speaker",
             "description": "智能音箱播报通勤或天气提醒"}
        ],
        "core_events": [
            {"event_type": "open_main_door", "predicate": "opened", "object_id": "door_main",
             "description": "打开大门准备离家"},
            {"event_type": "close_main_door", "predicate": "closed", "object_id": "door_main",
             "description": "离家后关上大门"},
            {"event_type": "lock_main_door", "predicate": "locked", "object_id": "door_main",
             "description": "离家后锁门"}
        ],
        "noise_events": [
            {"event_type": "living_room_occupied", "predicate": "detected", "object_id": "motion_sensor",
             "description": "客厅仍有人活动，则不关闭客厅灯、电视或空调"},
            {"event_type": "bedroom_occupied", "predicate": "detected", "object_id": "motion_sensor",
             "description": "卧室仍有人休息，则不关闭卧室灯或空调"},
            {"event_type": "coffee_machine_brewing", "predicate": "activated", "object_id": "coffee_machine",
             "description": "咖啡机仍在工作，说明厨房区域有人"},
            {"event_type": "wifi_phone_offline", "predicate": "detected", "object_id": "wifi_router",
             "description": "手机离开家庭 WiFi，辅助判断主体已经离家"}
        ]
    },
    "child_return": {
        "name": "小孩放学回家",
        "description": "小孩放学回家，门口识别、玄关灯、书房灯、空调和影音设备根据作业或休息状态联动",
        "default_subject": "child",
        "default_home": "home_1",
        "time_window": {
            "normal": {"start": "16:30", "end": "18:30"}
        },
        "primary_events": [
            {"event_type": "child_unlock_main_door", "predicate": "opened", "object_id": "door_main",
             "description": "小孩回家时打开大门"},
            {"event_type": "child_close_main_door", "predicate": "closed", "object_id": "door_main",
             "description": "小孩进门后关上大门"}
        ],
        "related_events": [
            {"subject_id": "home_system", "event_type": "door_camera_face_recognized", "predicate": "recognized", "object_id": "door_camera",
             "description": "门口摄像头识别到小孩到家"},
            {"subject_id": "home_system", "event_type": "turn_on_hallway_light", "predicate": "activated", "object_id": "light_hallway",
             "description": "玄关偏暗时打开玄关灯"},
            {"subject_id": "home_system", "event_type": "turn_on_study_light", "predicate": "activated", "object_id": "light_study",
             "description": "小孩进入书房学习前打开书房灯"},
            {"subject_id": "home_system", "event_type": "turn_on_living_room_tv", "predicate": "activated", "object_id": "tv_living_room",
             "description": "小孩选择在客厅休息时打开电视"},
            {"subject_id": "home_system", "event_type": "turn_on_living_room_ac", "predicate": "activated", "object_id": "ac_living_room",
             "description": "室温不舒适且客厅有人时打开客厅空调"},
            {"subject_id": "home_system", "event_type": "speaker_homework_reminder", "predicate": "announced", "object_id": "smart_speaker",
             "description": "智能音箱提醒写作业或喝水"}
        ],
        "core_events": [
            {"subject_id": "home_system", "event_type": "door_camera_motion", "predicate": "detected", "object_id": "door_camera",
             "description": "门口摄像头检测到有人靠近"},
            {"event_type": "child_unlock_main_door", "predicate": "opened", "object_id": "door_main",
             "description": "小孩打开大门"},
            {"event_type": "child_close_main_door", "predicate": "closed", "object_id": "door_main",
             "description": "小孩关上大门"}
        ],
        "noise_events": [
            {"event_type": "grandpa_watching_tv", "predicate": "activated", "object_id": "tv_living_room",
             "description": "客厅电视已经打开，说明可能有老人正在客厅看电视"},
            {"event_type": "study_light_already_on", "predicate": "activated", "object_id": "light_study",
             "description": "书房灯已经打开，可能有人在书房"},
            {"event_type": "light_sensor_dark", "predicate": "detected", "object_id": "light_sensor",
             "description": "下午光照不足，影响是否打开书房灯"}
        ]
    },
    "elderly_outdoor": {
        "name": "老人独自外出",
        "description": "老人独自外出，门锁、门口摄像头、玄关灯、空调和新风系统根据安全与舒适状态联动",
        "default_subject": "grandpa",
        "default_home": "home_1",
        "time_window": {
            "normal": {"start": "08:30", "end": "11:30"}
        },
        "primary_events": [
            {"event_type": "elderly_open_main_door", "predicate": "opened", "object_id": "door_main",
             "description": "老人外出时打开大门"},
            {"event_type": "elderly_close_main_door", "predicate": "closed", "object_id": "door_main",
             "description": "老人外出后关上大门"}
        ],
        "related_events": [
            {"subject_id": "home_system", "event_type": "lock_main_door", "predicate": "locked", "object_id": "door_main",
             "description": "老人外出后自动锁门"},
            {"subject_id": "home_system", "event_type": "door_camera_motion", "predicate": "detected", "object_id": "door_camera",
             "description": "门口摄像头检测老人离家方向"},
            {"subject_id": "home_system", "event_type": "turn_on_hallway_light", "predicate": "activated", "object_id": "light_hallway",
             "description": "玄关偏暗时打开玄关灯"},
            {"subject_id": "home_system", "event_type": "turn_off_living_room_ac", "predicate": "deactivated", "object_id": "ac_living_room",
             "description": "客厅无人时关闭客厅空调"},
            {"subject_id": "home_system", "event_type": "start_fresh_air", "predicate": "activated", "object_id": "fresh_air_system",
             "description": "老人离家前空气质量较差时启动新风系统"},
            {"subject_id": "home_system", "event_type": "speaker_safety_reminder", "predicate": "announced", "object_id": "smart_speaker",
             "description": "智能音箱播报天气或安全提醒"}
        ],
        "core_events": [
            {"event_type": "elderly_open_main_door", "predicate": "opened", "object_id": "door_main",
             "description": "老人打开大门"},
            {"event_type": "elderly_close_main_door", "predicate": "closed", "object_id": "door_main",
             "description": "老人关上大门"}
        ],
        "noise_events": [
            {"event_type": "living_room_occupied", "predicate": "detected", "object_id": "motion_sensor",
             "description": "客厅仍有人活动，影响是否关闭客厅设备"},
            {"event_type": "air_quality_poor", "predicate": "detected", "object_id": "air_quality_sensor",
             "description": "空气质量较差，可能启动新风系统"},
            {"event_type": "temp_low", "predicate": "detected", "object_id": "temp_humidity_sensor",
             "description": "温度偏低，可能影响老人外出提醒"}
        ]
    },
    "visitor_arrival": {
        "name": "访客到家",
        "description": "访客到家，门口摄像头、门铃、门锁、玄关灯、窗帘和智能音箱联动",
        "default_subject": "visitor",
        "default_home": "home_1",
        "time_window": {
            "normal": {"start": "10:00", "end": "21:00"}
        },
        "primary_events": [
            {"event_type": "visitor_arrival", "predicate": "arrived", "object_id": "door_bell",
             "description": "访客到家"}
        ],
        "related_events": [
            {"subject_id": "home_system", "event_type": "door_camera_motion", "predicate": "detected", "object_id": "door_camera",
             "description": "门口摄像头检测到访客靠近"},
            {"subject_id": "home_system", "event_type": "door_bell_ring", "predicate": "rang", "object_id": "door_bell",
             "description": "访客按响门铃"},
            {"subject_id": "home_system", "event_type": "remote_unlock_main_door", "predicate": "opened", "object_id": "door_main",
             "description": "主人远程开门或使用临时密码开门"},
            {"subject_id": "home_system", "event_type": "turn_on_hallway_light", "predicate": "activated", "object_id": "light_hallway",
             "description": "玄关偏暗时打开玄关灯"},
            {"subject_id": "home_system", "event_type": "speaker_visitor_notice", "predicate": "announced", "object_id": "smart_speaker",
             "description": "智能音箱播报访客到达提醒"}
        ],
        "core_events": [
            {"subject_id": "home_system", "event_type": "door_camera_motion", "predicate": "detected", "object_id": "door_camera",
             "description": "门口摄像头检测到访客"},
            {"subject_id": "home_system", "event_type": "door_bell_ring", "predicate": "rang", "object_id": "door_bell",
             "description": "门铃响起"},
            {"subject_id": "home_system", "event_type": "remote_unlock_main_door", "predicate": "opened", "object_id": "door_main",
             "description": "打开大门"}
        ],
        "noise_events": [
            {"event_type": "living_room_occupied", "predicate": "detected", "object_id": "motion_sensor",
             "description": "客厅有人，可能由家庭成员接待访客"},
            {"event_type": "curtain_living_room_open", "predicate": "opened", "object_id": "curtain_living_room",
             "description": "客厅窗帘打开，适合接待访客"},
            {"event_type": "door_camera_unrecognized", "predicate": "detected", "object_id": "door_camera",
             "description": "门口摄像头检测到未识别人员，影响开门方式"}
        ]
    },
    "all_leave_arm": {
        "name": "全员离家布防",
        "description": "全员离家后，门锁、灯光、空调、新风、摄像头和安防系统进入离家状态",
        "default_subject": "home_system",
        "default_home": "home_1",
        "time_window": {
            "normal": {"start": "08:30", "end": "09:30"}
        },
        "primary_events": [
            {"event_type": "arm_away_mode", "predicate": "activated", "object_id": "security_system",
             "description": "全员离家布防"}
        ],
        "related_events": [
            {"subject_id": "home_system", "event_type": "lock_main_door", "predicate": "locked", "object_id": "door_main",
             "description": "全员离家后锁门"},
            {"subject_id": "home_system", "event_type": "turn_off_hallway_light", "predicate": "deactivated", "object_id": "light_hallway",
             "description": "玄关无人时关闭玄关灯"},
            {"subject_id": "home_system", "event_type": "turn_off_living_room_light", "predicate": "deactivated", "object_id": "light_living_room",
             "description": "客厅无人时关闭客厅灯"},
            {"subject_id": "home_system", "event_type": "turn_off_bedroom_light", "predicate": "deactivated", "object_id": "light_bedroom",
             "description": "卧室无人时关闭卧室灯"},
            {"subject_id": "home_system", "event_type": "turn_off_living_room_ac", "predicate": "deactivated", "object_id": "ac_living_room",
             "description": "客厅无人时关闭客厅空调"},
            {"subject_id": "home_system", "event_type": "turn_off_bedroom_ac", "predicate": "deactivated", "object_id": "ac_bedroom",
             "description": "卧室无人时关闭卧室空调"},
            {"subject_id": "home_system", "event_type": "stop_fresh_air", "predicate": "deactivated", "object_id": "fresh_air_system",
             "description": "全员离家后关闭或降低新风系统"},
            {"subject_id": "home_system", "event_type": "camera_record", "predicate": "recording", "object_id": "security_camera",
             "description": "安防摄像头开始录像或进入警戒"}
        ],
        "core_events": [
            {"event_type": "lock_main_door", "predicate": "locked", "object_id": "door_main",
             "description": "锁门"},
            {"event_type": "security_on", "predicate": "activated", "object_id": "security_system",
             "description": "启动安防系统"}
        ],
        "noise_events": [
            {"event_type": "motion_sensor_clear", "predicate": "cleared", "object_id": "motion_sensor",
             "description": "室内移动传感器无活动，支持布防"},
            {"event_type": "wifi_all_phones_offline", "predicate": "detected", "object_id": "wifi_router",
             "description": "家庭成员手机均离线，辅助判断全员离家"},
            {"event_type": "air_quality_good", "predicate": "detected", "object_id": "air_quality_sensor",
             "description": "空气质量正常，离家后可关闭新风"}
        ]
    },
    "anomaly_detection": {
        "name": "异常活动检测",
        "description": "安防状态下检测到异常活动，门口摄像头、移动传感器、摄像头录像和音箱提醒联动",
        "default_subject": "home_system",
        "default_home": "home_1",
        "time_window": {
            "normal": {"start": "00:00", "end": "24:00"}
        },
        "primary_events": [
            {"event_type": "anomaly_detected", "predicate": "detected", "object_id": "motion_sensor",
             "description": "检测到异常活动"}
        ],
        "related_events": [
            {"subject_id": "home_system", "event_type": "door_camera_motion", "predicate": "detected", "object_id": "door_camera",
             "description": "门口摄像头检测到异常移动"},
            {"subject_id": "home_system", "event_type": "camera_record", "predicate": "recording", "object_id": "security_camera",
             "description": "安防摄像头开始录像"},
            {"subject_id": "home_system", "event_type": "speaker_alarm", "predicate": "announced", "object_id": "smart_speaker",
             "description": "智能音箱发出警示或提醒"},
            {"subject_id": "home_system", "event_type": "lock_main_door", "predicate": "locked", "object_id": "door_main",
             "description": "确认大门处于锁定状态"}
        ],
        "core_events": [
            {"event_type": "motion_detected", "predicate": "detected", "object_id": "motion_sensor",
             "description": "检测到移动"},
            {"event_type": "camera_record", "predicate": "recording", "object_id": "security_camera",
             "description": "摄像头录制"}
        ],
        "noise_events": [
            {"event_type": "door_camera_unrecognized", "predicate": "detected", "object_id": "door_camera",
             "description": "门口摄像头检测到未识别人员，可能触发异常"},
            {"event_type": "wifi_unknown_device", "predicate": "detected", "object_id": "wifi_router",
             "description": "家庭 WiFi 发现陌生设备，辅助异常判断"},
            {"event_type": "motion_sensor_false_positive", "predicate": "detected", "object_id": "motion_sensor",
             "description": "室内短暂移动，可能是误报背景"}
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

DEFAULT_ROOM_DEVICE_LAYOUT = {
    "entrance": ["door_main", "door_bell", "door_camera", "light_hallway"],
    "living_room": [
        "light_living_room", "ac_living_room", "tv_living_room", "curtain_living_room",
        "motion_sensor", "light_sensor", "air_quality_sensor", "fresh_air_system", "smart_speaker"
    ],
    "bedroom": ["light_bedroom", "ac_bedroom", "tv_bedroom", "curtain_bedroom", "temp_humidity_sensor"],
    "study": ["light_study"],
    "bathroom": ["light_bathroom"],
    "kitchen": ["coffee_machine"]
}

# 设备状态机
DEVICE_STATES = {
    "wifi_router": ["online", "offline", "unknown_device_detected"],
    "door_camera": ["idle", "motion_detected", "face_recognized", "unrecognized", "recording"],
    "door_main": ["open", "closed", "locked"],
    "door_bedroom": ["open", "closed", "locked"],
    "door_bell": ["ringing", "silent"],
    "temp_humidity_sensor": ["normal", "temp_high", "temp_low", "humidity_high", "humidity_low"],
    "light_sensor": ["bright", "dim", "dark"],
    "air_quality_sensor": ["good", "moderate", "poor"],
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
    "fresh_air_system": ["on", "off", "auto", "low", "medium", "high"],
    "security_system": ["armed", "disarmed"],
    "motion_sensor": ["detected", "clear"],
    "security_camera": ["recording", "idle"],
    "coffee_machine": ["brewing", "idle"],
    "smart_speaker": ["idle", "speaking", "playing", "listening"]
}

PERSON_ROOM_STATUS_SCHEMA = {
    "outside": ["outside", "commuting", "arriving", "left_home"],
    "entrance": ["arriving", "leaving", "waiting", "passing_through"],
    "living_room": ["watching_tv", "resting", "chatting", "playing", "awake"],
    "kitchen": ["cooking", "eating", "preparing_meal", "cleaning", "awake"],
    "bedroom": ["sleeping", "resting", "getting_ready", "awake"],
    "study": ["studying", "working", "reading", "awake"],
    "bathroom": ["washing", "getting_ready"],
    "balcony": ["resting", "watering_plants"],
}

# ==================== LLM 单日 Episode 生成 Prompt 模板 ====================

LLM_STATE_DESCRIPTION_PROMPT = """你是一个智能家居系统分析师。根据给定的家庭画像和场景，先判断当天该场景是否应该发生，并生成当天该场景下的家庭状态描述。

## 场景信息
场景类型: {scenario}
场景描述: {scenario_desc}
当前场景主体: {subject_id}
日期: {episode_date}
计划发生时间: {planned_scene_time}

## 当天已生成的其他情景描述
{previous_scenario_descriptions}

## 家庭成员
{members_info}

## 家庭关系
{relations_info}

## 房间与设备布局
{room_device_layout}

## 人物房间状态枚举
{person_room_status_schema}

## 设备状态枚举
{device_state_schema}

## 可控设备
{devices_info}

## 随机抽样上下文
本日重点人物: {sampled_persons}
本日重点设备: {sampled_devices}

## 任务要求
1. 判断当天该场景是否应该发生：
   - 如果是上班离家/下班回家，休息日、请假日、居家办公日可以不发生
   - 如果场景主体当天不在家或不符合角色作息，也可以不发生
2. 如果发生，生成 daily_state_description，描述当前场景开始前后的家庭状态：
   - 家庭成员的位置和活动状态
   - 每个相关房间是否有人，以及是谁
   - 主要设备的当前状态
   - 环境氛围（如安静、热闹、温馨等）
   - 任何特殊情况（如休息日、请假、加班、有访客等）
3. 如果不发生，daily_state_description 仍需解释不发生的原因。

## 输出格式
请严格按照以下 JSON 格式输出，不要包含其他解释文字：

{{
    "scenario_should_happen": true,
    "scenario_time": "2022-03-16T08:00:00+08:00",
    "skip_reason": "",
    "daily_state_description": "当天该情景下的家庭状态自然语言描述，50-120字，必须写明具体小时",
    "sampled_context": {{
        "persons": ["本日重点人物ID列表"],
        "devices": ["本日重点设备ID列表"]
    }}
}}

## 重要约束
- 输出必须是合法的 JSON 格式
- scenario_should_happen 必须是布尔值
- scenario_time 使用 ISO8601 格式，小时应与计划发生时间一致
- daily_state_description 必须是自然语言描述
- daily_state_description 不能与当天已生成的其他情景描述出现人物位置、设备状态或时间顺序冲突
- daily_state_description 中提到的设备状态应来自“设备状态枚举”

请生成场景发生判断和家庭状态描述："""


LLM_EVENT_ITEM_PROMPT = """你是一个智能家居系统分析师。请基于当天家庭状态描述和已经生成的事件，判断候选事件是否应该成为下一个 annotated_events item。

## 场景信息
场景类型: {scenario}
场景描述: {scenario_desc}
当前场景主体: {subject_id}
日期: {episode_date}

## 家庭成员
{members_info}

## 家庭关系
{relations_info}

## 房间与设备布局
{room_device_layout}

## 人物房间状态枚举
{person_room_status_schema}

## 设备状态枚举
{device_state_schema}

## 可控设备
{devices_info}

## 当天家庭状态描述
{daily_state_description}

## 已生成的 annotated_events
{previous_events}

## 当前候选事件
{candidate_event_info}

## 任务要求
1. 只判断“当前候选事件”是否应该在该场景下发生。
2. 如果不应该发生，输出 should_generate=false，并说明 reason。
3. 如果应该发生，输出 should_generate=true，并生成一个 annotated_event。
4. annotated_event.event 的 subject_id、predicate、object_id、attributes.event_type 必须和当前候选事件完全一致。
5. state_snapshot 表示该候选事件发生前/发生瞬间的全局状态切片，必须与 daily_state_description 和 previous_events 的时间顺序一致。
6. state_snapshot.persons 中每个人的 location 必须来自“人物房间状态枚举”的房间，status 必须来自该房间允许状态。
7. state_snapshot.devices 中每个设备的 state 必须来自“设备状态枚举”。
8. 不要生成候选事件之外的动作拆解细节。

## 输出格式
请严格按照以下 JSON 格式输出，不要包含其他解释文字：

{{
    "should_generate": true,
    "reason": "为什么该候选事件在当天状态下应该/不应该发生",
    "annotated_event": {{
        "event": {{
            "subject_id": "home_system",
            "predicate": "deactivated",
            "object_id": "light_living_room",
            "attributes": {{
                "event_type": "turn_off_living_room_light",
                "description": "客厅无人时关闭客厅灯"
            }}
        }},
        "state_snapshot": {{
            "timestamp": "2022-03-16T18:30:00+08:00",
            "persons": {{
                "dad": {{"status": "leaving", "location": "entrance"}},
                "mom": {{"status": "cooking", "location": "kitchen"}}
            }},
            "devices": {{
                "light_living_room": {{"state": "on"}},
                "tv_living_room": {{"state": "off"}}
            }},
            "space_occupancy": {{
                "entrance": ["dad"],
                "kitchen": ["mom"],
                "living_room": []
            }}
        }}
    }}
}}

## 重要约束
- timestamp 使用 ISO8601 格式，时间必须连续递增
- 所有设备 ID 必须来自可控设备列表
- state_snapshot 必须包含 persons、devices、space_occupancy 三个字段
- 人物 ID 必须来自家庭成员列表
- 人物 status/location 必须来自“人物房间状态枚举”
- 设备 state 必须来自“设备状态枚举”
- should_generate=false 时 annotated_event 可以为 null
- 输出必须是合法的 JSON 格式

请判断并生成当前候选事件 item："""


LLM_NEXT_EVENT_PROMPT = """你是一个智能家居系统分析师。请基于当天情景描述和已经生成的事件，生成当前情景下的下一个 annotated_events item，或判断当前情景事件已经结束。

## 场景信息
场景类型: {scenario}
场景描述: {scenario_desc}
当前场景主体: {subject_id}
日期: {episode_date}
情景发生时间: {scenario_time}

## 家庭成员
{members_info}

## 家庭关系
{relations_info}

## 房间与设备布局
{room_device_layout}

## 人物房间状态枚举
{person_room_status_schema}

## 设备状态枚举
{device_state_schema}

## 可控设备
{devices_info}

## 当天所有已生成的情景描述
{all_scenario_descriptions}

## 当前情景描述
{daily_state_description}

## 当前情景已生成的 annotated_events
{previous_events}

## 当前情景允许生成的事件集合
{allowed_events_info}

## 任务要求
1. 每次只输出一个“下一个事件”；如果当前情景已经结束，输出 should_continue=false。
2. 下一个事件必须来自“当前情景允许生成的事件集合”，不要生成集合之外的泛化事件或过程细节。
3. 事件顺序由当前情景描述、已生成事件和 state_snapshot 推演决定，例如离家可能是开门、关灯、关门，也可能先关灯再开门关门。
4. state_snapshot 表示该事件发生前/发生瞬间的全局状态切片，必须与当前情景描述和已生成事件连续一致。
5. state_snapshot.persons 中每个人的 location 必须来自“人物房间状态枚举”的房间，status 必须来自该房间允许状态。
6. state_snapshot.devices 中每个设备的 state 必须来自“设备状态枚举”。
7. 不要重复生成已经出现过的相同 subject_id/predicate/object_id/event_type 事件。

## 输出格式
请严格按照以下 JSON 格式输出，不要包含其他解释文字：

{{
    "should_continue": true,
    "reason": "为什么继续生成该事件，或为什么当前情景已经结束",
    "annotated_event": {{
        "event": {{
            "subject_id": "home_system",
            "predicate": "deactivated",
            "object_id": "light_living_room",
            "attributes": {{
                "event_type": "turn_off_living_room_light",
                "description": "客厅无人时关闭客厅灯"
            }}
        }},
        "state_snapshot": {{
            "timestamp": "2022-03-16T08:05:00+08:00",
            "persons": {{
                "dad": {{"status": "leaving", "location": "entrance"}},
                "mom": {{"status": "cooking", "location": "kitchen"}}
            }},
            "devices": {{
                "door_main": {{"state": "closed"}},
                "light_living_room": {{"state": "on"}}
            }},
            "space_occupancy": {{
                "entrance": ["dad"],
                "kitchen": ["mom"],
                "living_room": []
            }}
        }}
    }}
}}

## 重要约束
- timestamp 使用 ISO8601 格式，必须从情景发生时间开始递增
- event 的 subject_id、predicate、object_id、attributes.event_type 必须来自允许事件集合
- state_snapshot 必须包含 persons、devices、space_occupancy 三个字段
- 人物 ID 必须来自家庭成员列表
- 人物 status/location 必须来自“人物房间状态枚举”
- 设备 state 必须来自“设备状态枚举”
- should_continue=false 时 annotated_event 可以为 null
- 输出必须是合法的 JSON 格式

请生成当前情景的下一个 annotated_event："""

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
                                   household_profile, person_ids, device_file=None, subject_id=None,
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
    default_subject = subject_id or template.get('default_subject', 'dad')
    default_home = template.get('default_home', 'home_1')
    time_window = template.get('time_window', {})
    primary_events = get_primary_events(template)
    allowed_events = get_allowed_scene_events(template)
    
    # 确定时间窗口（是否是晚归日）
    is_late_day = is_late_work_day(day_offset, num_days=7)
    time_range = time_window.get('late' if is_late_day else 'normal', time_window.get('normal'))
    planned_scene_time = build_scene_time(episode_date, time_range)
    
    # 准备家庭成员信息
    members_info = format_members_info(household_profile, person_ids)
    relations_info = format_relations_info(household_profile)
    room_device_layout = format_room_device_layout(household_profile)
    person_room_status_schema = format_person_room_status_schema()
    device_state_schema = format_device_state_schema()
    
    # 准备设备信息
    devices_info = format_devices_info(device_file)
    primary_device_ids = [event.get('object_id') for event in allowed_events if event.get('object_id')]
    if primary_device_ids:
        devices_info += "\n\n## 场景候选事件设备对象\n"
        devices_info += "\n".join(f"- {device_id}: 场景候选事件对象" for device_id in primary_device_ids)
    
    # 随机抽样部分人物和设备
    sampled_persons = random.sample(person_ids, min(3, len(person_ids)))
    available_devices = get_available_device_ids(device_file)
    for device_id in get_layout_device_ids(household_profile):
        if device_id not in available_devices:
            available_devices.append(device_id)
    for device_id in primary_device_ids:
        if device_id not in available_devices:
            available_devices.append(device_id)
    sampled_devices = random.sample(available_devices, min(5, len(available_devices)))
    
    common_prompt_args = {
        "scenario": scenario,
        "scenario_desc": template.get('description', ''),
        "episode_date": episode_date.strftime('%Y-%m-%d'),
        "subject_id": default_subject,
        "members_info": members_info,
        "relations_info": relations_info,
        "room_device_layout": room_device_layout,
        "person_room_status_schema": person_room_status_schema,
        "device_state_schema": device_state_schema,
        "devices_info": devices_info,
    }

    state_prompt = LLM_STATE_DESCRIPTION_PROMPT.format(
        scenario=scenario,
        scenario_desc=template.get('description', ''),
        episode_date=episode_date.strftime('%Y-%m-%d'),
        subject_id=default_subject,
        planned_scene_time=planned_scene_time,
        previous_scenario_descriptions="无",
        members_info=members_info,
        relations_info=relations_info,
        room_device_layout=room_device_layout,
        person_room_status_schema=person_room_status_schema,
        device_state_schema=device_state_schema,
        devices_info=devices_info,
        sampled_persons=', '.join(sampled_persons),
        sampled_devices=', '.join(sampled_devices)
    )
    
    for attempt in range(max_retries):
        try:
            logging.info(f"Generating state description for {episode_date} (attempt {attempt + 1}/{max_retries})")
            
            state_result = run_json_trials_func(state_prompt, num_gen=1, num_tokens_request=1000, temperature=0.8)
            
            state_result = validate_llm_state_result(state_result)
            if not state_result['scenario_should_happen']:
                logging.info(
                    "Skipping episode for %s %s: %s",
                    scenario,
                    episode_date,
                    state_result.get('skip_reason', '')
                )
                return {"_skip": True}

            annotated_events = []
            for candidate_event in allowed_events:
                item_prompt = LLM_EVENT_ITEM_PROMPT.format(
                    **common_prompt_args,
                    daily_state_description=state_result['daily_state_description'],
                    previous_events=json.dumps(annotated_events, ensure_ascii=False, indent=2),
                    candidate_event_info=format_candidate_event_info(candidate_event, default_subject),
                )
                item_result = run_json_trials_func(item_prompt, num_gen=1, num_tokens_request=1600, temperature=0.7)
                annotated_event = validate_llm_event_item_result(
                    item_result,
                    candidate_event,
                    default_subject,
                    person_ids,
                    available_devices,
                    annotated_events,
                )
                if annotated_event:
                    annotated_events.append(annotated_event)
            
            llm_result = {
                'daily_state_description': state_result['daily_state_description'],
                'annotated_events': annotated_events,
            }
            validated_result = validate_llm_episode_result(
                llm_result, 
                scenario, 
                episode_date, 
                default_subject, 
                default_home,
                person_ids,
                available_devices,
                time_range,
                primary_events,
                allowed_events,
                get_household_room_layout(household_profile)
            )
            
            # 添加 sampled_context
            validated_result['sampled_context'] = {
                'persons': state_result.get('sampled_context', {}).get('persons', sampled_persons),
                'devices': state_result.get('sampled_context', {}).get('devices', sampled_devices)
            }
            
            logging.info(f"Successfully generated episode for {episode_date}")
            return validated_result
            
        except Exception as e:
            logging.warning(f"Attempt {attempt + 1} failed for {episode_date}: {e}")
            if attempt == max_retries - 1:
                logging.error(f"All {max_retries} attempts failed for {episode_date}, falling back to rule-based generation")
                return None
    
    return None


def generate_daily_device_episodes(generation_plan, num_days=7, household_profile=None,
                                   scene_templates=None, device_file=None, use_llm=True):
    """
    按天生成所有情景：LLM 路径先生成当天所有情景描述，再逐情景生成事件。
    rule-based 路径回退到原有按情景生成逻辑。
    """
    if scene_templates is None:
        scene_templates = SCENE_TEMPLATES
    if household_profile is None:
        household_profile = {}

    if not use_llm:
        episodes = []
        for plan_item in generation_plan:
            episodes.extend(generate_scenario_device_episodes(
                scenario=plan_item['scenario'],
                num_days=num_days,
                household_profile=household_profile,
                scene_templates=scene_templates,
                device_file=device_file,
                use_llm=False,
                subject_id=plan_item['person_id'],
                subject_profile=plan_item.get('member'),
            ))
        return episodes

    run_json_trials_func = get_run_json_trials()
    if run_json_trials_func is None:
        logging.warning("LLM not available, falling back to rule-based daily generation")
        return generate_daily_device_episodes(
            generation_plan,
            num_days=num_days,
            household_profile=household_profile,
            scene_templates=scene_templates,
            device_file=device_file,
            use_llm=False,
        )

    person_ids = get_person_ids_from_household(household_profile)
    layout_device_ids = get_layout_device_ids(household_profile)
    available_devices = get_available_device_ids(device_file)
    for device_id in layout_device_ids:
        if device_id not in available_devices:
            available_devices.append(device_id)

    members_info = format_members_info(household_profile, person_ids)
    relations_info = format_relations_info(household_profile)
    room_device_layout = format_room_device_layout(household_profile)
    person_room_status_schema = format_person_room_status_schema()
    device_state_schema = format_device_state_schema()
    devices_info = format_devices_info(device_file)

    start_date = datetime.now().date() - timedelta(days=num_days - 1)
    episodes = []

    for day_offset in range(num_days):
        episode_date = start_date + timedelta(days=day_offset)
        contexts = []

        for plan_index, plan_item in enumerate(generation_plan):
            scenario = canonicalize_scenario(plan_item['scenario'])
            template = scene_templates.get(scenario)
            if not template:
                logging.warning("Unknown scenario in generation plan: %s", scenario)
                continue

            default_subject = plan_item.get('person_id') or template.get('default_subject', 'dad')
            default_home = template.get('default_home', 'home_1')
            time_window = template.get('time_window', {})
            is_late_day = is_late_work_day(day_offset, num_days=7)
            time_range = time_window.get('late' if is_late_day else 'normal', time_window.get('normal'))
            planned_scene_time = build_scene_time(episode_date, time_range, fallback_hour=8 + plan_index)
            primary_events = get_primary_events(template)
            allowed_events = get_allowed_scene_events(template)

            for event in allowed_events:
                object_id = event.get('object_id')
                if object_id and object_id not in available_devices:
                    available_devices.append(object_id)
            event_device_ids = list(dict.fromkeys(
                event.get('object_id') for event in allowed_events if event.get('object_id')
            ))
            context_devices_info = devices_info
            if event_device_ids:
                context_devices_info += "\n\n## 场景候选事件设备对象\n"
                context_devices_info += "\n".join(f"- {device_id}: 场景候选事件对象" for device_id in event_device_ids)

            contexts.append({
                'scenario': scenario,
                'scenario_desc': template.get('description', ''),
                'episode_date': episode_date,
                'day_offset': day_offset,
                'template': template,
                'default_subject': default_subject,
                'default_home': default_home,
                'time_range': time_range,
                'planned_scene_time': planned_scene_time,
                'primary_events': primary_events,
                'allowed_events': allowed_events,
                'household_profile': household_profile,
                'person_ids': person_ids,
                'available_devices': available_devices,
                'members_info': members_info,
                'relations_info': relations_info,
                'room_device_layout': room_device_layout,
                'person_room_status_schema': person_room_status_schema,
                'device_state_schema': device_state_schema,
                'devices_info': context_devices_info,
                'subject_profile': plan_item.get('member'),
            })

        contexts.sort(key=lambda item: item['planned_scene_time'])

        generated_descriptions = []
        active_contexts = []
        for context in contexts:
            sampled_persons = random.sample(person_ids, min(3, len(person_ids))) if person_ids else []
            sampled_devices = random.sample(available_devices, min(5, len(available_devices))) if available_devices else []
            state_prompt = LLM_STATE_DESCRIPTION_PROMPT.format(
                scenario=context['scenario'],
                scenario_desc=context['scenario_desc'],
                episode_date=episode_date.strftime('%Y-%m-%d'),
                subject_id=context['default_subject'],
                planned_scene_time=context['planned_scene_time'],
                previous_scenario_descriptions=format_previous_scenario_descriptions(generated_descriptions),
                members_info=members_info,
                relations_info=relations_info,
                room_device_layout=room_device_layout,
                person_room_status_schema=person_room_status_schema,
                device_state_schema=device_state_schema,
                devices_info=context['devices_info'],
                sampled_persons=', '.join(sampled_persons),
                sampled_devices=', '.join(sampled_devices),
            )

            try:
                state_result = run_json_trials_func(
                    state_prompt,
                    num_gen=1,
                    num_tokens_request=1200,
                    temperature=0.8,
                )
                state_result = validate_llm_state_result(state_result)
            except Exception as e:
                logging.warning(
                    "State description generation failed for %s/%s: %s",
                    context['scenario'],
                    episode_date,
                    e,
                )
                continue

            if not state_result['scenario_should_happen']:
                logging.info(
                    "Skipping episode for %s %s: %s",
                    context['scenario'],
                    episode_date,
                    state_result.get('skip_reason', ''),
                )
                continue

            scenario_time = state_result.get('scenario_time') or context['planned_scene_time']
            context['scenario_time'] = scenario_time
            context['daily_state_description'] = state_result['daily_state_description']
            context['sampled_context'] = {
                'persons': state_result.get('sampled_context', {}).get('persons', sampled_persons),
                'devices': state_result.get('sampled_context', {}).get('devices', sampled_devices),
            }
            generated_descriptions.append({
                'scenario': context['scenario'],
                'subject_id': context['default_subject'],
                'scenario_time': scenario_time,
                'daily_state_description': context['daily_state_description'],
            })
            active_contexts.append(context)

        all_descriptions = format_previous_scenario_descriptions(generated_descriptions)
        for context in active_contexts:
            context['all_scenario_descriptions'] = all_descriptions
            episode = generate_scenario_events_from_description_llm(context, run_json_trials_func)
            if not episode:
                logging.warning(
                    "LLM event generation failed for %s/%s, falling back to rule-based episode",
                    context['scenario'],
                    episode_date,
                )
                template = context['template']
                episode = generate_single_day_episode_rule_based(
                    scenario=context['scenario'],
                    episode_date=episode_date,
                    day_offset=day_offset,
                    template=template,
                    core_events=template.get('core_events', []),
                    noise_events=template.get('noise_events', []),
                    time_window=template.get('time_window', {}),
                    default_subject=context['default_subject'],
                    default_home=context['default_home'],
                    household_profile=household_profile,
                    person_ids=person_ids,
                )
            if episode:
                if context.get('subject_profile'):
                    episode['subject_profile'] = context['subject_profile']
                episodes.append(episode)

    logging.info("Generated %s episodes for %s days with daily planning", len(episodes), num_days)
    return episodes


def get_primary_events(template):
    """
    获取场景级必选事件。未配置时返回空列表，避免回退到动作细节。
    """
    primary_events = template.get('primary_events') or []
    if primary_events:
        return [event.copy() for event in primary_events]
    return []


def get_allowed_scene_events(template):
    """
    获取场景期间允许出现的事件：主事件 + 可控设备核心事件 + 由当天家庭状态触发的相关设备事件。
    """
    events = get_primary_events(template)
    known_device_ids = set(DEVICE_STATES.keys())
    for devices in DEFAULT_ROOM_DEVICE_LAYOUT.values():
        known_device_ids.update(devices)
    seen_keys = {
        (event.get('subject_id'), event.get('event_type'), event.get('predicate'), event.get('object_id'))
        for event in events
    }
    for event in template.get('core_events', []):
        if event.get('object_id') not in known_device_ids:
            continue
        event_key = (
            event.get('subject_id'),
            event.get('event_type'),
            event.get('predicate'),
            event.get('object_id'),
        )
        if event_key in seen_keys:
            continue
        events.append(event.copy())
        seen_keys.add(event_key)
    events.extend(event.copy() for event in template.get('related_events', []))
    return events


def build_scene_time(episode_date, time_range, fallback_hour=8):
    """
    根据场景时间窗生成一个 ISO8601 时间。只固定到小时，分钟默认为 00。
    """
    start = (time_range or {}).get('start') if isinstance(time_range, dict) else None
    hour = fallback_hour
    minute = 0
    if isinstance(start, str) and ':' in start:
        try:
            hour, minute = [int(part) for part in start.split(':')[:2]]
        except ValueError:
            hour, minute = fallback_hour, 0
    hour = hour % 24
    scene_datetime = datetime.combine(episode_date, datetime.min.time()).replace(hour=hour, minute=minute)
    return scene_datetime.strftime('%Y-%m-%dT%H:%M:%S+08:00')


def format_previous_scenario_descriptions(descriptions):
    if not descriptions:
        return "无"
    lines = []
    for item in descriptions:
        lines.append(
            "- {time} {scenario}/{subject_id}: {description}".format(
                time=item.get('scenario_time', ''),
                scenario=item.get('scenario', ''),
                subject_id=item.get('subject_id', ''),
                description=item.get('daily_state_description', '')
            )
        )
    return '\n'.join(lines)


def format_allowed_events_info(primary_events, allowed_events, default_subject):
    """
    将主事件和可选相关事件格式化进 LLM prompt。
    """
    lines = []
    primary_keys = {
        (event.get('event_type'), event.get('predicate'), event.get('object_id'))
        for event in primary_events
    }
    for idx, event in enumerate(allowed_events, start=1):
        required = "必选主事件" if (
            event.get('event_type'), event.get('predicate'), event.get('object_id')
        ) in primary_keys else "按当天状态可选"
        lines.append(
            "- {idx}. {required}: subject_id={subject_id}, predicate={predicate}, object_id={object_id}, "
            "event_type={event_type}, description={description}".format(
                idx=idx,
                required=required,
                subject_id=event.get('subject_id', default_subject),
                predicate=event.get('predicate', ''),
                object_id=event.get('object_id', ''),
                event_type=event.get('event_type', ''),
                description=event.get('description', '')
            )
        )
    return '\n'.join(lines) if lines else f"- 1. subject_id={default_subject}, predicate=occurred, object_id=door_main, event_type=scene_main, description=场景主要事件"


def format_candidate_event_info(event, default_subject):
    return json.dumps({
        "subject_id": event.get('subject_id', default_subject),
        "predicate": event.get('predicate', ''),
        "object_id": event.get('object_id', ''),
        "attributes": {
            "event_type": event.get('event_type', ''),
            "description": event.get('description', ''),
        }
    }, ensure_ascii=False, indent=2)


def validate_llm_state_result(result):
    if not isinstance(result, dict):
        raise ValueError(f"State description result must be a dict, got {type(result)}")
    if 'scenario_should_happen' not in result:
        raise ValueError("Missing scenario_should_happen")
    if 'daily_state_description' not in result:
        raise ValueError("Missing daily_state_description")
    return {
        "scenario_should_happen": bool(result.get('scenario_should_happen')),
        "scenario_time": result.get('scenario_time', ''),
        "skip_reason": result.get('skip_reason', ''),
        "daily_state_description": result.get('daily_state_description', ''),
        "sampled_context": result.get('sampled_context', {}),
    }


def validate_llm_event_item_result(result, candidate_event, default_subject, person_ids, available_devices, previous_events):
    if not isinstance(result, dict):
        raise ValueError(f"Event item result must be a dict, got {type(result)}")
    if not result.get('should_generate', False):
        return None
    annotated_event = result.get('annotated_event')
    if not isinstance(annotated_event, dict):
        raise ValueError("should_generate=true but annotated_event is missing")

    event = annotated_event.get('event')
    snapshot = annotated_event.get('state_snapshot')
    if not isinstance(event, dict) or not isinstance(snapshot, dict):
        raise ValueError("annotated_event must contain event and state_snapshot")

    expected_subject = candidate_event.get('subject_id', default_subject)
    expected_type = candidate_event.get('event_type', '')
    if event.get('subject_id') != expected_subject:
        raise ValueError(f"Invalid subject_id: {event.get('subject_id')}, expected {expected_subject}")
    if event.get('predicate') != candidate_event.get('predicate'):
        raise ValueError(f"Invalid predicate: {event.get('predicate')}, expected {candidate_event.get('predicate')}")
    if event.get('object_id') != candidate_event.get('object_id'):
        raise ValueError(f"Invalid object_id: {event.get('object_id')}, expected {candidate_event.get('object_id')}")
    event.setdefault('attributes', {})
    if event['attributes'].get('event_type') != expected_type:
        raise ValueError(f"Invalid event_type: {event['attributes'].get('event_type')}, expected {expected_type}")
    event['attributes'].setdefault('description', candidate_event.get('description', ''))

    if event['subject_id'] not in person_ids and event['subject_id'] not in {'home_system', 'system', 'visitor'}:
        raise ValueError(f"Invalid subject_id: {event['subject_id']}")
    if event['object_id'] not in available_devices:
        raise ValueError(f"Invalid object_id: {event['object_id']}")

    for key in ('timestamp', 'persons', 'devices', 'space_occupancy'):
        if key not in snapshot:
            raise ValueError(f"state_snapshot missing {key}")
    validate_person_states(snapshot, person_ids)
    validate_device_states(snapshot)

    current_timestamp = datetime.fromisoformat(snapshot['timestamp'].replace('+08:00', ''))
    if previous_events:
        prev_timestamp = datetime.fromisoformat(
            previous_events[-1]['state_snapshot']['timestamp'].replace('+08:00', '')
        )
        if current_timestamp <= prev_timestamp:
            raise ValueError(f"timestamp is not increasing: {snapshot['timestamp']}")

    return annotated_event


def validate_person_states(snapshot, person_ids):
    """
    校验 state_snapshot 中人物 location/status 是否来自预定义房间状态枚举。
    """
    persons = snapshot.get('persons')
    if not isinstance(persons, dict):
        raise ValueError("state_snapshot.persons must be a dict")

    valid_person_ids = set(person_ids)
    for person_id, person_state in persons.items():
        if person_id not in valid_person_ids and person_id != 'visitor':
            raise ValueError(f"Invalid person_id in state_snapshot: {person_id}")
        if not isinstance(person_state, dict):
            raise ValueError(f"Invalid person state for {person_id}")

        location = person_state.get('location')
        status = person_state.get('status')
        allowed_statuses = PERSON_ROOM_STATUS_SCHEMA.get(location)
        if allowed_statuses is None:
            raise ValueError(f"Invalid location for {person_id}: {location}")
        if status not in allowed_statuses:
            raise ValueError(
                f"Invalid status for {person_id}: {status}; "
                f"location {location} allows {', '.join(allowed_statuses)}"
            )


def validate_device_states(snapshot):
    """
    校验 state_snapshot 中设备 state 是否来自 DEVICE_STATES。
    """
    devices = snapshot.get('devices')
    if not isinstance(devices, dict):
        raise ValueError("state_snapshot.devices must be a dict")

    for device_id, device_state in devices.items():
        if not isinstance(device_state, dict):
            raise ValueError(f"Invalid device state for {device_id}")
        if device_id not in DEVICE_STATES:
            raise ValueError(f"Unknown device_id in state_snapshot: {device_id}")
        state = device_state.get('state')
        if state not in DEVICE_STATES[device_id]:
            raise ValueError(
                f"Invalid state for {device_id}: {state}; "
                f"allowed states: {', '.join(DEVICE_STATES[device_id])}"
            )


def get_annotated_event_key(annotated_event):
    event = annotated_event.get('event', {}) if isinstance(annotated_event, dict) else {}
    attributes = event.get('attributes', {}) if isinstance(event.get('attributes'), dict) else {}
    return (
        event.get('subject_id', ''),
        attributes.get('event_type', ''),
        event.get('predicate', ''),
        event.get('object_id', ''),
    )


def find_matching_allowed_event(annotated_event, allowed_events, default_subject):
    key = get_annotated_event_key(annotated_event)
    for candidate_event in allowed_events:
        candidate_key = (
            candidate_event.get('subject_id', default_subject),
            candidate_event.get('event_type', ''),
            candidate_event.get('predicate', ''),
            candidate_event.get('object_id', ''),
        )
        if key == candidate_key:
            return candidate_event
    return None


def validate_llm_next_event_result(result, allowed_events, default_subject, person_ids,
                                   available_devices, previous_events):
    if not isinstance(result, dict):
        raise ValueError(f"Next event result must be a dict, got {type(result)}")
    if not result.get('should_continue', False):
        return None

    annotated_event = result.get('annotated_event')
    if not isinstance(annotated_event, dict):
        raise ValueError("should_continue=true but annotated_event is missing")

    candidate_event = find_matching_allowed_event(annotated_event, allowed_events, default_subject)
    if not candidate_event:
        raise ValueError(f"Generated event is not in allowed event set: {get_annotated_event_key(annotated_event)}")

    current_key = get_annotated_event_key(annotated_event)
    used_keys = {get_annotated_event_key(event) for event in previous_events}
    if current_key in used_keys:
        raise ValueError(f"Duplicate generated event: {current_key}")

    return validate_llm_event_item_result(
        {"should_generate": True, "annotated_event": annotated_event},
        candidate_event,
        default_subject,
        person_ids,
        available_devices,
        previous_events,
    )


def generate_scenario_events_from_description_llm(context, run_json_trials_func, max_retries=3):
    scenario = context['scenario']
    episode_date = context['episode_date']
    default_subject = context['default_subject']
    default_home = context['default_home']
    person_ids = context['person_ids']
    available_devices = context['available_devices']
    allowed_events = context['allowed_events']
    primary_events = context['primary_events']
    time_range = context['time_range']
    household_profile = context['household_profile']
    annotated_events = []

    max_events = max(1, len(allowed_events))
    all_scenario_descriptions = context.get('all_scenario_descriptions') or "无"

    for attempt in range(max_retries):
        annotated_events = []
        try:
            for _ in range(max_events):
                next_prompt = LLM_NEXT_EVENT_PROMPT.format(
                    scenario=scenario,
                    scenario_desc=context['scenario_desc'],
                    episode_date=episode_date.strftime('%Y-%m-%d'),
                    subject_id=default_subject,
                    scenario_time=context['scenario_time'],
                    members_info=context['members_info'],
                    relations_info=context['relations_info'],
                    room_device_layout=context['room_device_layout'],
                    person_room_status_schema=context['person_room_status_schema'],
                    device_state_schema=context['device_state_schema'],
                    devices_info=context['devices_info'],
                    all_scenario_descriptions=all_scenario_descriptions,
                    daily_state_description=context['daily_state_description'],
                    previous_events=json.dumps([i["event"] for i in annotated_events], ensure_ascii=False, indent=2),
                    allowed_events_info=format_allowed_events_info(primary_events, allowed_events, default_subject),
                )
                next_result = run_json_trials_func(
                    next_prompt,
                    num_gen=1,
                    num_tokens_request=1800,
                    temperature=0.7,
                )
                annotated_event = validate_llm_next_event_result(
                    next_result,
                    allowed_events,
                    default_subject,
                    person_ids,
                    available_devices,
                    annotated_events,
                )
                if not annotated_event:
                    break
                annotated_events.append(annotated_event)

            llm_result = {
                'daily_state_description': context['daily_state_description'],
                'annotated_events': annotated_events,
            }
            episode = validate_llm_episode_result(
                llm_result,
                scenario,
                episode_date,
                default_subject,
                default_home,
                person_ids,
                available_devices,
                time_range,
                primary_events,
                allowed_events,
                get_household_room_layout(household_profile),
            )
            episode['scenario_time'] = context['scenario_time']
            episode['sampled_context'] = context.get('sampled_context', {})
            return episode
        except Exception as e:
            logging.warning(
                "Event generation attempt %s failed for %s/%s: %s",
                attempt + 1,
                scenario,
                episode_date,
                e,
            )
            if attempt == max_retries - 1:
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
    member_map = {}
    if isinstance(members, dict):
        member_map = members
    elif isinstance(members, list):
        for member in members:
            if isinstance(member, dict):
                member_id = member.get('person_id') or member.get('id') or member.get('name')
                if member_id:
                    member_map[member_id] = member
    
    for person_id in person_ids:
        if person_id in member_map:
            member = member_map[person_id]
            name = member.get('name', person_id)
            role = member.get('role') or member.get('family_role') or member.get('family_role_label') or ''
            age = member.get('age', '')
            info_lines.append(f"- {person_id}: {name}, 角色: {role}, 年龄: {age}")
        else:
            # 使用默认映射
            if person_id in PERSON_ID_MAPPING:
                mapping = PERSON_ID_MAPPING[person_id]
                info_lines.append(f"- {person_id}: {mapping['name']}, 角色: {mapping['role']}, 年龄范围: {mapping['age_range']}")
    
    return '\n'.join(info_lines) if info_lines else "- dad: 父亲, 角色: 男主人, 年龄范围: 35-50\n- mom: 母亲, 角色: 女主人, 年龄范围: 35-50"


def format_relations_info(household_profile):
    """
    格式化家庭成员关系。
    """
    relations = household_profile.get('relations', [])
    if isinstance(relations, dict):
        relation_items = []
        for source, targets in relations.items():
            if isinstance(targets, dict):
                for target, relation_type in targets.items():
                    relation_items.append(f"- {source} --{relation_type}--> {target}")
            elif isinstance(targets, list):
                for item in targets:
                    relation_items.append(f"- {source}: {item}")
        return '\n'.join(relation_items) if relation_items else "未提供显式家庭关系"
    if isinstance(relations, list):
        lines = []
        for relation in relations:
            if isinstance(relation, dict):
                source = relation.get('from') or relation.get('source') or relation.get('subject') or ''
                target = relation.get('to') or relation.get('target') or relation.get('object') or ''
                relation_type = relation.get('type') or relation.get('relation') or ''
                if source or target or relation_type:
                    lines.append(f"- {source} --{relation_type}--> {target}")
            else:
                lines.append(f"- {relation}")
        return '\n'.join(lines) if lines else "未提供显式家庭关系"
    return "未提供显式家庭关系"


def get_household_room_layout(household_profile):
    """
    获取家庭房间与设备布局，家庭画像未提供时使用默认布局。
    """
    for key in ('rooms', 'room_layout', 'spaces'):
        layout = household_profile.get(key)
        if isinstance(layout, dict) and layout:
            normalized = {}
            for room_id, room_data in layout.items():
                if isinstance(room_data, dict):
                    devices = room_data.get('devices') or room_data.get('device_ids') or []
                elif isinstance(room_data, list):
                    devices = room_data
                else:
                    devices = []
                normalized[room_id] = list(devices)
            if normalized:
                return normalized
    return copy.deepcopy(DEFAULT_ROOM_DEVICE_LAYOUT)


def format_room_device_layout(household_profile):
    """
    格式化房间与设备布局。
    """
    layout = get_household_room_layout(household_profile)
    lines = []
    for room_id, devices in layout.items():
        device_text = ', '.join(devices) if devices else '无固定设备'
        lines.append(f"- {room_id}: {device_text}")
    return '\n'.join(lines)


def format_person_room_status_schema():
    """
    格式化人物在不同房间中的可用状态枚举，作为 LLM 约束输入。
    """
    lines = []
    for room_id, statuses in PERSON_ROOM_STATUS_SCHEMA.items():
        lines.append(f"- {room_id}: {', '.join(statuses)}")
    return '\n'.join(lines)


def format_device_state_schema():
    """
    格式化设备状态枚举，作为 LLM 约束输入。
    """
    lines = []
    for device_id, states in DEVICE_STATES.items():
        lines.append(f"- {device_id}: {', '.join(states)}")
    return '\n'.join(lines)


def get_layout_device_ids(household_profile):
    """
    从房间设备布局中提取设备 ID。
    """
    layout = get_household_room_layout(household_profile)
    device_ids = []
    for devices in layout.values():
        device_ids.extend(devices)
    return list(dict.fromkeys(device_ids))


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
            "wifi_router: WiFi路由器",
            "door_camera: 门口摄像头",
            "door_main: 主门（智能门锁）",
            "door_bell: 门铃",
            "temp_humidity_sensor: 温湿度传感器",
            "light_sensor: 光照传感器",
            "air_quality_sensor: 空气质量传感器",
            "light_hallway: 玄关灯",
            "light_living_room: 客厅灯",
            "light_bedroom: 卧室灯",
            "light_study: 书房灯",
            "ac_living_room: 客厅空调",
            "ac_bedroom: 卧室空调",
            "tv_living_room: 客厅电视",
            "tv_bedroom: 卧室电视",
            "curtain_living_room: 客厅窗帘",
            "fresh_air_system: 新风系统",
            "security_system: 安防系统",
            "motion_sensor: 移动传感器",
            "security_camera: 安防摄像头",
            "coffee_machine: 咖啡机",
            "smart_speaker: 智能音箱"
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


def validate_llm_episode_result(result, scenario, episode_date, default_subject, 
                                 default_home, person_ids, available_devices, time_range,
                                 primary_events=None, allowed_events=None, household_layout=None):
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
    
    primary_events = primary_events or []
    allowed_events = allowed_events or primary_events
    min_event_count = len(primary_events) if primary_events else 1
    max_event_count = len(allowed_events) if allowed_events else max(min_event_count, 1)
    
    # 检查事件数量：必须包含主事件，相关设备事件按当天家庭状态选择。
    if len(annotated_events) < min_event_count or len(annotated_events) > max_event_count:
        raise ValueError(
            f"Invalid number of events: {len(annotated_events)}, expected {min_event_count}-{max_event_count} scene events"
        )
    
    allowed_event_map = {
        (
            event.get('subject_id', default_subject),
            event.get('event_type', ''),
            event.get('predicate', ''),
            event.get('object_id', '')
        ): event
        for event in allowed_events
    }
    required_event_keys = {
        (
            event.get('subject_id', default_subject),
            event.get('event_type', ''),
            event.get('predicate', ''),
            event.get('object_id', '')
        )
        for event in primary_events
    }
    seen_event_keys = set()
    
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
        if 'attributes' not in event:
            event['attributes'] = {}
        
        # 验证 subject_id 在可用人员列表或系统执行主体中
        if event['subject_id'] not in person_ids and event['subject_id'] not in {'home_system', 'system', 'visitor'}:
            raise ValueError(f"Event {i} has invalid subject_id: {event['subject_id']}")
        
        # 验证 object_id 在可用设备列表中
        if event['object_id'] not in available_devices:
            raise ValueError(f"Event {i} has invalid object_id: {event['object_id']}")
        
        actual_type = event.get('attributes', {}).get('event_type', '')
        event_key = (event['subject_id'], actual_type, event['predicate'], event['object_id'])
        if allowed_event_map and event_key not in allowed_event_map:
            raise ValueError(f"Event {i} is not an allowed scene event: {event_key}")
        seen_event_keys.add(event_key)
        
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
        validate_person_states(snapshot, person_ids)
        validate_device_states(snapshot)
        
        # 验证时间戳格式和递增性
        try:
            current_timestamp = datetime.fromisoformat(snapshot['timestamp'].replace('+08:00', ''))
            if prev_timestamp and current_timestamp <= prev_timestamp:
                raise ValueError(f"Event {i} timestamp is not increasing: {snapshot['timestamp']}")
            prev_timestamp = current_timestamp
        except ValueError as e:
            raise ValueError(f"Event {i} has invalid timestamp format: {e}")
    
    missing_required = required_event_keys - seen_event_keys
    if missing_required:
        raise ValueError(f"Missing required primary events: {sorted(missing_required)}")
    
    # 构建完整的 episode
    episode = {
        "episode_id": f"{scenario}_{default_subject}_{episode_date.strftime('%Y%m%d')}",
        "home_id": default_home,
        "scene": scenario,
        "subject_id": default_subject,
        "confidence": round(0.85 + random.random() * 0.1, 2),
        "date": episode_date.isoformat(),
        "household_layout": household_layout or get_household_room_layout({}),
        "daily_state_description": result['daily_state_description'],
        "annotated_events": annotated_events
    }
    
    return episode


def generate_scenario_device_episodes(scenario, num_days=7, household_profile=None, 
                                      scene_templates=None, device_file=None, use_llm=True,
                                      subject_id=None, subject_profile=None):
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
    scenario = canonicalize_scenario(scenario)
    
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
    default_subject = subject_id or template.get('default_subject', 'dad')
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
    if default_subject not in person_ids:
        person_ids.append(default_subject)
    
    # 确定起始日期（从今天往前推num_days天）
    start_date = datetime.now().date() - timedelta(days=num_days - 1)
    
    # 为每一天生成一个episode
    for day_offset in range(num_days):
        episode_date = start_date + timedelta(days=day_offset)
        if should_skip_scene_by_calendar(scenario, episode_date):
            logging.info("Skipping %s for %s due to calendar constraints", scenario, episode_date)
            continue
        
        if use_llm:
            # 使用 LLM 生成 episode
            episode = generate_single_day_episode_llm(
                scenario=scenario,
                episode_date=episode_date,
                day_offset=day_offset,
                template=template,
                household_profile=household_profile,
                person_ids=person_ids,
                device_file=device_file,
                subject_id=default_subject
            )
            if episode and episode.get('_skip'):
                continue
            
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
            if subject_profile:
                episode['subject_profile'] = subject_profile
            episodes.append(episode)
    
    logging.info(f"Generated {len(episodes)} episodes for scenario '{scenario}'")
    return episodes


def should_skip_scene_by_calendar(scenario, episode_date):
    """
    规则兜底下的日历约束：周末不生成工作日/上学日强绑定场景。
    LLM 路径会在状态描述阶段做更细判断。
    """
    if episode_date.weekday() >= 5 and scenario in {'leave_work', 'family_return', 'child_return'}:
        return True
    return False


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
    
    current_state = initialize_state(person_ids)
    all_events = get_primary_events(template)
    all_events.extend(select_contextual_related_events(template, current_state))
    
    # 生成annotated_events
    annotated_events = []
    event_time = base_timestamp
    
    for event_data in all_events:
        current_state = prepare_state_for_primary_event(current_state, event_data, default_subject)
        # 创建事件前的状态快照
        state_snapshot = create_state_snapshot(
            timestamp=event_time.isoformat(),
            persons=current_state['persons'],
            devices=current_state['devices'].copy(),
            space_occupancy=current_state['space_occupancy'].copy()
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
        "episode_id": f"{scenario}_{default_subject}_{episode_date.strftime('%Y%m%d')}",
        "home_id": default_home,
        "scene": scenario,
        "subject_id": default_subject,
        "confidence": round(0.85 + random.random() * 0.1, 2),
        "date": episode_date.isoformat(),
        "household_layout": get_household_room_layout(household_profile),
        "daily_state_description": f"基于规则模板生成的{template.get('name', scenario)}场景，只记录当天的场景主要事件和对应设备状态。",
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
        if isinstance(members, dict):
            for member_id, member_info in members.items():
                person_ids.append(member_id)
        elif isinstance(members, list):
            for member in members:
                if isinstance(member, dict):
                    person_ids.append(member.get('person_id') or member.get('id') or member.get('name'))
                else:
                    person_ids.append(str(member))
            person_ids = [person_id for person_id in person_ids if person_id]
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
            persons[person_id] = {"status": "cooking", "location": "kitchen"}
        elif person_id == 'grandpa':
            persons[person_id] = {"status": "resting", "location": "living_room"}
        elif person_id == 'grandma':
            persons[person_id] = {"status": "resting", "location": "bedroom"}
        elif person_id == 'child':
            persons[person_id] = {"status": "studying", "location": "study"}
        else:
            persons[person_id] = {"status": "outside", "location": "outside"}
    
    # 初始化设备状态
    devices = {
        "wifi_router": {"state": "online"},
        "door_camera": {"state": "idle"},
        "door_main": {"state": "locked"},
        "door_bedroom": {"state": "closed"},
        "door_bell": {"state": "silent"},
        "temp_humidity_sensor": {"state": "normal"},
        "light_sensor": {"state": "bright"},
        "air_quality_sensor": {"state": "good"},
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
        "fresh_air_system": {"state": "off"},
        "security_system": {"state": "disarmed"},
        "motion_sensor": {"state": "clear"},
        "security_camera": {"state": "idle"},
        "coffee_machine": {"state": "idle"},
        "smart_speaker": {"state": "idle"}
    }
    
    return {
        "persons": persons,
        "devices": devices,
        "space_occupancy": {"entrance": 0, "living_room": 1, "bedroom": 1, "study": 1, "kitchen": 1, "bathroom": 0}
    }


def select_contextual_related_events(template, current_state):
    """
    根据当天家庭状态选择会被场景触发的相关设备事件。
    """
    related_events = template.get('related_events', [])
    if not related_events:
        return []

    selected = []
    scenario_name = template.get('name', '')
    living_room_occupied = random.random() < 0.35
    bedroom_occupied = random.random() < 0.25
    if '上班离家' in scenario_name:
        current_state['space_occupancy']['living_room'] = 1 if living_room_occupied else 0
        current_state['space_occupancy']['bedroom'] = 1 if bedroom_occupied else 0
        if not living_room_occupied and 'grandpa' in current_state['persons']:
            current_state['persons']['grandpa'] = {"status": "resting", "location": "bedroom"}
        if living_room_occupied and 'grandpa' in current_state['persons']:
            current_state['persons']['grandpa'] = {"status": "watching_tv", "location": "living_room"}

    for event in related_events:
        event_type = event.get('event_type', '')

        if '上班离家' in scenario_name:
            if event_type == 'lock_main_door':
                selected.append(event.copy())
            elif event_type in {
                'turn_off_living_room_light',
                'turn_off_living_room_tv',
                'turn_off_living_room_ac',
            } and not living_room_occupied:
                selected.append(event.copy())
            elif event_type in {
                'turn_off_bedroom_light',
                'turn_off_bedroom_ac',
            } and not bedroom_occupied:
                selected.append(event.copy())
        elif '下班回家' in scenario_name:
            if event_type == 'turn_on_living_room_light' and random.random() < 0.75:
                selected.append(event.copy())
            elif event_type == 'turn_on_living_room_ac' and random.random() < 0.55:
                selected.append(event.copy())
            elif event_type == 'turn_on_living_room_tv' and random.random() < 0.35:
                selected.append(event.copy())
        elif random.random() < 0.5:
            selected.append(event.copy())

    return selected


def create_state_snapshot(timestamp, persons, devices, space_occupancy=None):
    """
    创建状态快照。
    
    Args:
        timestamp: 时间戳字符串
        persons: 人员状态字典
        devices: 设备状态字典
        space_occupancy: 空间占用字典
        
    Returns:
        dict: 状态快照
    """
    return {
        "timestamp": timestamp,
        "persons": copy.deepcopy(persons),
        "devices": copy.deepcopy(devices),
        "space_occupancy": copy.deepcopy(space_occupancy or {})
    }


def prepare_state_for_primary_event(current_state, event_data, default_subject):
    """
    为场景级主事件准备快照状态，避免规则兜底沿用过细的过程状态。
    """
    state = {
        "persons": copy.deepcopy(current_state['persons']),
        "devices": copy.deepcopy(current_state['devices']),
        "space_occupancy": copy.deepcopy(current_state['space_occupancy'])
    }
    subject_id = event_data.get('subject_id', default_subject)
    event_type = event_data.get('event_type', '')
    object_id = event_data.get('object_id', '')

    if event_type in {'return_home', 'visitor_arrival'}:
        if subject_id in state['persons']:
            state['persons'][subject_id] = {"status": "arriving", "location": "entrance"}
        if object_id in state['devices']:
            state['devices'][object_id] = {"state": "closed" if object_id == "door_main" else state['devices'][object_id].get('state', 'idle')}
        state['space_occupancy']['entrance'] = max(1, state['space_occupancy'].get('entrance', 0))
    elif event_type == 'arm_away_mode':
        for person_id in state['persons']:
            state['persons'][person_id] = {"status": "outside", "location": "outside"}
        if object_id in state['devices']:
            state['devices'][object_id] = {"state": "armed"}
        state['space_occupancy'] = {space: 0 for space in state['space_occupancy']}
    elif event_type == 'anomaly_detected' and object_id in state['devices']:
        state['devices'][object_id] = {"state": "detected"}
    elif event_type == 'lock_main_door' and object_id in state['devices']:
        state['devices'][object_id] = {"state": "closed"}
        if 'dad' in state['persons']:
            state['persons']['dad'] = {"status": "left_home", "location": "outside"}
    elif event_data.get('predicate') == 'deactivated' and object_id in state['devices']:
        state['devices'][object_id] = {"state": "on"}
    elif event_data.get('predicate') == 'activated' and object_id in state['devices']:
        state['devices'][object_id] = {"state": "off"}

    return state


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
        "persons": copy.deepcopy(current_state['persons']),
        "devices": copy.deepcopy(current_state['devices']),
        "space_occupancy": copy.deepcopy(current_state['space_occupancy'])
    }
    
    predicate = event_data['predicate']
    object_id = event_data['object_id']
    event_type = event_data.get('event_type', '')
    
    # 更新人员状态
    subject_id = event_data.get('subject_id', 'dad')
    if subject_id in new_state['persons']:
        if predicate in {'entered', 'returned', 'arrived'}:
            new_state['persons'][subject_id]['status'] = 'arriving'
            new_state['persons'][subject_id]['location'] = 'entrance'
        elif predicate == 'left':
            new_state['persons'][subject_id]['status'] = 'left_home'
            new_state['persons'][subject_id]['location'] = 'outside'
        elif predicate in {'opened', 'closed', 'locked'} and object_id == 'door_main':
            new_state['persons'][subject_id]['status'] = 'leaving' if event_type in {
                'open_main_door', 'close_main_door', 'elderly_open_main_door', 'elderly_close_main_door'
            } else 'arriving'
            new_state['persons'][subject_id]['location'] = 'entrance'
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
            if object_id == 'security_system':
                device['state'] = 'armed'
            elif object_id == 'fresh_air_system':
                device['state'] = 'on'
            elif object_id == 'coffee_machine':
                device['state'] = 'brewing'
            elif object_id == 'smart_speaker':
                device['state'] = 'speaking'
            else:
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
            if object_id == 'door_camera':
                device['state'] = 'motion_detected'
            elif object_id == 'wifi_router':
                device['state'] = 'unknown_device_detected'
            elif object_id == 'light_sensor':
                device['state'] = 'dark'
            elif object_id == 'air_quality_sensor':
                device['state'] = 'poor'
            elif object_id == 'temp_humidity_sensor':
                device['state'] = 'temp_low'
            else:
                device['state'] = 'detected'
        elif predicate == 'recognized':
            device['state'] = 'face_recognized'
        elif predicate == 'rang':
            device['state'] = 'ringing'
        elif predicate == 'announced':
            device['state'] = 'speaking'
        elif predicate == 'cleared':
            device['state'] = 'clear'
        elif predicate == 'recording':
            device['state'] = 'recording'
    
    # 更新空间占用
    if event_type in {'enter_home', 'return_home', 'visitor_arrival'}:
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
