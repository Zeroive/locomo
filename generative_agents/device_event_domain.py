"""智能家居设备事件的领域定义。

这里放稳定的领域词表、场景模板、房间/设备枚举和时间段定义，避免生成编排代码里混入大段配置。
"""

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
            {"event_type": "unlock_main_door", "predicate": "open", "object_id": "door_main",
             "description": "回家时打开大门"},
            {"event_type": "close_main_door", "predicate": "closed", "object_id": "door_main",
             "description": "进门后关上大门"}
        ],
        "related_events": [
            {"subject_id": "home_assistant", "event_type": "door_camera_face_recognized", "predicate": "face_recognized", "object_id": "door_camera",
             "description": "门口摄像头识别到回家的家庭成员"},
            {"subject_id": "home_assistant", "event_type": "turn_on_living_room_light", "predicate": "on", "object_id": "light_living_room",
             "description": "客厅光线较暗且准备进入客厅时打开客厅灯"},
            {"subject_id": "home_assistant", "event_type": "turn_on_hallway_light", "predicate": "on", "object_id": "light_hallway",
             "description": "玄关光线较暗时打开玄关灯"},
            {"subject_id": "home_assistant", "event_type": "turn_on_living_room_ac", "predicate": "on", "object_id": "ac_living_room",
             "description": "客厅温度不舒适时打开客厅空调"},
            {"subject_id": "home_assistant", "event_type": "turn_on_kitchen_light", "predicate": "on", "object_id": "light_kitchen",
             "description": "回家后准备进入厨房或厨房光线较暗时打开厨房灯"},
            {"subject_id": "home_assistant", "event_type": "turn_on_living_room_tv", "predicate": "on", "object_id": "tv_living_room",
             "description": "回到客厅休息时打开电视"},
            {"subject_id": "home_assistant", "event_type": "close_living_room_curtain", "predicate": "closed", "object_id": "curtain_living_room",
             "description": "夜间回家后关闭客厅窗帘"},
            {"subject_id": "home_assistant", "event_type": "start_fresh_air", "predicate": "on", "object_id": "fresh_air_system",
             "description": "空气质量较差时启动新风系统"},
            {"subject_id": "home_assistant", "event_type": "speaker_welcome", "predicate": "speaking", "object_id": "smart_speaker",
             "description": "智能音箱播报回家欢迎或提醒"}
        ],
        "core_events": [
            {"subject_id": "home_assistant", "event_type": "door_camera_motion", "predicate": "motion_detected", "object_id": "door_camera",
             "description": "门口摄像头检测到有人靠近"},
            {"event_type": "unlock_main_door", "predicate": "open", "object_id": "door_main",
             "description": "打开大门"},
            {"event_type": "close_main_door", "predicate": "closed", "object_id": "door_main",
             "description": "关上大门"},
            {"subject_id": "home_assistant", "event_type": "lock_main_door", "predicate": "locked", "object_id": "door_main",
             "description": "进门后自动落锁"}
        ],
        "noise_events": [
            {"event_type": "living_room_occupied", "predicate": "detected", "object_id": "motion_sensor",
             "description": "客厅有人活动，影响是否打开客厅灯和电视"},
            {"event_type": "light_sensor_dark", "predicate": "dark", "object_id": "light_sensor",
             "description": "室内光照偏暗，可能触发开灯"},
            {"event_type": "bedroom_ac_already_on", "predicate": "on", "object_id": "ac_bedroom",
             "description": "卧室空调已开启，回家后不重复控制"},
            {"event_type": "tv_bedroom_on", "predicate": "on", "object_id": "tv_bedroom",
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
            {"event_type": "open_main_door", "predicate": "open", "object_id": "door_main",
             "description": "上班离家时打开大门"},
            {"event_type": "close_main_door", "predicate": "closed", "object_id": "door_main",
             "description": "上班离家后关上大门"}
        ],
        "related_events": [
            {"subject_id": "home_assistant", "event_type": "lock_main_door", "predicate": "locked", "object_id": "door_main",
             "description": "男主人离家后锁门"},
            {"subject_id": "home_assistant", "event_type": "turn_off_living_room_light", "predicate": "off", "object_id": "light_living_room",
             "description": "客厅无人时关闭客厅灯"},
            {"subject_id": "home_assistant", "event_type": "turn_off_living_room_tv", "predicate": "off", "object_id": "tv_living_room",
             "description": "客厅无人时关闭电视"},
            {"subject_id": "home_assistant", "event_type": "turn_off_living_room_ac", "predicate": "off", "object_id": "ac_living_room",
             "description": "客厅无人时关闭客厅空调"},
            {"subject_id": "home_assistant", "event_type": "turn_off_kitchen_light", "predicate": "off", "object_id": "light_kitchen",
             "description": "厨房无人或早餐准备结束后关闭厨房灯"},
            {"subject_id": "home_assistant", "event_type": "turn_off_bedroom_light", "predicate": "off", "object_id": "light_bedroom",
             "description": "卧室无人时关闭卧室灯"},
            {"subject_id": "home_assistant", "event_type": "turn_off_bedroom_ac", "predicate": "off", "object_id": "ac_bedroom",
             "description": "卧室无人时关闭卧室空调"},
            {"subject_id": "home_assistant", "event_type": "close_living_room_curtain", "predicate": "closed", "object_id": "curtain_living_room",
             "description": "离家前根据日晒或隐私需求关闭客厅窗帘"},
            {"subject_id": "home_assistant", "event_type": "turn_on_hallway_light", "predicate": "on", "object_id": "light_hallway",
             "description": "离家前经过玄关时打开玄关灯"},
            {"subject_id": "home_assistant", "event_type": "speaker_commute_reminder", "predicate": "speaking", "object_id": "smart_speaker",
             "description": "智能音箱播报通勤或天气提醒"}
        ],
        "core_events": [
            {"event_type": "open_main_door", "predicate": "open", "object_id": "door_main",
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
            {"event_type": "coffee_machine_brewing", "predicate": "brewing", "object_id": "coffee_machine",
             "description": "咖啡机仍在工作，说明厨房区域有人"},
            {"event_type": "wifi_phone_offline", "predicate": "offline", "object_id": "wifi_router",
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
            {"event_type": "child_unlock_main_door", "predicate": "open", "object_id": "door_main",
             "description": "小孩回家时打开大门"},
            {"event_type": "child_close_main_door", "predicate": "closed", "object_id": "door_main",
             "description": "小孩进门后关上大门"}
        ],
        "related_events": [
            {"subject_id": "home_assistant", "event_type": "door_camera_face_recognized", "predicate": "face_recognized", "object_id": "door_camera",
             "description": "门口摄像头识别到小孩到家"},
            {"subject_id": "home_assistant", "event_type": "turn_on_hallway_light", "predicate": "on", "object_id": "light_hallway",
             "description": "玄关偏暗时打开玄关灯"},
            {"subject_id": "home_assistant", "event_type": "turn_on_study_light", "predicate": "on", "object_id": "light_study",
             "description": "小孩进入书房学习前打开书房灯"},
            {"subject_id": "home_assistant", "event_type": "turn_on_living_room_tv", "predicate": "on", "object_id": "tv_living_room",
             "description": "小孩选择在客厅休息时打开电视"},
            {"subject_id": "home_assistant", "event_type": "turn_on_living_room_ac", "predicate": "on", "object_id": "ac_living_room",
             "description": "室温不舒适且客厅有人时打开客厅空调"},
            {"subject_id": "home_assistant", "event_type": "speaker_homework_reminder", "predicate": "speaking", "object_id": "smart_speaker",
             "description": "智能音箱提醒写作业或喝水"}
        ],
        "core_events": [
            {"subject_id": "home_assistant", "event_type": "door_camera_motion", "predicate": "motion_detected", "object_id": "door_camera",
             "description": "门口摄像头检测到有人靠近"},
            {"event_type": "child_unlock_main_door", "predicate": "open", "object_id": "door_main",
             "description": "小孩打开大门"},
            {"event_type": "child_close_main_door", "predicate": "closed", "object_id": "door_main",
             "description": "小孩关上大门"}
        ],
        "noise_events": [
            {"event_type": "grandpa_watching_tv", "predicate": "on", "object_id": "tv_living_room",
             "description": "客厅电视已经打开，说明可能有老人正在客厅看电视"},
            {"event_type": "study_light_already_on", "predicate": "on", "object_id": "light_study",
             "description": "书房灯已经打开，可能有人在书房"},
            {"event_type": "light_sensor_dark", "predicate": "dark", "object_id": "light_sensor",
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
            {"event_type": "elderly_open_main_door", "predicate": "open", "object_id": "door_main",
             "description": "老人外出时打开大门"},
            {"event_type": "elderly_close_main_door", "predicate": "closed", "object_id": "door_main",
             "description": "老人外出后关上大门"}
        ],
        "related_events": [
            {"subject_id": "home_assistant", "event_type": "lock_main_door", "predicate": "locked", "object_id": "door_main",
             "description": "老人外出后自动锁门"},
            {"subject_id": "home_assistant", "event_type": "door_camera_motion", "predicate": "motion_detected", "object_id": "door_camera",
             "description": "门口摄像头检测老人离家方向"},
            {"subject_id": "home_assistant", "event_type": "turn_on_hallway_light", "predicate": "on", "object_id": "light_hallway",
             "description": "玄关偏暗时打开玄关灯"},
            {"subject_id": "home_assistant", "event_type": "turn_off_living_room_ac", "predicate": "off", "object_id": "ac_living_room",
             "description": "客厅无人时关闭客厅空调"},
            {"subject_id": "home_assistant", "event_type": "start_fresh_air", "predicate": "on", "object_id": "fresh_air_system",
             "description": "老人离家前空气质量较差时启动新风系统"},
            {"subject_id": "home_assistant", "event_type": "speaker_safety_reminder", "predicate": "speaking", "object_id": "smart_speaker",
             "description": "智能音箱播报天气或安全提醒"}
        ],
        "core_events": [
            {"event_type": "elderly_open_main_door", "predicate": "open", "object_id": "door_main",
             "description": "老人打开大门"},
            {"event_type": "elderly_close_main_door", "predicate": "closed", "object_id": "door_main",
             "description": "老人关上大门"}
        ],
        "noise_events": [
            {"event_type": "living_room_occupied", "predicate": "detected", "object_id": "motion_sensor",
             "description": "客厅仍有人活动，影响是否关闭客厅设备"},
            {"event_type": "air_quality_poor", "predicate": "poor", "object_id": "air_quality_sensor",
             "description": "空气质量较差，可能启动新风系统"},
            {"event_type": "temp_low", "predicate": "temp_low", "object_id": "temp_humidity_sensor",
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
            {"event_type": "visitor_arrival", "predicate": "ringing", "object_id": "door_bell",
             "description": "访客到家"}
        ],
        "related_events": [
            {"subject_id": "home_assistant", "event_type": "door_camera_motion", "predicate": "motion_detected", "object_id": "door_camera",
             "description": "门口摄像头检测到访客靠近"},
            {"subject_id": "home_assistant", "event_type": "door_bell_ring", "predicate": "ringing", "object_id": "door_bell",
             "description": "访客按响门铃"},
            {"subject_id": "home_assistant", "event_type": "remote_unlock_main_door", "predicate": "open", "object_id": "door_main",
             "description": "主人远程开门或使用临时密码开门"},
            {"subject_id": "home_assistant", "event_type": "turn_on_hallway_light", "predicate": "on", "object_id": "light_hallway",
             "description": "玄关偏暗时打开玄关灯"},
            {"subject_id": "home_assistant", "event_type": "speaker_visitor_notice", "predicate": "speaking", "object_id": "smart_speaker",
             "description": "智能音箱播报访客到达提醒"}
        ],
        "core_events": [
            {"subject_id": "home_assistant", "event_type": "door_camera_motion", "predicate": "motion_detected", "object_id": "door_camera",
             "description": "门口摄像头检测到访客"},
            {"subject_id": "home_assistant", "event_type": "door_bell_ring", "predicate": "ringing", "object_id": "door_bell",
             "description": "门铃响起"},
            {"subject_id": "home_assistant", "event_type": "remote_unlock_main_door", "predicate": "open", "object_id": "door_main",
             "description": "打开大门"}
        ],
        "noise_events": [
            {"event_type": "living_room_occupied", "predicate": "detected", "object_id": "motion_sensor",
             "description": "客厅有人，可能由家庭成员接待访客"},
            {"event_type": "curtain_living_room_open", "predicate": "open", "object_id": "curtain_living_room",
             "description": "客厅窗帘打开，适合接待访客"},
            {"event_type": "door_camera_unrecognized", "predicate": "unrecognized", "object_id": "door_camera",
             "description": "门口摄像头检测到未识别人员，影响开门方式"}
        ]
    },
    "all_leave_arm": {
        "name": "全员离家布防",
        "description": "全员离家后，门锁、灯光、空调、新风、摄像头和安防系统进入离家状态",
        "default_subject": "home_assistant",
        "default_home": "home_1",
        "time_window": {
            "normal": {"start": "08:30", "end": "09:30"}
        },
        "primary_events": [
            {"event_type": "arm_away_mode", "predicate": "armed", "object_id": "security_system",
             "description": "全员离家布防"}
        ],
        "related_events": [
            {"subject_id": "home_assistant", "event_type": "lock_main_door", "predicate": "locked", "object_id": "door_main",
             "description": "全员离家后锁门"},
            {"subject_id": "home_assistant", "event_type": "turn_off_hallway_light", "predicate": "off", "object_id": "light_hallway",
             "description": "玄关无人时关闭玄关灯"},
            {"subject_id": "home_assistant", "event_type": "turn_off_living_room_light", "predicate": "off", "object_id": "light_living_room",
             "description": "客厅无人时关闭客厅灯"},
            {"subject_id": "home_assistant", "event_type": "turn_off_bedroom_light", "predicate": "off", "object_id": "light_bedroom",
             "description": "卧室无人时关闭卧室灯"},
            {"subject_id": "home_assistant", "event_type": "turn_off_living_room_ac", "predicate": "off", "object_id": "ac_living_room",
             "description": "客厅无人时关闭客厅空调"},
            {"subject_id": "home_assistant", "event_type": "turn_off_bedroom_ac", "predicate": "off", "object_id": "ac_bedroom",
             "description": "卧室无人时关闭卧室空调"},
            {"subject_id": "home_assistant", "event_type": "stop_fresh_air", "predicate": "off", "object_id": "fresh_air_system",
             "description": "全员离家后关闭或降低新风系统"},
            {"subject_id": "home_assistant", "event_type": "camera_record", "predicate": "recording", "object_id": "security_camera",
             "description": "安防摄像头开始录像或进入警戒"}
        ],
        "core_events": [
            {"event_type": "lock_main_door", "predicate": "locked", "object_id": "door_main",
             "description": "锁门"},
            {"event_type": "security_on", "predicate": "armed", "object_id": "security_system",
             "description": "启动安防系统"}
        ],
        "noise_events": [
            {"event_type": "motion_sensor_clear", "predicate": "clear", "object_id": "motion_sensor",
             "description": "室内移动传感器无活动，支持布防"},
            {"event_type": "wifi_all_phones_offline", "predicate": "offline", "object_id": "wifi_router",
             "description": "家庭成员手机均离线，辅助判断全员离家"},
            {"event_type": "air_quality_good", "predicate": "good", "object_id": "air_quality_sensor",
             "description": "空气质量正常，离家后可关闭新风"}
        ]
    },
    "anomaly_detection": {
        "name": "异常活动检测",
        "description": "安防状态下检测到异常活动，门口摄像头、移动传感器、摄像头录像和音箱提醒联动",
        "default_subject": "home_assistant",
        "default_home": "home_1",
        "time_window": {
            "normal": {"start": "00:00", "end": "24:00"}
        },
        "primary_events": [
            {"event_type": "anomaly_detected", "predicate": "detected", "object_id": "motion_sensor",
             "description": "检测到异常活动"}
        ],
        "related_events": [
            {"subject_id": "home_assistant", "event_type": "door_camera_motion", "predicate": "motion_detected", "object_id": "door_camera",
             "description": "门口摄像头检测到异常移动"},
            {"subject_id": "home_assistant", "event_type": "camera_record", "predicate": "recording", "object_id": "security_camera",
             "description": "安防摄像头开始录像"},
            {"subject_id": "home_assistant", "event_type": "speaker_alarm", "predicate": "speaking", "object_id": "smart_speaker",
             "description": "智能音箱发出警示或提醒"},
            {"subject_id": "home_assistant", "event_type": "lock_main_door", "predicate": "locked", "object_id": "door_main",
             "description": "确认大门处于锁定状态"}
        ],
        "core_events": [
            {"event_type": "motion_detected", "predicate": "detected", "object_id": "motion_sensor",
             "description": "检测到移动"},
            {"event_type": "camera_record", "predicate": "recording", "object_id": "security_camera",
             "description": "摄像头录制"}
        ],
        "noise_events": [
            {"event_type": "door_camera_unrecognized", "predicate": "unrecognized", "object_id": "door_camera",
             "description": "门口摄像头检测到未识别人员，可能触发异常"},
            {"event_type": "wifi_unknown_device", "predicate": "unknown_device_detected", "object_id": "wifi_router",
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
    "kitchen": ["light_kitchen", "coffee_machine"]
}


FLOOR_PLAN_PRESETS = [
    {
        "layout_id": "one_bedroom",
        "name": "一室一厅",
        "min_members": 1,
        "max_members": 2,
        "rooms": ["entrance", "living_room", "bedroom", "kitchen", "bathroom", "balcony"],
    },
    {
        "layout_id": "two_bedroom",
        "name": "两室一厅",
        "min_members": 2,
        "max_members": 4,
        "rooms": ["entrance", "living_room", "bedroom", "second_bedroom", "kitchen", "bathroom", "balcony"],
    },
    {
        "layout_id": "three_bedroom",
        "name": "三室两厅",
        "min_members": 3,
        "max_members": 6,
        "rooms": ["entrance", "living_room", "dining_room", "bedroom", "second_bedroom", "children_room", "kitchen", "bathroom", "balcony"],
    },
    {
        "layout_id": "three_bedroom_study",
        "name": "三室一厅带书房",
        "min_members": 3,
        "max_members": 6,
        "rooms": ["entrance", "living_room", "bedroom", "second_bedroom", "children_room", "study", "kitchen", "bathroom", "balcony"],
    },
    {
        "layout_id": "four_bedroom",
        "name": "四室两厅",
        "min_members": 5,
        "max_members": 8,
        "rooms": ["entrance", "living_room", "dining_room", "bedroom", "second_bedroom", "children_room", "elderly_room", "study", "kitchen", "bathroom", "balcony"],
    },
]


ROOM_LABELS = {
    "entrance": "玄关",
    "living_room": "客厅",
    "dining_room": "餐厅",
    "bedroom": "主卧",
    "second_bedroom": "次卧",
    "children_room": "儿童房",
    "elderly_room": "老人房",
    "study": "书房",
    "kitchen": "厨房",
    "bathroom": "卫生间",
    "balcony": "阳台",
}


ROOM_DEVICE_CANDIDATES = {
    "entrance": ["door_main", "door_bell", "door_camera", "light_hallway"],
    "living_room": ["light_living_room", "ac_living_room", "tv_living_room", "curtain_living_room", "motion_sensor", "light_sensor", "air_quality_sensor", "fresh_air_system", "smart_speaker"],
    "dining_room": ["light_living_room", "motion_sensor", "air_quality_sensor"],
    "bedroom": ["light_bedroom", "ac_bedroom", "tv_bedroom", "curtain_bedroom", "temp_humidity_sensor"],
    "second_bedroom": ["light_bedroom", "ac_bedroom", "curtain_bedroom", "temp_humidity_sensor"],
    "children_room": ["light_bedroom", "ac_bedroom", "tv_kids", "curtain_bedroom", "temp_humidity_sensor"],
    "elderly_room": ["light_bedroom", "ac_bedroom", "tv_bedroom", "curtain_bedroom", "temp_humidity_sensor"],
    "study": ["light_study", "motion_sensor"],
    "kitchen": ["light_kitchen", "coffee_machine", "motion_sensor", "air_quality_sensor"],
    "bathroom": ["light_bathroom", "temp_humidity_sensor", "motion_sensor"],
    "balcony": ["motion_sensor", "air_quality_sensor"],
}


REQUIRED_ROOM_DEVICES = {
    "entrance": ["door_main", "door_bell", "door_camera", "light_hallway"],
    "living_room": ["light_living_room", "motion_sensor", "light_sensor", "smart_speaker"],
    "bedroom": ["light_bedroom", "temp_humidity_sensor"],
    "kitchen": ["light_kitchen", "coffee_machine"],
    "bathroom": ["light_bathroom"],
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
    "light_kitchen": ["on", "off"],
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
    "dining_room": ["eating", "chatting", "awake"],
    "kitchen": ["cooking", "eating", "preparing_meal", "cleaning", "awake"],
    "bedroom": ["sleeping", "resting", "getting_ready", "awake"],
    "second_bedroom": ["sleeping", "resting", "getting_ready", "awake"],
    "children_room": ["sleeping", "studying", "playing", "resting", "awake"],
    "elderly_room": ["sleeping", "resting", "getting_ready", "awake"],
    "study": ["studying", "working", "reading", "awake"],
    "bathroom": ["washing", "getting_ready"],
    "balcony": ["resting", "watering_plants"],
}


PERSON_STATUS_ALIASES = {
    ("bedroom", "asleep"): "sleeping",
    ("bedroom", "sleep"): "sleeping",
    ("bedroom", "waking_up"): "getting_ready",
    ("outside", "away"): "outside",
}

TIME_PERIODS = [
    {"slug": "late_night", "label": "深夜", "start": "00:00", "end": "05:59", "start_min": 0, "end_min": 359},
    {"slug": "early_morning", "label": "早上", "start": "06:00", "end": "08:59", "start_min": 360, "end_min": 539},
    {"slug": "morning", "label": "上午", "start": "09:00", "end": "11:59", "start_min": 540, "end_min": 719},
    {"slug": "noon", "label": "中午", "start": "12:00", "end": "13:59", "start_min": 720, "end_min": 839},
    {"slug": "afternoon", "label": "下午", "start": "14:00", "end": "17:59", "start_min": 840, "end_min": 1079},
    {"slug": "evening", "label": "晚上", "start": "18:00", "end": "23:59", "start_min": 1080, "end_min": 1439},
]
