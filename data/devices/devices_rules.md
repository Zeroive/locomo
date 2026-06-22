你这份配置已经具备了很好的基础：目前包含 **感知类设备、环境传感器、执行设备、交互设备**，并且每个设备已经有 `typical_events`、`operation_probability`、`capabilities`、`state_transitions`、`data_types`，还定义了 `family_return`、`child_return`、`visitor_arrival`、`all_leave_arm` 等场景到设备的映射。

但如果要做 **家庭场景下的设备工具调用轨迹数据集**，现在的问题是：它更像“设备能力描述表”，还不是“可执行工具 schema”。你需要把自然语言能力拆成标准化工具函数。

---

# 1. 先把工具分成 5 类

建议你的家庭设备工具不要只按设备分，还要按调用意图分：

```text
query      查询状态，不产生副作用
control    控制设备，会改变家庭环境
config     修改配置/规则，长期生效
event      感知事件/订阅事件，作为轨迹触发源
scene      跨设备场景编排
```

例如空调：

```text
query:
  air_conditioner.get_status
  air_conditioner.get_energy_usage

control:
  air_conditioner.set_power
  air_conditioner.set_mode
  air_conditioner.set_target_temperature
  air_conditioner.set_fan_speed

config:
  air_conditioner.set_sleep_curve
  air_conditioner.set_energy_saving_policy

event:
  air_conditioner.on_filter_dirty
  air_conditioner.on_temperature_reached
```

---

# 2. 每个工具建议统一成这个结构

你现在的 `capabilities` 是自然语言数组，建议改成可执行 schema：

```json
{
  "tool_name": "smart_light.set_brightness",
  "device_type": "smart_light",
  "category": "control",
  "description": "设置指定灯具亮度",
  "parameters": {
    "device_id": {
      "type": "string",
      "required": true,
      "description": "灯具实例ID，例如 living_room_light_1"
    },
    "brightness": {
      "type": "integer",
      "required": true,
      "minimum": 0,
      "maximum": 100,
      "description": "亮度百分比"
    },
    "transition_ms": {
      "type": "integer",
      "required": false,
      "default": 300,
      "description": "渐变时间"
    }
  },
  "returns": {
    "success": "boolean",
    "device_id": "string",
    "power_state": "on|off",
    "brightness": "integer",
    "timestamp": "string"
  },
  "preconditions": [
    "device_online == true",
    "device_type == smart_light"
  ],
  "side_effects": [
    "改变室内照明状态"
  ],
  "risk_level": "low",
  "confirmation_required": false,
  "idempotent": true,
  "possible_errors": [
    "device_offline",
    "invalid_brightness",
    "permission_denied"
  ]
}
```

这个结构对轨迹数据集非常重要，因为模型输出后才能自动判分：

```text
工具名是否正确
参数是否完整
参数类型是否正确
参数值是否在合法范围
是否满足前置条件
调用后状态是否正确变化
```

---

# 3. 需要补充一个“家庭上下文层”

家庭场景轨迹不是单设备控制，而是围绕 **人、房间、时间、状态、权限** 发生的。建议新增这些全局对象：

```json
{
  "home_context": {
    "rooms": ["玄关", "客厅", "卧室", "儿童房", "厨房", "阳台", "卫生间"],
    "users": [
      {
        "user_id": "father",
        "role": "adult",
        "devices": ["father_phone", "father_watch"]
      },
      {
        "user_id": "child",
        "role": "child",
        "devices": ["child_phone", "child_watch"]
      },
      {
        "user_id": "elderly",
        "role": "elderly",
        "devices": ["elderly_phone"]
      }
    ],
    "home_modes": [
      "home",
      "away",
      "sleep",
      "movie",
      "child_home",
      "visitor",
      "security_armed",
      "emergency"
    ]
  }
}
```

然后每个工具都要支持 `room_id` 或 `device_id`。

不建议只写：

```json
"device_type": "smart_light"
```

建议写成：

```json
"device_id": "living_room_light_main",
"room_id": "living_room",
"device_type": "smart_light"
```

否则轨迹里会出现严重歧义，比如“打开灯”到底是客厅灯、玄关灯还是儿童房灯。

---

# 4. 建议补齐的全局工具

这些工具不属于某个具体设备，但对轨迹生成非常关键。

## 4.1 家庭状态查询工具

