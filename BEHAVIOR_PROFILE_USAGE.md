# 行为画像生成使用说明

## 概述

`generate_behavior_profile.py` 用于生成连续多日的设备事件行为画像，支持两种生成方式：
1. **LLM 生成**：使用大语言模型每天生成家庭状态描述和设备事件（默认）
2. **规则模板生成**：使用预定义的规则模板生成设备事件

## 功能特性

### LLM 生成模式（推荐）

- 每天一次模型调用，同时生成家庭状态描述和设备事件
- 自动随机抽样部分人物和设备，融入家庭状态描述
- 事件围绕"男主人下班回家"场景，包含核心事件和噪声事件
- 自动验证生成结果，失败时回退到规则模板

### 规则模板生成模式

- 使用预定义的核心事件和噪声事件模板
- 支持基于家庭画像的动态噪声事件生成
- 快速生成，无需模型调用

## 使用方法

### 基本用法

```bash
# 使用 LLM 生成 7 天的 family_return 场景（默认）
python locomo/generative_agents/generate_behavior_profile.py \
    --out-dir ./output \
    --scenario family_return

# 使用规则模板生成
python locomo/generative_agents/generate_behavior_profile.py \
    --out-dir ./output \
    --scenario family_return \
    --use-rule-based
```

### 参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--out-dir` | 输出目录路径（必需） | - |
| `--scenario` | 场景类型 | `family_return` |
| `--num-days` | 生成连续天数 | `7` |
| `--device-event-days` | 设备事件生成天数 | 与 `--num-days` 相同 |
| `--overwrite-events` | 覆盖已存在的设备事件 | `False` |
| `--use-llm` | 使用 LLM 生成（默认启用） | `True` |
| `--use-rule-based` | 使用规则模板生成 | `False` |
| `--household-profile` | 家庭画像文件路径 | `./data/household/household_profile.json` |
| `--device-file` | 家庭设备库文件路径 | `./data/devices/home_devices.json` |

### 支持的场景

- `family_return`：家庭成员下班回家（男主人回家）
- `male_leave_work`：男主人上班离家
- `elderly_outdoor`：老人独自外出
- `child_return`：小孩放学回家
- `visitor_arrival`：访客到家
- `all_leave_arm`：全员离家布防
- `anomaly_detection`：异常活动检测

## 输出格式

生成的 `device_events.json` 文件包含以下结构：

```json
{
  "version": "2.0",
  "scenario": "family_return",
  "generated_at": "2026-06-23T11:26:26.816763",
  "generation_method": "LLM",
  "total_episodes": 7,
  "episodes": [
    {
      "episode_id": "family_return_20260621",
      "home_id": "home_1",
      "scene": "family_return",
      "subject_id": "dad",
      "confidence": 0.9,
      "date": "2026-06-21",
      "daily_state_description": "当天的家庭状态自然语言描述（LLM 模式）",
      "sampled_context": {
        "persons": ["dad", "mom", "child"],
        "devices": ["door_main", "light_hallway", "ac_living_room"]
      },
      "annotated_events": [
        {
          "event": {
            "subject_id": "dad",
            "predicate": "entered",
            "object_id": "door_main",
            "attributes": {
              "event_type": "enter_home",
              "description": "开门进入"
            }
          },
          "state_snapshot": {
            "timestamp": "2026-06-21T18:30:00+08:00",
            "persons": {
              "dad": {"status": "entering", "location": "entrance"},
              "mom": {"status": "at_home", "location": "kitchen"}
            },
            "devices": {
              "door_main": {"state": "open"},
              "light_hallway": {"state": "off"}
            },
            "space_occupancy": {
              "entrance": ["dad"],
              "kitchen": ["mom"],
              "living_room": []
            }
          }
        }
      ]
    }
  ]
}
```

## 字段说明

### Episode 级别字段

- `episode_id`：Episode 唯一标识符
- `home_id`：家庭 ID
- `scene`：场景类型
- `subject_id`：主要人物 ID（如 `dad`）
- `confidence`：置信度（0-1）
- `date`：日期（ISO8601 格式）
- `daily_state_description`：当天家庭状态描述（LLM 模式）
- `sampled_context`：随机抽样的人物和设备（LLM 模式）
- `annotated_events`：设备事件列表

