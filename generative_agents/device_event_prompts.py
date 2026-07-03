"""智能家居设备事件生成使用的 LLM Prompt 模板。"""

LLM_STATE_DESCRIPTION_PROMPT = """你是一个智能家居系统分析师。根据给定的家庭画像和场景，先判断当天该场景是否应该发生，并生成当天该场景下的家庭状态描述。

## 场景信息
场景类型: {scenario}
场景描述: {scenario_desc}
当前场景主体: {subject_id}
日期: {episode_date}
候选发生时段:
{time_period_options}
参考时间: {planned_scene_time}

## 当天已生成的其他情景描述
{previous_scenario_descriptions}

## 家庭成员
{members_info}

## 家庭关系
{relations_info}

## 房间与设备布局
{room_device_layout}

## 可控设备
{devices_info}

## 随机抽样上下文
本日重点人物: {sampled_persons}
本日重点设备: {sampled_devices}

## 任务要求
1. 判断当天该场景是否应该发生：
   - 如果是上班离家/下班回家，休息日、请假日、居家办公日可以不发生
   - 如果场景主体当天不在家或不符合角色作息，也可以不发生
2. 如果发生，先根据家庭成员画像、当天其他情景和场景语义，从候选发生时段中选择一个合理的具体 scenario_time，再生成 daily_state_description，描述当前场景开始前后的家庭状态：
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
        "persons": ["person_005"],
        "devices": ["door_main"]
    }}
}}

## 重要约束
- 输出必须是合法的 JSON 格式
- scenario_should_happen 必须是布尔值
- scenario_time 使用 ISO8601 格式，必须落在“候选发生时段”之一；不要机械照抄参考时间
- daily_state_description 必须写明模型选择的具体小时/分钟，并与 scenario_time 保持一致
- daily_state_description 必须是自然语言描述
- daily_state_description 不能与当天已生成的其他情景描述出现人物位置、设备状态或时间顺序冲突
- daily_state_description 中提到的设备状态应来自“设备状态枚举”

请生成场景发生判断和家庭状态描述："""


LLM_HOME_LAYOUT_DEVICE_PROMPT = """你是一个智能家居户型与设备配置助手。请根据家庭成员、预制户型和设备库信息，为该家庭选择真实存在的房间设备。

## 家庭成员
{members_info}

## 家庭用户偏好与日常习惯
{household_preferences}

## 预制户型
户型ID: {layout_id}
户型名称: {layout_name}
房间列表:
{rooms_info}

## data/devices/home_devices.json 设备库摘要
{devices_info}

## 允许输出的设备ID
{allowed_device_ids}

## 每个房间推荐候选设备
{room_device_candidates}

## 任务要求
1. 只从“允许输出的设备ID”中选择设备，不能创造新设备ID。
2. 每个房间至少保留基础照明或必要传感/门锁设备；按家庭人口、成员角色、生活习惯和偏好选择合理设备。
3. 如果家庭有儿童学习需求，优先给儿童房/书房配置学习照明；如果老人多，优先考虑卧室/老人房舒适与安全传感；如果有人重视影音休闲，客厅可配置电视/音箱；如果有人照护宠物或关注空气质量，优先配置传感器/新风。
4. 客厅通常包含灯、空调/新风/传感器/音箱等；卧室按实际需要选择灯、空调、窗帘、温湿度传感器；玄关必须包含门锁、门铃、门口摄像头和玄关灯。
5. 可以让同一种设备ID出现在多个同类房间中，表示同类设备能力存在；但不要把明显不属于房间的设备放进去。

## 输出格式
请严格按照 JSON 输出，不要包含解释文字：

{{
  "layout_id": "{layout_id}",
  "layout_name": "{layout_name}",
  "rooms": {{
    "entrance": {{"name": "玄关", "devices": ["door_main", "door_bell", "door_camera", "light_hallway"]}},
    "living_room": {{"name": "客厅", "devices": ["light_living_room", "ac_living_room", "smart_speaker"]}}
  }}
}}

请生成该家庭的 rooms 配置："""


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

## 已生成事件摘要与最新 state_snapshot
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
            "subject_id": "home_assistant",
            "predicate": "off",
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

## 当前情景已生成事件摘要与最新 state_snapshot
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
            "subject_id": "home_assistant",
            "predicate": "off",
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


LLM_NEXT_EVENT_ONLY_PROMPT = """你是一个智能家居系统分析师。请基于当前情景描述和已经生成的事件，只生成当前情景下的下一个 event，或判断当前情景事件已经结束。

## 场景信息
场景类型: {scenario}
场景描述: {scenario_desc}
当前场景主体: {subject_id}
日期: {episode_date}
情景发生时间: {scenario_time}

## 当前情景描述
这是整个当前情景预期发生的事情。请结合当前情景已生成事件、最新 state_snapshot 和允许事件集合，判断相关事件是否还应该发生。
{daily_state_description}

## 当前情景已生成事件摘要与最新 state_snapshot
{previous_events}

## 当前情景尚未生成且允许生成的事件集合
{allowed_events_info}

## 任务要求
1. 每次只输出一个“下一个 event”；如果当前情景已经结束，输出 should_continue=false。
2. event 的 subject_id、predicate、object_id、attributes.event_type 必须来自“当前情景尚未生成且允许生成的事件集合”。
3. 需要根据当前情景描述表达的预期、已生成事件摘要和最新 state_snapshot，选择是否发生尚未生成的相关事件。
4. 不要重复生成已经出现过的相同 subject_id/predicate/object_id/event_type 事件。
5. 不要生成候选集合之外的泛化事件或动作拆解细节。

## 输出格式
请严格按照以下 JSON 格式输出，不要包含其他解释文字：

{{
    "should_continue": true,
    "reason": "为什么继续生成该事件，或为什么当前情景已经结束",
    "event": {{
        "subject_id": "home_assistant",
        "predicate": "off",
        "object_id": "light_living_room",
        "attributes": {{
            "event_type": "turn_off_living_room_light",
            "description": "客厅无人时关闭客厅灯"
        }}
    }}
}}

请生成当前情景的下一个 event："""