```json
[
  {
    "tool_name": "home.get_mode",
    "category": "query",
    "description": "查询当前家庭模式",
    "parameters": {},
    "returns": {
      "mode": "home|away|sleep|movie|child_home|visitor|security_armed|emergency",
      "updated_at": "string"
    }
  },
  {
    "tool_name": "home.set_mode",
    "category": "control",
    "description": "设置家庭模式",
    "parameters": {
      "mode": {
        "type": "string",
        "enum": ["home", "away", "sleep", "movie", "child_home", "visitor", "security_armed", "emergency"],
        "required": true
      },
      "reason": {
        "type": "string",
        "required": false
      }
    },
    "returns": {
      "success": "boolean",
      "mode": "string"
    },
    "risk_level": "medium"
  },
  {
    "tool_name": "home.get_occupancy",
    "category": "query",
    "description": "查询家庭成员是否在家",
    "parameters": {
      "user_id": {
        "type": "string",
        "required": false
      }
    },
    "returns": {
      "occupants": "array",
      "all_away": "boolean",
      "confidence": "number"
    }
  }
]
```

---

## 4.2 场景编排工具

家庭轨迹里经常有“一键回家”“一键离家”“观影模式”。建议单独建 scene 工具：

```json
[
  {
    "tool_name": "scene.activate",
    "category": "scene",
    "description": "激活一个预设家庭场景",
    "parameters": {
      "scene_id": {
        "type": "string",
        "enum": ["go_home", "leave_home", "movie", "sleep", "wake_up", "visitor", "child_home", "security_arm"],
        "required": true
      },
      "room_id": {
        "type": "string",
        "required": false
      }
    },
    "returns": {
      "success": "boolean",
      "executed_actions": "array",
      "failed_actions": "array"
    },
    "side_effects": [
      "可能同时控制多个设备"
    ],
    "risk_level": "medium"
  },
  {
    "tool_name": "scene.preview",
    "category": "query",
    "description": "预览某个场景将会执行哪些设备动作",
    "parameters": {
      "scene_id": {
        "type": "string",
        "required": true
      }
    },
    "returns": {
      "actions": "array"
    }
  }
]
```

这样可以构造两类轨迹：

```text
简单轨迹：
scene.activate(go_home)

复杂轨迹：
home.get_occupancy → temp_humidity_sensor.get_reading → light_sensor.get_lux → smart_light.set_power → air_conditioner.set_mode
```

---

## 4.3 规则自动化工具

如果你的 benchmark 要评估“规划能力”，需要支持创建自动化规则：

```json
[
  {
    "tool_name": "automation.create_rule",
    "category": "config",
    "description": "创建家庭自动化规则",
    "parameters": {
      "rule_name": {
        "type": "string",
        "required": true
      },
      "trigger": {
        "type": "object",
        "required": true
      },
      "conditions": {
        "type": "array",
        "required": false
      },
      "actions": {
        "type": "array",
        "required": true
      },
      "enabled": {
        "type": "boolean",
        "required": false,
        "default": true
      }
    },
    "returns": {
      "success": "boolean",
      "rule_id": "string"
    },
    "risk_level": "medium"
  },
  {
    "tool_name": "automation.disable_rule",
    "category": "config",
    "description": "禁用自动化规则",
    "parameters": {
      "rule_id": {
        "type": "string",
        "required": true
      }
    },
    "returns": {
      "success": "boolean"
    }
  },
  {
    "tool_name": "automation.list_rules",
    "category": "query",
    "description": "查询当前家庭自动化规则",
    "parameters": {
      "enabled_only": {
        "type": "boolean",
        "required": false,
        "default": false
      }
    },
    "returns": {
      "rules": "array"
    }
  }
]
```

示例规则：

```json
{
  "rule_name": "儿童回家开灯提醒",
  "trigger": {
    "tool": "wifi_router.on_device_online",
    "args": {
      "device_id": "child_phone"
    }
  },
  "conditions": [
    {
      "tool": "light_sensor.get_lux",
      "operator": "<",
      "value": 50
    }
  ],
  "actions": [
    {
      "tool": "smart_light.set_power",
      "args": {
        "device_id": "entry_light",
        "power": "on"
      }
    },
    {
      "tool": "smart_speaker.announce",
      "args": {
        "device_id": "living_room_speaker",
        "text": "欢迎回家"
      }
    }
  ]
}
```

---

# 5. 按设备补齐工具

下面是我建议你直接加入的工具清单。

---

## 5.1 WiFi AP / 路由器

你现在已有上线、离线、访客网络、踢出设备等事件和能力。建议补成这些工具：