### Event 级别字段

- `event.subject_id`：操作者 ID
- `event.predicate`：操作类型（如 `entered`, `activated`, `closed`）
- `event.object_id`：操作对象 ID（设备 ID）
- `event.attributes`：事件属性（包含 `event_type` 和 `description`）

### State Snapshot 字段

- `timestamp`：时间戳（ISO8601 格式）
- `persons`：人物状态字典
  - `status`：人物状态（如 `at_home`, `entering`, `sleeping`）
  - `location`：人物位置（如 `entrance`, `kitchen`, `living_room`）
- `devices`：设备状态字典
  - `state`：设备状态（如 `on`, `off`, `open`, `closed`, `locked`）
- `space_occupancy`：空间占用情况
  - 每个空间包含当前占用的人员 ID 列表

## 家庭画像

家庭画像文件（`household_profile.json`）用于提供家庭成员信息和家庭特征，支持以下字段：

```json
{
  "members": {
    "dad": {
      "name": "父亲",
      "role": "男主人",
      "age": 40
    },
    "mom": {
      "name": "母亲",
      "role": "女主人",
      "age": 38
    },
    "child": {
      "name": "孩子",
      "role": "子女",
      "age": 10
    }
  },
  "family": {
    "has_pet": false
  },
  "role_responsibilities": {
    "mom": ["做饭", "打扫卫生"],
    "dad": ["采购", "维修"]
  }
}
```

## 示例

### 示例 1：使用 LLM 生成 7 天行为画像

```bash
python locomo/generative_agents/generate_behavior_profile.py \
    --out-dir ./output/family_return_7days \
    --scenario family_return \
    --num-days 7
```

### 示例 2：使用规则模板生成 3 天行为画像

```bash
python locomo/generative_agents/generate_behavior_profile.py \
    --out-dir ./output/family_return_3days \
    --scenario family_return \
    --num-days 3 \
    --use-rule-based
```

### 示例 3：使用自定义家庭画像

```bash
python locomo/generative_agents/generate_behavior_profile.py \
    --out-dir ./output/custom_household \
    --scenario family_return \
    --household-profile ./data/household/custom_profile.json \
    --num-days 5
```

### 示例 4：覆盖已存在的设备事件

```bash
python locomo/generative_agents/generate_behavior_profile.py \
    --out-dir ./output/family_return \
    --scenario family_return \
    --overwrite-events
```

## 注意事项

1. **LLM 可用性**：LLM 生成模式需要配置好 `openai` 或其他 LLM 服务，否则会自动回退到规则模板生成
2. **设备文件**：确保 `home_devices.json` 文件存在且格式正确
3. **家庭画像**：如果没有提供家庭画像，系统会使用默认的家庭成员模板
4. **时间连续性**：生成的 episodes 日期是连续的，从今天往前推 `num_days` 天
5. **事件数量**：每天生成 2-8 个设备事件（核心事件 2-5 条，噪声事件 0-3 条）

## 故障排查

### 问题：LLM 生成失败

**解决方案**：
- 检查 LLM 服务配置是否正确
- 使用 `--use-rule-based` 参数切换到规则模板生成
- 查看日志了解具体错误信息

### 问题：设备事件数量不符合预期

**解决方案**：
- 检查场景模板中的核心事件和噪声事件配置
- 调整家庭画像中的成员数量
- 使用 `--use-rule-based` 模式查看规则模板生成结果

### 问题：生成的设备 ID 不存在

**解决方案**：
- 检查 `home_devices.json` 文件是否包含所需的设备
- 确认设备 ID 格式正确
- 查看日志中的设备 ID 列表

## 更新日志

### v2.0（当前版本）

- 新增 LLM 生成模式，支持每天生成家庭状态描述
- 新增 `sampled_context` 字段，记录随机抽样的人物和设备
- 新增 `daily_state_description` 字段，保存每天的家庭状态描述
- 新增 `generation_method` 字段，标识生成方法
- 新增 `--use-llm` 和 `--use-rule-based` 参数
- 改进验证逻辑，支持 LLM 生成失败时自动回退
- 优化输出格式，版本号升级到 2.0

### v1.0

- 初始版本，支持规则模板生成
- 支持连续多日设备事件生成
- 支持基于家庭画像的动态噪声事件生成