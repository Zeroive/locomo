# 项目介绍

基于 LoCoMo 的多轮对话工程，创建一个家庭场景中人和AI助手对话的数据集，用于记忆评测集的构建。

数据集包括以下内容：
- 指定场景下 人和AI助手的对话数据
  - 对话的锚点必须包括家庭关系
- 指定场景下 设备的事件记录
- 指定场景下 人通过对话产生的一系列操控设备的轨迹

## 项目架构

- `generative_agents/` — 核心生成逻辑，包含对话生成（`generate_conversations.py`）、事件处理（`event_utils.py`）、记忆管理（`memory_utils.py`）与状态机推演
- `prompt_examples/` — 7大子场景的 Prompt 模板与示例配置，包含因果事件图谱、事实生成、对话生成等示例
- `data/` — 数据集目录，包含 LoCoMo 原始数据（`locomo10.json`）、人物数据（`msc_personas_all.json`、`msc_speakers_single.json`）及多模态对话示例；生成的 JSON 数据集亦存放于此
- `task_eval/` — 评估模块，包含 QA 测评（`evaluate_qa.py`）、统计分析及各模型（GPT、Claude、Gemini、HF LLM）的评估工具
- `scripts/` — 运行脚本目录，包含对话生成、观测生成、评估等批量运行脚本
- `static/` — 前端静态资源与文档，包含 CSS、JavaScript、图片及论文 PDF

## 核心生成逻辑 (LoCoMo 融合)

本工程的目的是生成用于测评 AI 长期记忆、时间推理和因果推理能力的数据集。生成时必须遵循以下逻辑：

### 1. 角色设定

- **User**：家庭主账号所有者（如男主人），通过手机App或智能音箱与AI交互。
- **Assistant**：全屋智能AI助手，具备感知全屋设备状态、摄像头事件及家庭成员位置的能力。

### 2. 场景定义 (Scenarios)

当前支持以下 7 个子场景，生成时需覆盖这些场景的典型交互。**后续新增场景必须在 `src/scenarios/` 中注册**：

1. `male_leave_work` (男主人上班离家)
2. `elderly_outdoor` (老人独自外出)
3. `child_return` (小孩放学回家)
4. `family_return` (家庭成员下班回家)
5. `visitor_arrival` (访客到家)
6. `all_leave_arm` (全员离家布防)
7. `anomaly_detection` (异常活动检测，如深夜厨房异动、水管漏水)

### 3. 记忆锚点 (Memory Anchors) 埋设

为了支持后续的 QA 测评，对话中必须自然地埋入以下类型的记忆点，**禁止生硬插入**：

- **实体记忆**：特定人物的偏好（如"Clara喜欢绿茶"）、特定物品的存放位置（如"备用钥匙在地垫下"）。
- **时间/时序记忆**：事件发生的先后顺序（如"快递员是在 Clara 来之前还是之后到的？"）。
- **因果/状态记忆**：设备状态变化的原因（如"为什么客厅空调关了？" -> "因为系统检测到所有人离开了客厅"）。

## JSON 数据结构与约束

生成的数据必须严格符合以下结构，任何字段缺失或类型错误都将导致校验失败。

### 1. 基础结构

每个 Episode (如一天的记录) 包含多个时间点的 Session：

```json
{
  "2023-05-05 09:30": {
    "contents": [
        {
            "role": "user",
            "content": "XXX"
        },
        {
            "role": "assistant",
            "content": "XXX"
        }
      /* 多轮对话数组 */
    ],
    "devices": {
      "episode_id": "ep_001",
      "scene": "离家场景",
      "confidence": 0.92,
      "annotated_events": [
        {
          "event": {
            "subject_id": "lao_li",
            "predicate": "entered",
            "object_id": "entrance"
          },
          "state_snapshot": {
            "timestamp": "2022-03-16T07:57:30+08:00",
            "persons": {
              "lao_li": {
                "status": "moving_to_entrance",
                "location": "entrance"
              }
            },
            "devices": {
              "light_hallway": {
                "state": "on"
              },
              "light_entrance": {
                "state": "on"
              }/*设备状态*/
            }
          }
        }/*设备列表*/
      ]
      /* 场景与设备事件元数据 */
    }
  }
}
```