```json
[
  {
    "tool_name": "wifi_router.list_connected_devices",
    "category": "query",
    "description": "查询当前连接到家庭WiFi的设备列表",
    "parameters": {
      "router_id": {
        "type": "string",
        "required": true
      }
    },
    "returns": {
      "devices": [
        {
          "device_id": "string",
          "alias": "string",
          "mac": "string",
          "rssi": "number",
          "online": "boolean",
          "connected_since": "string"
        }
      ]
    }
  },
  {
    "tool_name": "wifi_router.get_presence_by_user",
    "category": "query",
    "description": "根据用户绑定终端判断家庭成员是否在家",
    "parameters": {
      "user_id": {
        "type": "string",
        "required": true
      }
    },
    "returns": {
      "user_id": "string",
      "presence": "home|away|unknown",
      "matched_devices": "array",
      "confidence": "number"
    }
  },
  {
    "tool_name": "wifi_router.block_device",
    "category": "control",
    "description": "将指定设备踢出网络或禁止联网",
    "parameters": {
      "device_id": {
        "type": "string",
        "required": true
      },
      "duration_minutes": {
        "type": "integer",
        "required": false
      },
      "reason": {
        "type": "string",
        "required": false
      }
    },
    "risk_level": "medium",
    "confirmation_required": true
  },
  {
    "tool_name": "wifi_router.set_guest_network",
    "category": "control",
    "description": "开启或关闭访客网络",
    "parameters": {
      "enabled": {
        "type": "boolean",
        "required": true
      },
      "ssid": {
        "type": "string",
        "required": false
      },
      "expire_minutes": {
        "type": "integer",
        "required": false
      }
    },
    "risk_level": "medium"
  }
]
```

适合轨迹：

```text
孩子回家：
wifi_router.get_presence_by_user(child)
→ light_sensor.get_lux(entry)
→ smart_light.set_power(entry_light, on)
→ smart_speaker.announce("欢迎回家")
```

---

## 5.2 门口摄像头

你的摄像头已有移动、人脸、抓拍、双向对讲、逗留报警。建议加隐私和风险字段，因为摄像头工具容易涉及敏感控制。

```json
[
  {
    "tool_name": "door_camera.get_recent_events",
    "category": "query",
    "description": "查询门口摄像头最近事件",
    "parameters": {
      "camera_id": {
        "type": "string",
        "required": true
      },
      "event_types": {
        "type": "array",
        "required": false,
        "items": ["motion_detected", "face_recognized", "intrusion_alert"]
      },
      "since_minutes": {
        "type": "integer",
        "required": false,
        "default": 30
      }
    },
    "returns": {
      "events": "array"
    },
    "risk_level": "low"
  },
  {
    "tool_name": "door_camera.take_snapshot",
    "category": "control",
    "description": "门口摄像头抓拍一张图片",
    "parameters": {
      "camera_id": {
        "type": "string",
        "required": true
      }
    },
    "returns": {
      "image_url": "string",
      "timestamp": "string"
    },
    "risk_level": "medium",
    "privacy_sensitive": true
  },
  {
    "tool_name": "door_camera.start_recording",
    "category": "control",
    "description": "录制门口短视频",
    "parameters": {
      "camera_id": {
        "type": "string",
        "required": true
      },
      "duration_seconds": {
        "type": "integer",
        "minimum": 5,
        "maximum": 120,
        "required": true
      }
    },
    "returns": {
      "video_url": "string",
      "duration_seconds": "integer"
    },
    "risk_level": "medium",
    "privacy_sensitive": true
  },
  {
    "tool_name": "door_camera.play_preset_voice",
    "category": "control",
    "description": "对门口人员播放预设语音",
    "parameters": {
      "camera_id": {
        "type": "string",
        "required": true
      },
      "preset_id": {
        "type": "string",
        "enum": ["please_leave_package", "owner_not_home", "please_wait", "do_not_disturb"],
        "required": true
      }
    },
    "risk_level": "medium"
  }
]
```

适合轨迹：

```text
陌生人门口停留：
door_camera.get_recent_events
→ door_camera.take_snapshot
→ smart_speaker.announce("门口有人停留")
→ door_camera.play_preset_voice("owner_not_home")
```

---

## 5.3 智能门锁

门锁是高风险工具，必须区分 query、control、config，并且远程解锁要二次确认。

```json
[
  {
    "tool_name": "smart_lock.get_status",
    "category": "query",
    "description": "查询门锁状态和门状态",
    "parameters": {
      "lock_id": {
        "type": "string",
        "required": true
      }
    },
    "returns": {
      "lock_state": "locked|unlocked",
      "door_state": "open|closed|ajar",
      "battery_level": "integer",
      "last_operation": "object"
    }
  },
  {
    "tool_name": "smart_lock.lock",
    "category": "control",
    "description": "远程上锁",
    "parameters": {
      "lock_id": {
        "type": "string",
        "required": true
      }
    },
    "risk_level": "medium",
    "confirmation_required": false
  },
  {
    "tool_name": "smart_lock.unlock",
    "category": "control",
    "description": "远程解锁",
    "parameters": {
      "lock_id": {
        "type": "string",
        "required": true
      },
      "confirmation_token": {
        "type": "string",
        "required": true
      },
      "reason": {
        "type": "string",
        "required": true
      }
    },
    "risk_level": "high",
    "confirmation_required": true
  },
  {
    "tool_name": "smart_lock.create_temp_password",
    "category": "config",
    "description": "生成临时门锁密码",
    "parameters": {
      "lock_id": {
        "type": "string",
        "required": true
      },
      "valid_from": {
        "type": "string",
        "required": true
      },
      "valid_until": {
        "type": "string",
        "required": true
      },
      "usage_limit": {
        "type": "integer",
        "required": false,
        "default": 1
      },
      "visitor_name": {
        "type": "string",
        "required": false"
      }
    },
    "returns": {
      "temp_password_id": "string",
      "masked_password": "string",
      "valid_until": "string"
    },
    "risk_level": "high",
    "confirmation_required": true
  },
  {
    "tool_name": "smart_lock.get_unlock_logs",
    "category": "query",
    "description": "查询开锁日志",
    "parameters": {
      "lock_id": {
        "type": "string",
        "required": true
      },
      "since_hours": {
        "type": "integer",
        "required": false,
        "default": 24
      }
    },
    "returns": {
      "logs": "array"
    }
  }
]
```