LLM_EVENT_TIMESTAMP_PROMPT = """你是一个智能家居系统分析师。请只为当前 event 生成 state_snapshot.timestamp。

## 场景信息
场景类型: {scenario}
日期: {episode_date}
情景发生时间: {scenario_time}

## 当前情景描述
{daily_state_description}

## 当前情景已生成事件摘要与最新 state_snapshot
{previous_events}

## 当前 event
{event_json}

## 输出格式
请严格按照以下 JSON 格式输出，不要包含其他解释文字：

{{
    "timestamp": "2022-03-16T08:05:00+08:00"
}}

## 重要约束
- timestamp 使用 ISO8601 格式
- 第一条事件应从情景发生时间之后开始
- 如果已有事件，timestamp 不能早于最后一条事件的 timestamp；同一秒内的联动事件可以使用相同 timestamp

请生成 timestamp："""


LLM_EVENT_PERSONS_PROMPT = """你是一个智能家居系统分析师。请只为当前 event 生成 state_snapshot.persons。

## 场景信息
场景类型: {scenario}
当前场景主体: {subject_id}
日期: {episode_date}
当前事件时间: {timestamp}

## 家庭成员
{members_info}

## 家庭关系
{relations_info}

## 当天所有已生成的情景描述
{all_scenario_descriptions}

## 人物房间状态枚举
{person_room_status_schema}

## 当前情景描述
{daily_state_description}

## 当前情景已生成事件摘要与最新 state_snapshot
{previous_events}

## 当前 event
{event_json}

## 输出格式
请严格按照以下 JSON 格式输出，不要包含其他解释文字：

{{
    "persons": {{
        "person_001": {{"status": "leaving", "location": "entrance"}},
        "person_002": {{"status": "cooking", "location": "kitchen"}}
    }}
}}

## 重要约束
- persons 必须包含所有家庭成员列表中的人物
- 每个人的 location 必须来自“人物房间状态枚举”
- 每个人的 status 必须来自该 location 允许状态
- 只输出人物状态，不要输出设备状态或 timestamp

请生成 persons："""


LLM_EVENT_DEVICES_PROMPT = """你是一个智能家居系统分析师。请只为当前 event 生成 state_snapshot.devices。

## 场景信息
场景类型: {scenario}
日期: {episode_date}
当前事件时间: {timestamp}

## 房间与设备布局
{room_device_layout}

## 设备状态枚举
{device_state_schema}

## 可控设备
{devices_info}

## 当前家庭存在的设备 ID
{household_device_ids}

## 当前情景描述
{daily_state_description}

## 当前情景已生成事件摘要与最新 state_snapshot
{previous_events}

## 当前 event
{event_json}

## 输出格式
请严格按照以下 JSON 格式输出，不要包含其他解释文字：

{{
    "devices": {{
        "door_main": {{"state": "closed"}},
        "light_living_room": {{"state": "on"}}
    }}
}}

## 重要约束
- devices 必须包含“当前家庭存在的设备 ID”中的每一个设备，不能遗漏
- 不要输出“当前家庭存在的设备 ID”之外的设备
- 每个设备 state 必须来自“设备状态枚举”
- state_snapshot 表示事件发生前/发生瞬间的设备状态
- 只输出设备状态，不要输出人物状态或 timestamp

请生成 devices："""


LLM_SINGLE_DEVICE_STATE_PROMPT = """你是一个智能家居系统分析师。请只为当前 event 下的一个指定设备生成 state_snapshot.devices 中该设备的状态。

## 场景信息
场景类型: {scenario}
日期: {episode_date}
当前事件时间: {timestamp}

## 当前设备
设备ID: {device_id}
允许状态: {allowed_states}

## 房间与设备布局
{room_device_layout}

## 可控设备
{devices_info}

## 当前情景描述
{daily_state_description}

## 当前情景已生成事件摘要与最新 state_snapshot
{previous_events}

## 当前 event
{event_json}

## 已生成 persons
{persons_json}

## 输出格式
请严格按照以下 JSON 格式输出，不要包含其他解释文字：

{{
    "device_id": "{device_id}",
    "state": "closed"
}}

## 重要约束
- 只输出当前设备 {device_id} 的状态
- state 必须来自当前设备的允许状态
- state_snapshot 表示事件发生前/发生瞬间的设备状态
- 不要输出其他设备、人物状态或 timestamp

请生成该设备状态："""

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


# ==================== 连续多日设备事件生成功能 ====================