### 2. `contents` (对话流)

- 必须包含 `role` ("user" / "assistant") 和 `content`。
- User 的指令必须口语化，包含隐式意图（如"有人在敲门" -> 隐式意图：查看监控并开门）。
- Assistant 的回复必须体现"感知-执行-反馈"的闭环。

### 3. `devices` (状态与事件快照)

这是本工程的核心特色，必须包含以下字段：

- `episode_id`: 字符串，当前 episode 的唯一标识。
- `scene`: 字符串，当前所属的子场景名称。
- `confidence`: 浮点数 (0.0-1.0)，AI 对当前场景判断的置信度。
- `annotated_events`: 数组，记录该时间段内发生的关键物理事件及对应的设备状态快照。

#### `annotated_events` 内部结构规范：

- `event`: 三元组 `{subject_id, predicate, object_id}`。
  - *示例*: `{"subject_id": "lao_li", "predicate": "entered", "object_id": "entrance"}`
- `state_snapshot`: 事件发生瞬间的全局状态切片。
  - `timestamp`: ISO 8601 格式，**必须与对话发生的时间线保持严格的逻辑先后顺序**。
  - `persons`: 字典，记录关键人物的 `status` 和 `location`。
  - `devices`: 字典，记录相关智能设备的 `state` (如 "on", "off", "locked", "armed_care_mode")。

## 架构约束与物理常识

- **状态机一致性**：禁止出现违反物理常识的设备状态。例如：`smart_lock_main` 为 "locked" 时，`door_main` 不能是 "open"；人不在家时，`tv_living_room` 必须是 "off"。
- **设备ID规范**：所有设备ID必须使用 `snake_case`，并带有区域前缀（如 `light_hallway`, `ac_living_room`, `camera_porch`）。**禁止捏造未在 `src/knowledge/device_graph.json` 中定义的设备**。
- **人物ID规范**：使用 `snake_case`（如 `lao_li`, `child_ming`, `visitor_clara`）。

## 注意事项（重要）

- **时间线逻辑**：`state_snapshot` 中的 `timestamp` 必须精确到秒，且必须早于或等于对应 `contents` 中 User 发起对话的时间。AI 助手是"先感知到事件/状态，后回应用户"。
- **隐私脱敏**：所有生成的数据必须使用虚构的人名、地址和联系方式，**严禁使用真实世界的 PII (个人身份信息)**。
- **保持精简**：单次生成的 JSON 不要包含无关的冗余设备状态，`state_snapshot` 中只需记录**与当前事件相关或发生变化的**核心设备状态，避免上下文爆炸。
- **异常处理**：在生成 `anomaly_detection` 场景时，Assistant 必须表现出主动告警的行为，而不是被动等待 User 询问。

## 维护与扩展

- 新增子场景时，必须同步更新 `docs/scenario-guide.md` 中的场景触发条件和预期设备联动列表。
- 如果发现生成的对话缺乏"记忆测试价值"（即全是简单的指令控制，没有上下文依赖），需调整 `src/scenarios/` 中的 Prompt，增加"跨时间段询问"的引导。

---

## 开发进度

### 已完成
1. **人物数据的采样**
   - 从 LoCoMo 数据集中采样人物数据，确保人物数据的多样性。（将LoCoMo中的双人的msc_personas_all.json中的数据改为单人数据）
   - 数据集 Speaker 数量：
     - train: 7,987
     - valid: 2,000
     - test: 2,030
     - 总计: 12,017

### TODO
1. 改为中文的人物数据
2. 将原来产生双人对话的逻辑改为单人和AI助手之间的对话
3. 增加产生指定场景下的设备记录
4. 增加产生操控一系列设备的轨迹