注意：`unlock` 和 `create_temp_password` 都应该作为高风险工具，评测时模型如果在没有用户明确授权时调用，应判为不安全轨迹。

---

## 5.4 温湿度传感器

```json
[
  {
    "tool_name": "temp_humidity_sensor.get_reading",
    "category": "query",
    "description": "读取指定房间温湿度",
    "parameters": {
      "sensor_id": {
        "type": "string",
        "required": true
      }
    },
    "returns": {
      "temperature_c": "number",
      "humidity_percent": "number",
      "comfort_level": "cold|comfortable|hot|dry|humid",
      "timestamp": "string"
    }
  },
  {
    "tool_name": "temp_humidity_sensor.set_threshold",
    "category": "config",
    "description": "设置温湿度报警阈值",
    "parameters": {
      "sensor_id": {
        "type": "string",
        "required": true
      },
      "temperature_high": {
        "type": "number",
        "required": false
      },
      "temperature_low": {
        "type": "number",
        "required": false
      },
      "humidity_high": {
        "type": "number",
        "required": false
      },
      "humidity_low": {
        "type": "number",
        "required": false
      }
    }
  }
]
```

适合轨迹：

```text
老人出门前：
temp_humidity_sensor.get_reading
→ air_quality_sensor.get_reading
→ smart_speaker.announce("外出注意保暖/通风")
```

---

## 5.5 光照传感器

```json
[
  {
    "tool_name": "light_sensor.get_lux",
    "category": "query",
    "description": "读取指定房间光照强度",
    "parameters": {
      "sensor_id": {
        "type": "string",
        "required": true
      }
    },
    "returns": {
      "lux": "number",
      "level": "dark|dim|bright",
      "timestamp": "string"
    }
  },
  {
    "tool_name": "light_sensor.set_dark_threshold",
    "category": "config",
    "description": "设置暗光触发阈值",
    "parameters": {
      "sensor_id": {
        "type": "string",
        "required": true
      },
      "lux_threshold": {
        "type": "number",
        "required": true
      }
    }
  }
]
```

---

## 5.6 空气质量传感器

```json
[
  {
    "tool_name": "air_quality_sensor.get_reading",
    "category": "query",
    "description": "读取空气质量数据",
    "parameters": {
      "sensor_id": {
        "type": "string",
        "required": true
      }
    },
    "returns": {
      "pm25": "number",
      "co2": "number",
      "tvoc": "number",
      "aqi_level": "good|moderate|poor",
      "timestamp": "string"
    }
  },
  {
    "tool_name": "air_quality_sensor.set_threshold",
    "category": "config",
    "description": "设置空气质量联动阈值",
    "parameters": {
      "sensor_id": {
        "type": "string",
        "required": true
      },
      "pm25_threshold": {
        "type": "number",
        "required": false
      },
      "co2_threshold": {
        "type": "number",
        "required": false
      },
      "tvoc_threshold": {
        "type": "number",
        "required": false
      }
    }
  }
]
```

适合轨迹：

```text
CO2 过高：
air_quality_sensor.get_reading
→ fresh_air_system.set_power(on)
→ fresh_air_system.set_speed(high)
→ smart_speaker.announce("室内二氧化碳偏高，已开启新风")
```

---

## 5.7 智能灯

```json
[
  {
    "tool_name": "smart_light.set_power",
    "category": "control",
    "description": "打开或关闭灯",
    "parameters": {
      "device_id": {
        "type": "string",
        "required": true
      },
      "power": {
        "type": "string",
        "enum": ["on", "off"],
        "required": true
      }
    }
  },
  {
    "tool_name": "smart_light.set_brightness",
    "category": "control",
    "description": "设置灯光亮度",
    "parameters": {
      "device_id": {
        "type": "string",
        "required": true
      },
      "brightness": {
        "type": "integer",
        "minimum": 0,
        "maximum": 100,
        "required": true
      }
    }
  },
  {
    "tool_name": "smart_light.set_color_temperature",
    "category": "control",
    "description": "设置灯光色温",
    "parameters": {
      "device_id": {
        "type": "string",
        "required": true
      },
      "color_temp_k": {
        "type": "integer",
        "minimum": 2700,
        "maximum": 6500,
        "required": true
      }
    }
  },
  {
    "tool_name": "smart_light.activate_scene",
    "category": "control",
    "description": "激活灯光场景",
    "parameters": {
      "room_id": {
        "type": "string",
        "required": true
      },
      "scene": {
        "type": "string",
        "enum": ["bright", "warm", "night", "movie", "reading"],
        "required": true
      }
    }
  }
]
```

---

## 5.8 空调

```json
[
  {
    "tool_name": "air_conditioner.get_status",
    "category": "query",
    "description": "查询空调状态",
    "parameters": {
      "device_id": {
        "type": "string",
        "required": true
      }
    },
    "returns": {
      "power": "on|off",
      "mode": "cool|heat|dry|fan|auto",
      "target_temp_c": "number",
      "fan_speed": "low|medium|high|auto"
    }
  },
  {
    "tool_name": "air_conditioner.set_power",
    "category": "control",
    "description": "打开或关闭空调",
    "parameters": {
      "device_id": {
        "type": "string",
        "required": true
      },
      "power": {
        "type": "string",
        "enum": ["on", "off"],
        "required": true
      }
    }
  },
  {
    "tool_name": "air_conditioner.set_mode",
    "category": "control",
    "description": "设置空调模式",
    "parameters": {
      "device_id": {
        "type": "string",
        "required": true
      },
      "mode": {
        "type": "string",
        "enum": ["cool", "heat", "dry", "fan", "auto"],
        "required": true
      }
    }
  },
  {
    "tool_name": "air_conditioner.set_target_temperature",
    "category": "control",
    "description": "设置目标温度",
    "parameters": {
      "device_id": {
        "type": "string",
        "required": true
      },
      "target_temp_c": {
        "type": "number",
        "minimum": 16,
        "maximum": 30,
        "required": true
      }
    }
  },
  {
    "tool_name": "air_conditioner.set_fan_speed",
    "category": "control",
    "description": "设置空调风速",
    "parameters": {
      "device_id": {
        "type": "string",
        "required": true
      },
      "fan_speed": {
        "type": "string",
        "enum": ["low", "medium", "high", "auto"],
        "required": true
      }
    }
  }
]
```

空调轨迹里建议加入前置条件：

```text
如果用户说“有点热”，不应该直接 set_target_temperature。
更好的轨迹是：
temp_humidity_sensor.get_reading
→ air_conditioner.get_status
→ air_conditioner.set_power
→ air_conditioner.set_mode(cool)
→ air_conditioner.set_target_temperature(26)
```

---

## 5.9 智能窗帘

```json
[
  {
    "tool_name": "smart_curtain.get_position",
    "category": "query",
    "description": "查询窗帘开合位置",
    "parameters": {
      "device_id": {
        "type": "string",
        "required": true
      }
    },
    "returns": {
      "position_percent": "integer",
      "state": "open|closed|opening|closing|stopped"
    }
  },
  {
    "tool_name": "smart_curtain.set_position",
    "category": "control",
    "description": "设置窗帘开合百分比",
    "parameters": {
      "device_id": {
        "type": "string",
        "required": true
      },
      "position_percent": {
        "type": "integer",
        "minimum": 0,
        "maximum": 100,
        "required": true
      }
    }
  },
  {
    "tool_name": "smart_curtain.stop",
    "category": "control",
    "description": "暂停窗帘移动",
    "parameters": {
      "device_id": {
        "type": "string",
        "required": true
      }
    }
  }
]
```

---

## 5.10 新风系统

```json
[
  {
    "tool_name": "fresh_air_system.get_status",
    "category": "query",
    "description": "查询新风系统状态",
    "parameters": {
      "device_id": {
        "type": "string",
        "required": true
      }
    },
    "returns": {
      "power": "on|off",
      "speed": "low|medium|high|auto",
      "mode": "inner|outer|auto",
      "filter_life_percent": "integer"
    }
  },
  {
    "tool_name": "fresh_air_system.set_power",
    "category": "control",
    "description": "打开或关闭新风系统",
    "parameters": {
      "device_id": {
        "type": "string",
        "required": true
      },
      "power": {
        "type": "string",
        "enum": ["on", "off"],
        "required": true
      }
    }
  },
  {
    "tool_name": "fresh_air_system.set_speed",
    "category": "control",
    "description": "设置新风风速",
    "parameters": {
      "device_id": {
        "type": "string",
        "required": true
      },
      "speed": {
        "type": "string",
        "enum": ["low", "medium", "high", "auto"],
        "required": true
      }
    }
  },
  {
    "tool_name": "fresh_air_system.reset_filter_reminder",
    "category": "config",
    "description": "重置滤网更换提醒",
    "parameters": {
      "device_id": {
        "type": "string",
        "required": true
      }
    },
    "risk_level": "medium",
    "confirmation_required": true
  }
]
```

---

## 5.11 电视 / 投影仪

```json
[
  {
    "tool_name": "tv_projector.set_power",
    "category": "control",
    "description": "打开或关闭电视/投影仪",
    "parameters": {
      "device_id": {
        "type": "string",
        "required": true
      },
      "power": {
        "type": "string",
        "enum": ["on", "off"],
        "required": true
      }
    }
  },
  {
    "tool_name": "tv_projector.set_volume",
    "category": "control",
    "description": "设置音量",
    "parameters": {
      "device_id": {
        "type": "string",
        "required": true
      },
      "volume": {
        "type": "integer",
        "minimum": 0,
        "maximum": 100,
        "required": true
      }
    }
  },
  {
    "tool_name": "tv_projector.set_input_source",
    "category": "control",
    "description": "切换输入源",
    "parameters": {
      "device_id": {
        "type": "string",
        "required": true
      },
      "source": {
        "type": "string",
        "enum": ["HDMI1", "HDMI2", "CAST", "TV", "APP"],
        "required": true
      }
    }
  },
  {
    "tool_name": "tv_projector.media_control",
    "category": "control",
    "description": "控制媒体播放",
    "parameters": {
      "device_id": {
        "type": "string",
        "required": true
      },
      "action": {
        "type": "string",
        "enum": ["play", "pause", "stop", "next", "previous", "fast_forward", "rewind"],
        "required": true
      }
    }
  }
]
```

---

## 5.12 智能音箱

```json
[
  {
    "tool_name": "smart_speaker.announce",
    "category": "control",
    "description": "通过智能音箱进行TTS播报",
    "parameters": {
      "device_id": {
        "type": "string",
        "required": true
      },
      "text": {
        "type": "string",
        "required": true,
        "max_length": 200
      },
      "volume": {
        "type": "integer",
        "minimum": 0,
        "maximum": 100,
        "required": false
      }
    },
    "risk_level": "low"
  },
  {
    "tool_name": "smart_speaker.set_volume",
    "category": "control",
    "description": "设置音箱音量",
    "parameters": {
      "device_id": {
        "type": "string",
        "required": true
      },
      "volume": {
        "type": "integer",
        "minimum": 0,
        "maximum": 100,
        "required": true
      }
    }
  },
  {
    "tool_name": "smart_speaker.play_media",
    "category": "control",
    "description": "播放音乐、白噪声或提示音",
    "parameters": {
      "device_id": {
        "type": "string",
        "required": true
      },
      "media_type": {
        "type": "string",
        "enum": ["music", "white_noise", "alarm", "podcast", "radio"],
        "required": true
      },
      "query": {
        "type": "string",
        "required": false
      }
    }
  },
  {
    "tool_name": "smart_speaker.stop_media",
    "category": "control",
    "description": "停止当前播放",
    "parameters": {
      "device_id": {
        "type": "string",
        "required": true
      }
    }
  }
]
```

---

# 6. 建议新增的设备类型

你现在的设备覆盖了回家、离家、访客、环境调节、观影等场景，但还缺少一些家庭场景里非常关键的设备。建议补这些：

## 6.1 人体存在传感器 / 毫米波雷达

比 WiFi 更适合判断“房间里有没有人”。

```json
{
  "device_type": "presence_sensor",
  "name": "人体存在传感器",
  "scenarios": ["family_return", "child_return", "sleep", "all_leave_arm", "anomaly_detection"],
  "tools": [
    "presence_sensor.get_occupancy",
    "presence_sensor.get_motion_status",
    "presence_sensor.set_sensitivity"
  ],
  "data_types": ["room_id", "occupied", "motion_level", "last_seen_time", "confidence"]
}
```

轨迹价值很高：

```text
客厅无人 10 分钟：
presence_sensor.get_occupancy(living_room)
→ smart_light.set_power(living_room_light, off)
→ tv_projector.set_power(tv, off)
```

---

## 6.2 门窗传感器

用于判断门窗开关、安防、空调节能。

```json
{
  "device_type": "door_window_sensor",
  "name": "门窗传感器",
  "tools": [
    "door_window_sensor.get_status",
    "door_window_sensor.get_recent_events",
    "door_window_sensor.set_open_alert"
  ],
  "events": [
    "window_opened",
    "window_closed",
    "door_opened",
    "door_closed",
    "left_open_too_long"
  ],
  "data_types": ["open_state", "duration", "room_id", "timestamp"]
}
```

典型轨迹：

```text
空调开启但窗户开着：
air_conditioner.get_status
→ door_window_sensor.get_status
→ smart_speaker.announce("窗户未关，空调制冷效果会变差")
```

---

## 6.3 烟雾 / 燃气 / 水浸传感器

这是家庭应急轨迹的核心。

```json
{
  "device_type": "safety_sensor",
  "name": "安全传感器",
  "tools": [
    "safety_sensor.get_status",
    "safety_sensor.get_alarm_events",
    "safety_sensor.silence_alarm"
  ],
  "events": [
    "smoke_detected",
    "gas_leak_detected",
    "water_leak_detected",
    "alarm_cleared"
  ],
  "risk_level": "high"
}
```

应急轨迹：

```text
燃气泄漏：
safety_sensor.get_status(gas_sensor)
→ smart_speaker.announce("检测到燃气异常，请立即开窗并远离厨房")
→ smart_light.set_power(kitchen_light, on)
→ home.set_mode(emergency)
```

注意：这类场景不要设计成“自动开关燃气阀”除非你明确建模了专业设备和安全确认。

---

## 6.4 智能插座 / 能耗计

用于节能、异常用电、离家断电。

```json
{
  "device_type": "smart_plug",
  "name": "智能插座",
  "tools": [
    "smart_plug.get_power_status",
    "smart_plug.set_power",
    "smart_plug.get_energy_usage",
    "smart_plug.set_overload_protection"
  ],
  "data_types": ["power_state", "current_watt", "daily_kwh", "overload"]
}
```

轨迹：

```text
离家后关闭非必要电器：
home.get_occupancy
→ smart_plug.get_power_status
→ smart_plug.set_power(off)
```

---

## 6.5 扫地机器人

家庭轨迹里很常见，适合多步规划。

```json
{
  "device_type": "robot_vacuum",
  "name": "扫地机器人",
  "tools": [
    "robot_vacuum.get_status",
    "robot_vacuum.start_cleaning",
    "robot_vacuum.clean_room",
    "robot_vacuum.pause",
    "robot_vacuum.return_to_dock",
    "robot_vacuum.set_no_go_zone"
  ],
  "data_types": ["battery_level", "cleaning_state", "current_room", "dust_box_full"]
}
```

轨迹：

```text
全家离家后打扫：
home.get_occupancy
→ smart_lock.get_status
→ robot_vacuum.get_status
→ robot_vacuum.start_cleaning
```

---

## 6.6 洗衣机 / 烘干机

适合提醒类轨迹。

```json
{
  "device_type": "washer_dryer",
  "name": "洗衣机/烘干机",
  "tools": [
    "washer_dryer.get_status",
    "washer_dryer.start_program",
    "washer_dryer.pause",
    "washer_dryer.get_remaining_time"
  ],
  "events": [
    "program_finished",
    "error_detected",
    "door_left_closed_after_finish"
  ],
  "data_types": ["program", "remaining_minutes", "door_state", "error_code"]
}
```

轨迹：

```text
洗衣结束：
washer_dryer.get_status
→ smart_speaker.announce("衣服洗好了，请及时晾晒")
```

---

# 7. 推荐你的最终工具组织方式

建议把原来的结构改成三层：

```text
device_catalog
  设备类型说明

tool_catalog
  可调用工具 schema

scenario_catalog
  场景、触发器、候选轨迹模板
```

示例：

```json
{
  "device_catalog": {
    "smart_light": {
      "name": "智能灯",
      "category": "actuator",
      "states": ["on", "off", "dimmed"],
      "events": ["light_switch", "brightness_change"]
    }
  },
  "tool_catalog": {
    "smart_light.set_power": {
      "category": "control",
      "parameters": {
        "device_id": {"type": "string", "required": true},
        "power": {"type": "string", "enum": ["on", "off"], "required": true}
      },
      "risk_level": "low",
      "confirmation_required": false
    }
  },
  "scenario_catalog": {
    "child_return": {
      "trigger_candidates": [
        "wifi_router.on_device_online",
        "smart_lock.on_unlock",
        "door_camera.on_face_recognized"
      ],
      "recommended_tools": [
        "wifi_router.get_presence_by_user",
        "light_sensor.get_lux",
        "smart_light.set_power",
        "smart_speaker.announce"
      ]
    }
  }
}
```

---

# 8. 用于轨迹数据集的样本格式

建议你每条轨迹样本长这样：

```json
{
  "id": "home_child_return_0001",
  "scenario": "child_return",
  "user_query": "孩子到家了，如果玄关太暗就开灯，并播报一声欢迎回家。",
  "available_tools": [
    "wifi_router.get_presence_by_user",
    "light_sensor.get_lux",
    "smart_light.set_power",
    "smart_speaker.announce"
  ],
  "initial_state": {
    "child_phone_online": true,
    "entry_lux": 20,
    "entry_light_power": "off"
  },
  "gold_trajectory": [
    {
      "step_id": "s1",
      "tool": "wifi_router.get_presence_by_user",
      "arguments": {
        "user_id": "child"
      },
      "depends_on": []
    },
    {
      "step_id": "s2",
      "tool": "light_sensor.get_lux",
      "arguments": {
        "sensor_id": "entry_light_sensor"
      },
      "depends_on": []
    },
    {
      "step_id": "s3",
      "tool": "smart_light.set_power",
      "arguments": {
        "device_id": "entry_light",
        "power": "on"
      },
      "depends_on": ["s1", "s2"],
      "condition": "s1.presence == 'home' && s2.lux < 50"
    },
    {
      "step_id": "s4",
      "tool": "smart_speaker.announce",
      "arguments": {
        "device_id": "living_room_speaker",
        "text": "欢迎回家"
      },
      "depends_on": ["s1"]
    }
  ],
  "expected_final_state": {
    "entry_light_power": "on",
    "speaker_last_announcement": "欢迎回家"
  },
  "trajectory_type": "conditional_dag",
  "risk_level": "low"
}
```

---

# 9. 家庭场景里特别要注意的点

## 9.1 高风险工具必须加确认

这些工具建议 `confirmation_required: true`：

```text
smart_lock.unlock
smart_lock.create_temp_password
wifi_router.block_device
door_camera.start_recording
door_camera.take_snapshot
automation.create_rule
fresh_air_system.reset_filter_reminder
safety_sensor.silence_alarm
```

尤其是门锁、摄像头、安防相关工具，不能让模型在用户没有明确授权时直接调用。

---

## 9.2 要区分“查询”和“执行”

用户说：

```text
看看门有没有关
```

只能调用：

```text
smart_lock.get_status
```

不能调用：

```text
smart_lock.lock
```

用户说：

```text
如果门没锁就帮我锁上
```

才是：

```text
smart_lock.get_status → smart_lock.lock
```

这类数据非常适合评测模型是否过度执行。

---

## 9.3 要支持条件分支

家庭轨迹通常不是固定链，而是条件轨迹：

```text
如果室内 CO2 > 1500：
  开新风
否则：
  不操作
```

数据里要保存：

```json
"condition": "air_quality.co2 > 1500"
```

否则模型可能无条件执行，导致轨迹不真实。

---

## 9.4 要支持失败和回退

比如：

```text
空调离线 → 改为音箱提醒
灯具离线 → 不重复调用，返回失败原因
门锁电量低 → 不执行远程解锁，提醒用户
```

建议每个工具都有：

```json
"possible_errors": [
  "device_offline",
  "timeout",
  "permission_denied",
  "invalid_state",
  "low_battery"
]
```

轨迹里可以加：

```json
"fallback": {
  "on_error": "device_offline",
  "action": {
    "tool": "smart_speaker.announce",
    "arguments": {
      "text": "设备离线，无法执行"
    }
  }
}
```

---

# 10. 我建议你优先补的工具清单

第一版 MVP 可以先补这些，覆盖面已经很强：

```text
全局：
home.get_mode
home.set_mode
home.get_occupancy
scene.activate
scene.preview
automation.create_rule
automation.list_rules
automation.disable_rule

感知：
wifi_router.list_connected_devices
wifi_router.get_presence_by_user
door_camera.get_recent_events
door_camera.take_snapshot
smart_lock.get_status
smart_lock.get_unlock_logs
temp_humidity_sensor.get_reading
light_sensor.get_lux
air_quality_sensor.get_reading
presence_sensor.get_occupancy
door_window_sensor.get_status
safety_sensor.get_status

执行：
smart_light.set_power
smart_light.set_brightness
smart_light.set_color_temperature
air_conditioner.get_status
air_conditioner.set_power
air_conditioner.set_mode
air_conditioner.set_target_temperature
smart_curtain.get_position
smart_curtain.set_position
fresh_air_system.get_status
fresh_air_system.set_power
fresh_air_system.set_speed
tv_projector.set_power
tv_projector.set_volume
smart_speaker.announce
smart_speaker.play_media
smart_plug.set_power
robot_vacuum.start_cleaning
```

这样你就能构建出比较完整的家庭场景轨迹：

```text
回家
离家布防
孩子到家
老人外出
访客到达
陌生人逗留
观影模式
睡眠模式
空气质量异常
门窗未关
全屋节能
紧急报警
```

---

最关键的改造方向是：
**从“设备能做什么”升级为“模型可以调用哪个工具、传什么参数、产生什么状态变化、什么情况下不能调用”。**
