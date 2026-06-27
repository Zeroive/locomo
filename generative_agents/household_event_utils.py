"""
Household event generation utilities.

Events are generated before conversations and later selected into each session,
mirroring the original persona -> graph -> session flow.

扩展新分类时，只需添加以下内容：
- SCENARIOS: 新场景列表
- SCENARIO_LABELS: 场景标签（中文描述）
- SCENARIO_DIMENSIONS: 场景涉及的记忆维度
- SCENARIO_GUIDANCE: 场景生成指导
- 必要时添加 scenario_is_applicable: 场景适用性检查函数
"""

import json
import logging
import random
import re
from datetime import timedelta

from generative_agents.time_utils import catch_date, dateObj2Str, get_random_date
from generative_agents.household_utils import strip_generation_prompts


# ==================== 周末场景 ====================
# 注意：后续新增场景请直接添加到 SCENARIOS 列表，无需单独分类
# 扩展新分类时，只需添加：
# - SCENARIOS: 新场景列表
# - SCENARIO_LABELS: 场景标签（中文描述）
# - SCENARIO_DIMENSIONS: 场景涉及的记忆维度
# - SCENARIO_GUIDANCE: 场景生成指导
# - 必要时添加 scenario_is_applicable: 场景适用性检查函数

SCENARIOS = [
    # 周末场景（原有）
    "weekend_family_outing",
    "weekend_home_relaxation",
    "family_meal_plan",
    "child_weekend_activity",
    "elderly_weekend_activity",
    "pet_weekend_care",
    "couple_leisure_plan",
    "visit_relatives",
    "conflicting_plans",
    "changed_weekend_plan",
    
    # 家庭属性 - 成员构成
    "family_relationship_confirmation",
    "family_member_presence_update",
    "kinship_relation_reasoning",
    "family_nickname_reference",
    "family_interaction_pattern",
    "caregiving_responsibility_update",
    "recurring_family_event",
    "member_birthday_celebration",
    "family_member_health_event",
    "pet_adoption",
    "pet_health_check",
    # 家庭属性 - 居住房屋
    "home_maintenance_request",
    "renovation_plan",
    "furniture_purchase",
    # 家庭属性 - 财产状况
    "bill_payment_reminder",
    "large_purchase_decision",
    # 生活作息 - 工作日
    "workday_morning_routine",
    "workday_evening_routine",
    "overtime_notice",
    "work_from_home_day",
    # 生活作息 - 就餐
    "meal_preparation",
    "dining_reservation",
    "dietary_change_request",
    # 生活作息 - 就寝
    "bedtime_routine_setup",
    "sleep_disruption_report",
    # 生活作息 - 大家庭互动
    "elderly_care_arrangement",
    "extended_family_visit",
    "family_reunion_planning",
    # 生活作息 - 纪律规范
    "screen_time_limit",
    "homework_enforcement",
    "chore_assignment",
    # 生活作息 - 家务活动
    "cleaning_schedule",
    "laundry_reminder",
    "grocery_shopping",
    # 生活作息 - 家庭娱乐
    "leisure_activity_preference",
    "leisure_time_preference",
    "member_personal_leisure_preference",
    "group_leisure_preference",
    "leisure_comfort_constraint",
    "leisure_dining_budget_preference",
    "leisure_preference_change",
    "leisure_conflict_compromise",
    "movie_night_planning",
    "game_activity_arrangement",
    "holiday_celebration",
]


# ==================== 家庭画像场景（已合并到 SCENARIOS） ====================
# 家庭画像分类说明：
# 1. 家庭属性
#    - 家庭成员构成：人口、成员组成、宠物、家庭关系
#    - 居住房屋类型：房屋属性、空间分配、装修风格
#    - 财产状况：年收入、家庭资产、流动资金和负债、消费价值观
# 2. 生活作息
#    - 工作日作息：周一至周五的固定作息和流程
#    - 周末和休闲作息：周末或非工作时间的家庭活动安排
#    - 就餐规律：涉及家庭饮食时间、地点和方式的规律性
#    - 就寝规律：睡前准备和入睡过程的规律性
#    - 大家庭互动规律：涉及与核心家庭之外的人物互动的规律性
#    - 纪律规范：涉及家庭规则执行和行为管理的规律性
#    - 家务活动：涉及维持家庭环境整洁和运转的规律性
#    - 家庭娱乐活动：涉及家庭内部休闲、娱乐和互动的规律性


SCENARIO_LABELS = {
    # 周末场景
    "weekend_family_outing": "周末全家外出",
    "weekend_home_relaxation": "周末居家休息",
    "family_meal_plan": "家庭聚餐/做饭/外卖",
    "child_weekend_activity": "孩子兴趣班/作业/玩耍",
    "elderly_weekend_activity": "老人散步/买菜/社区活动",
    "pet_weekend_care": "遛狗/喂猫/宠物看护",
    "couple_leisure_plan": "夫妻二人休闲安排",
    "visit_relatives": "探亲/亲友来访",
    "conflicting_plans": "家庭成员计划冲突",
    "changed_weekend_plan": "周末计划变更",
    
    # 家庭属性 - 成员构成
    "family_relationship_confirmation": "家庭关系确认",
    "family_member_presence_update": "家庭成员出现/居住状态变化",
    "kinship_relation_reasoning": "亲属关系推理",
    "family_nickname_reference": "家庭称谓/昵称指代",
    "family_interaction_pattern": "家庭亲疏互动模式",
    "caregiving_responsibility_update": "照顾责任分工",
    "recurring_family_event": "固定家庭事件",
    "member_birthday_celebration": "家庭成员生日庆祝",
    "family_member_health_event": "家庭成员健康事件",
    "pet_adoption": "宠物领养/添置",
    "pet_health_check": "宠物健康检查/就医",
    
    # 家庭属性 - 居住房屋
    "home_maintenance_request": "房屋维修请求",
    "renovation_plan": "装修计划/改造",
    "furniture_purchase": "家具购买/更换",
    
    # 家庭属性 - 财产状况
    "bill_payment_reminder": "账单缴费提醒",
    "large_purchase_decision": "大额消费决策",
    
    # 生活作息 - 工作日
    "workday_morning_routine": "工作日早晨出门流程",
    "workday_evening_routine": "工作日晚间回家流程",
    "overtime_notice": "加班通知",
    "work_from_home_day": "居家办公日",
    
    # 生活作息 - 就餐
    "meal_preparation": "餐食准备/烹饪",
    "dining_reservation": "餐厅预约",
    "dietary_change_request": "饮食调整需求",
    
    # 生活作息 - 就寝
    "bedtime_routine_setup": "就寝流程设置",
    "sleep_disruption_report": "睡眠干扰报告",
    
    # 生活作息 - 大家庭互动
    "elderly_care_arrangement": "老人照护安排",
    "extended_family_visit": "大家庭成员来访",
    "family_reunion_planning": "家庭聚会计划",
    
    # 生活作息 - 纪律规范
    "screen_time_limit": "屏幕使用时间限制",
    "homework_enforcement": "作业监督执行",
    "chore_assignment": "家务分配调整",
    
    # 生活作息 - 家务活动
    "cleaning_schedule": "清洁打扫安排",
    "laundry_reminder": "洗衣提醒",
    "grocery_shopping": "采购/买菜",
    
    # 生活作息 - 家庭娱乐
    "leisure_activity_preference": "休闲活动类型偏好",
    "leisure_time_preference": "休闲时间偏好",
    "member_personal_leisure_preference": "成员个人休闲偏好",
    "group_leisure_preference": "家庭组合休闲偏好",
    "leisure_comfort_constraint": "休闲舒适度约束",
    "leisure_dining_budget_preference": "休闲餐饮/消费偏好",
    "leisure_preference_change": "休闲偏好变化",
    "leisure_conflict_compromise": "休闲偏好冲突与折中",
    "movie_night_planning": "家庭电影夜",
    "game_activity_arrangement": "家庭游戏活动",
    "holiday_celebration": "节日庆祝活动",
}

# 需要至少2个事件才能触发的依赖场景
DEPENDENT_SCENARIOS = [
    "family_relationship_confirmation",
    "member_birthday_celebration", 
    "movie_night_planning", 
]


# ==================== 记忆维度体系（基于维度三） ====================
# 维度一：家庭画像记忆
# 维度二：家庭属性、生活作息
# 维度三：具体分类（11个）
# 
# 记忆维度标签设计原则：
# 1. 每个维度三对应一组具体的记忆维度标签
# 2. 标签名称要能反映具体内容
# 3. 场景的记忆维度 = 所属维度三的标签 + 跨维度标签（如需要）

MEMORY_DIMENSIONS_BY_CATEGORY = {
    # 家庭属性
    "家庭成员构成": [
        "family_composition",      # 家庭人口
        "member_count",            # 成员数量
        "member_info",             # 成员基本信息（姓名、年龄、性别）
        "residence_status",        # 居住/临时到访状态
        "pet_info",                # 宠物信息
        "family_relationship",     # 家庭关系
        "kinship_reasoning",       # 亲属关系推理
        "nickname_reference",      # 昵称/称谓/指代
        "interaction_pattern",     # 亲疏互动模式
    ],
    "居住房屋类型": [
        "home_property",           # 房屋属性（面积、户型）
        "space_allocation",        # 空间分配（房间分配）
        "room_layout",             # 房间布局
        "decoration_style",        # 装修风格
    ],
    "财产状况": [
        "annual_income",           # 年收入
        "family_assets",           # 家庭资产
        "financial_status",        # 流动资金和负债
        "consumption_values",      # 消费价值观
        "expense_plan",            # 支出计划
    ],
    
    # 生活作息
    "工作日作息": [
        "weekday_routine",         # 工作日整体作息
        "work_schedule",           # 工作时间安排
        "morning_routine",         # 早晨流程
        "evening_routine",         # 晚间流程
        "commute_time",            # 通勤时间
    ],
    "周末和休闲作息": [
        "weekend_plan",            # 周末计划
        "weekend_routine",         # 周末习惯
        "leisure_activity",        # 休闲活动
        "activity_preference",     # 活动类型偏好
        "leisure_time_preference", # 休闲时间偏好
        "personal_preference",     # 成员个人偏好
        "group_preference",        # 家庭组合偏好
        "comfort_constraint",      # 活动强度/舒适度约束
        "preference_change",       # 偏好变化
        "compromise_plan",         # 折中方案
        "family_outing",           # 家庭外出
        "rest_schedule",           # 休息安排
    ],
    "就餐规律": [
        "meal_arrangement",        # 餐食安排
        "dining_time",             # 用餐时间
        "dining_location",         # 用餐地点
        "dietary_preference",      # 饮食偏好
        "cooking_plan",            # 烹饪计划
    ],
    "就寝规律": [
        "sleep_schedule",          # 睡眠时间
        "bedtime_routine",         # 睡前流程
        "sleep_environment",       # 睡眠环境
        "sleep_quality",           # 睡眠质量
    ],
    "大家庭互动规律": [
        "extended_family_interaction",  # 大家庭互动
        "grandparent_relation",         # 祖父母关系
        "relative_visit",               # 亲友来访
        "cross_member_reference",       # 跨成员引用
    ],
    "纪律规范": [
        "discipline_rules",        # 家庭规则
        "behavior_management",     # 行为管理
        "screen_time_limit",       # 屏幕时间限制
        "homework_rule",           # 作业规则
        "chore_rule",              # 家务规则
    ],
    "家务活动": [
        "home_maintenance",        # 家庭维护
        "cleaning_schedule",       # 清洁安排
        "laundry_plan",            # 洗衣计划
        "grocery_plan",            # 采购计划
        "chore_assignment",        # 家务分配
    ],
    "家庭娱乐活动": [
        "family_entertainment",    # 家庭娱乐
        "movie_night",             # 电影夜
        "game_activity",           # 游戏活动
        "hobby_activity",          # 兴趣爱好
        "holiday_plan",            # 节日计划
    ],
}

# 跨维度通用标签
CROSS_DIMENSION_TAGS = {
    "role_responsibility",     # 角色责任
    "temporary_schedule",      # 临时安排
    "preference_conflict",     # 偏好冲突
    "preference_priority",     # 偏好优先级
    "special_occasion",        # 特殊场合
    "health_status",           # 健康状况
    "care_arrangement",        # 照护安排
}


SCENARIO_DIMENSIONS = {
    # ==================== 周末场景（周末和休闲作息） ====================
    "weekend_family_outing": [
        "weekend_plan",           # 周末计划
        "family_outing",          # 家庭外出
        "cross_member_reference", # 跨成员引用（涉及多人）
    ],
    "weekend_home_relaxation": [
        "weekend_plan",           # 周末计划
        "leisure_activity",       # 休闲活动
        "rest_schedule",          # 休息安排
    ],
    "family_meal_plan": [
        "meal_arrangement",       # 餐食安排
        "dining_time",            # 用餐时间
        "role_responsibility",    # 角色责任（谁做饭）
    ],
    "child_weekend_activity": [
        "weekend_plan",           # 周末计划
        "hobby_activity",         # 兴趣爱好（兴趣班）
        "temporary_schedule",     # 临时安排（接送时间）
    ],
    "elderly_weekend_activity": [
        "weekend_plan",           # 周末计划
        "leisure_activity",       # 休闲活动（散步）
        "role_responsibility",    # 角色责任（陪同）
    ],
    "pet_weekend_care": [
        "weekend_plan",           # 周末计划
        "pet_info",               # 宠物信息
        "role_responsibility",    # 角色责任（照护人）
    ],
    "couple_leisure_plan": [
        "weekend_plan",           # 周末计划
        "leisure_activity",       # 休闲活动
        "family_relationship",    # 家庭关系（夫妻）
    ],
    "visit_relatives": [
        "weekend_plan",           # 周末计划
        "relative_visit",         # 亲友来访
        "cross_member_reference", # 跨成员引用
    ],
    "conflicting_plans": [
        "weekend_plan",           # 周末计划
        "preference_conflict",    # 偏好冲突
        "cross_member_reference", # 跨成员引用
    ],
    "changed_weekend_plan": [
        "weekend_plan",           # 周末计划
        "temporary_schedule",     # 临时安排（变更）
    ],
    
    # ==================== 家庭属性 - 家庭成员构成 ====================
    "family_relationship_confirmation": [
        "member_info",            # 成员信息
        "family_relationship",    # 家庭关系（亲子/夫妻/祖孙等）
        "cross_member_reference", # 跨成员引用（谁是谁的亲属）
    ],
    "family_member_presence_update": [
        "family_composition",     # 家庭成员构成
        "residence_status",       # 居住/临时到访状态
        "temporary_schedule",     # 临时安排（回来/到访时间）
    ],
    "kinship_relation_reasoning": [
        "family_relationship",    # 家庭关系
        "kinship_reasoning",      # 亲属关系推理
        "cross_member_reference", # 跨成员引用（爸爸的弟弟等）
    ],
    "family_nickname_reference": [
        "member_info",            # 成员信息
        "nickname_reference",     # 昵称/称谓/指代
        "cross_member_reference", # 跨成员引用
    ],
    "family_interaction_pattern": [
        "family_relationship",    # 家庭关系
        "interaction_pattern",    # 亲疏互动模式
        "preference_conflict",    # 沟通/偏好冲突
    ],
    "caregiving_responsibility_update": [
        "family_relationship",    # 家庭关系
        "role_responsibility",    # 角色责任
        "care_arrangement",       # 照护安排
    ],
    "recurring_family_event": [
        "family_composition",     # 家庭成员构成
        "special_occasion",       # 固定家庭事件/特殊日期
        "temporary_schedule",     # 时间安排
    ],
    "member_birthday_celebration": [
        "member_info",            # 成员信息（生日对象）
        "family_relationship",    # 家庭关系
        "special_occasion",       # 特殊场合（生日）
    ],
    "family_member_health_event": [
        "member_info",            # 成员信息
        "health_status",          # 健康状况
        "care_arrangement",       # 照护安排
    ],
    "pet_adoption": [
        "pet_info",               # 宠物信息
        "family_composition",     # 家庭构成（新增成员）
        "family_relationship",    # 家庭关系
    ],
    "pet_health_check": [
        "pet_info",               # 宠物信息
        "health_status",          # 健康状况
        "role_responsibility",    # 角色责任（谁带去就医）
    ],
    
    # ==================== 家庭属性 - 居住房屋类型 ====================
    "home_maintenance_request": [
        "home_property",          # 房屋属性
        "space_allocation",       # 空间分配（哪个区域）
        "temporary_schedule",     # 临时安排（维修时间）
    ],
    "renovation_plan": [
        "home_property",          # 房屋属性
        "decoration_style",       # 装修风格
        "expense_plan",           # 支出计划（预算）
    ],
    "furniture_purchase": [
        "home_property",          # 房屋属性
        "space_allocation",       # 空间分配（放置位置）
        "consumption_values",     # 消费价值观
    ],
    
    # ==================== 家庭属性 - 财产状况 ====================
    "bill_payment_reminder": [
        "financial_status",       # 财务状况
        "expense_plan",           # 支出计划
        "temporary_schedule",     # 临时安排（缴费时间）
    ],
    "large_purchase_decision": [
        "financial_status",       # 财务状况
        "consumption_values",     # 消费价值观
        "cross_member_reference", # 跨成员引用（家庭决策）
    ],
    
    # ==================== 生活作息 - 工作日作息 ====================
    "workday_morning_routine": [
        "weekday_routine",        # 工作日作息
        "morning_routine",        # 早晨流程
        "commute_time",           # 通勤时间
    ],
    "workday_evening_routine": [
        "weekday_routine",        # 工作日作息
        "evening_routine",        # 晚间流程
        "dining_time",            # 用餐时间（晚餐）
    ],
    "overtime_notice": [
        "work_schedule",          # 工作时间
        "temporary_schedule",     # 临时安排（加班）
        "cross_member_reference", # 跨成员引用（通知家人）
    ],
    "work_from_home_day": [
        "work_schedule",          # 工作时间
        "space_allocation",       # 空间分配（工作区域）
        "weekday_routine",        # 工作日作息
    ],
    
    # ==================== 生活作息 - 就餐规律 ====================
    "meal_preparation": [
        "meal_arrangement",       # 餐食安排
        "cooking_plan",           # 烹饪计划
        "role_responsibility",    # 角色责任（谁做饭）
    ],
    "dining_reservation": [
        "meal_arrangement",       # 餐食安排
        "dining_location",        # 用餐地点（餐厅）
        "temporary_schedule",     # 临时安排（预约时间）
    ],
    "dietary_change_request": [
        "dietary_preference",     # 饮食偏好
        "health_status",          # 健康状况
        "meal_arrangement",       # 餐食安排
    ],
    
    # ==================== 生活作息 - 就寝规律 ====================
    "bedtime_routine_setup": [
        "sleep_schedule",         # 睡眠时间
        "bedtime_routine",        # 睡前流程
        "sleep_environment",      # 睡眠环境
    ],
    "sleep_disruption_report": [
        "sleep_schedule",         # 睡眠时间
        "sleep_quality",          # 睡眠质量
        "health_status",          # 健康状况
    ],
    
    # ==================== 生活作息 - 大家庭互动规律 ====================
    "elderly_care_arrangement": [
        "grandparent_relation",   # 祖父母关系
        "care_arrangement",       # 照护安排
        "cross_member_reference", # 跨成员引用
    ],
    "extended_family_visit": [
        "relative_visit",         # 亲友来访
        "extended_family_interaction",  # 大家庭互动
        "temporary_schedule",     # 临时安排（来访时间）
    ],
    "family_reunion_planning": [
        "extended_family_interaction",  # 大家庭互动
        "special_occasion",       # 特殊场合（聚会）
        "cross_member_reference", # 跨成员引用
    ],
    
    # ==================== 生活作息 - 纪律规范 ====================
    "screen_time_limit": [
        "discipline_rules",       # 家庭规则
        "screen_time_limit",      # 屏幕时间限制
        "behavior_management",    # 行为管理
    ],
    "homework_enforcement": [
        "discipline_rules",       # 家庭规则
        "homework_rule",          # 作业规则
        "role_responsibility",    # 角色责任（监督人）
    ],
    "chore_assignment": [
        "discipline_rules",       # 家庭规则
        "chore_rule",             # 家务规则
        "chore_assignment",       # 家务分配
    ],
    
    # ==================== 生活作息 - 家务活动 ====================
    "cleaning_schedule": [
        "cleaning_schedule",      # 清洁安排
        "space_allocation",       # 空间分配（清洁区域）
        "role_responsibility",    # 角色责任
    ],
    "laundry_reminder": [
        "laundry_plan",           # 洗衣计划
        "temporary_schedule",     # 临时安排（洗衣时间）
        "role_responsibility",    # 角色责任
    ],
    "grocery_shopping": [
        "grocery_plan",           # 采购计划
        "expense_plan",           # 支出计划（预算）
        "role_responsibility",    # 角色责任
    ],
    
    # ==================== 生活作息 - 家庭娱乐活动 ====================
    "leisure_activity_preference": [
        "weekend_routine",        # 周末习惯
        "activity_preference",    # 活动类型偏好
        "leisure_activity",       # 休闲活动
    ],
    "leisure_time_preference": [
        "weekend_routine",        # 周末习惯
        "leisure_time_preference",# 活动时段/时长偏好
        "rest_schedule",          # 休息缓冲
    ],
    "member_personal_leisure_preference": [
        "personal_preference",    # 成员个人偏好
        "leisure_activity",       # 休闲活动
        "cross_member_reference", # 跨成员引用
    ],
    "group_leisure_preference": [
        "group_preference",       # 家庭组合偏好
        "family_entertainment",   # 家庭娱乐
        "family_relationship",    # 家庭关系（组合关系）
    ],
    "leisure_comfort_constraint": [
        "comfort_constraint",     # 强度/距离/噪声/天气约束
        "leisure_activity",       # 休闲活动
        "health_status",          # 身体或舒适度状态
    ],
    "leisure_dining_budget_preference": [
        "dietary_preference",     # 餐饮偏好
        "expense_plan",           # 消费预算
        "leisure_activity",       # 休闲活动
    ],
    "leisure_preference_change": [
        "preference_change",      # 偏好变化
        "temporary_schedule",     # 短期状态/最近变化
        "leisure_activity",       # 休闲活动
    ],
    "leisure_conflict_compromise": [
        "preference_conflict",    # 偏好冲突
        "preference_priority",    # 优先级
        "compromise_plan",        # 折中方案
    ],
    "movie_night_planning": [
        "movie_night",            # 电影夜
        "family_entertainment",   # 家庭娱乐
        "temporary_schedule",     # 临时安排（观影时间）
    ],
    "game_activity_arrangement": [
        "game_activity",          # 游戏活动
        "family_entertainment",   # 家庭娱乐
        "cross_member_reference", # 跨成员引用（参与人员）
    ],
    "holiday_celebration": [
        "holiday_plan",           # 节日计划
        "special_occasion",       # 特殊场合（节日）
        "family_relationship",    # 家庭关系
    ],
}


SCENARIO_GUIDANCE = {
    # 周末场景
    "weekend_family_outing": "全家或多名成员外出，重点是地点、出门准备、交通或天气。",
    "weekend_home_relaxation": "居家休息，重点是家庭成员休闲偏好和家务/娱乐安排。",
    "family_meal_plan": "家庭聚餐、做饭、外食或外卖安排，体现责任分工。",
    "child_weekend_activity": "孩子兴趣班、作业、玩耍或接送安排，必须有孩子或青少年参与。",
    "elderly_weekend_activity": "老人散步、买菜、社区活动或探亲，必须有老人参与。",
    "pet_weekend_care": "宠物喂养、遛宠、清洁或看护，只让照护人参与，宠物不作为用户。",
    "couple_leisure_plan": "夫妻/伴侣二人休闲安排，体现与其他家庭事项的协调。",
    "visit_relatives": "探亲或亲友来访，体现用餐、到达时间或接待准备。",
    "conflicting_plans": "多个成员周末偏好或时间冲突，后续可能需要协调。",
    "changed_weekend_plan": "已有安排发生变更，必须引用或承接一个更早事件。",
    
    # 家庭属性 - 成员构成
    "family_relationship_confirmation": "家庭关系确认，重点是明确成员之间的亲属称谓或监护关系，例如谁是谁的爸爸、妈妈、孩子或祖父母。",
    "family_member_presence_update": "家庭成员出现或居住状态变化，重点是谁平时是否同住、这周末谁会回来或临时到访。",
    "kinship_relation_reasoning": "亲属关系推理，重点是通过多跳关系表达称谓，例如爸爸的弟弟、妈妈的妈妈、孩子的外婆等。",
    "family_nickname_reference": "家庭称谓、昵称或代词指代，重点是某个成员的小名、惯用称呼，或“她/孩子/老二”指向谁。",
    "family_interaction_pattern": "家庭亲疏与互动模式，重点是谁和谁更亲近、容易冲突、沟通需要委婉，及其对安排的影响。",
    "caregiving_responsibility_update": "照顾责任或家务分工，重点是谁负责照顾谁、接送谁、提醒谁或承担某项家庭任务。",
    "recurring_family_event": "固定家庭事件或特殊日期，重点是每周固定活动、生日/纪念日/探亲等长期和短期时间记忆。",
    "member_birthday_celebration": "家庭成员生日或纪念日庆祝，重点是庆祝准备、礼物选择或家庭聚餐安排。",
    "family_member_health_event": "家庭成员健康问题或医疗事件，重点是看医生、用药提醒或照护安排。",
    "pet_adoption": "宠物领养或新宠物到来，重点是新宠物适应、家庭成员反应或宠物用品准备。",
    "pet_health_check": "宠物健康检查或就医，重点是预约兽医、用药或术后护理。",
    
    # 家庭属性 - 居住房屋
    "home_maintenance_request": "房屋维修或物业问题，重点是报修、设备故障或环境调节需求。",
    "renovation_plan": "装修或房屋改造计划，重点是方案讨论、预算或时间安排。",
    "furniture_purchase": "家具购买或更换，重点是选购、配送或安装安排。",
    
    # 家庭属性 - 财产状况
    "bill_payment_reminder": "账单缴费提醒，重点是水电网费、保险或房贷等定期支出。",
    "large_purchase_decision": "大额消费决策，重点是家庭成员意见统一、预算或性价比讨论。",
    
    # 生活作息 - 工作日
    "workday_morning_routine": "工作日早晨出门准备，重点是闹钟、早餐、出门检查或交通安排。",
    "workday_evening_routine": "工作日晚间回家流程，重点是晚餐、孩子作业检查或休息安排。",
    "overtime_notice": "加班通知或工作时间变更，重点是回家时间调整或家庭安排受影响。",
    "work_from_home_day": "居家办公日，重点是工作环境准备、家人配合或工作休息平衡。",
    
    # 生活作息 - 就餐
    "meal_preparation": "餐食准备或烹饪，重点是食材准备、烹饪分工或时间安排。",
    "dining_reservation": "餐厅预约，重点是地点选择、人数确认或特殊需求说明。",
    "dietary_change_request": "饮食调整需求，重点是健康饮食、特殊饮食要求或减肥计划。",
    
    # 生活作息 - 就寝
    "bedtime_routine_setup": "就寝流程设置，重点是睡前习惯、设备调节或睡眠环境优化。",
    "sleep_disruption_report": "睡眠干扰报告，重点是噪音、光线或健康问题导致的睡眠问题。",
    
    # 生活作息 - 大家庭互动
    "elderly_care_arrangement": "老人照护安排，重点是陪护人员、送餐服务或紧急联系方案。",
    "extended_family_visit": "大家庭成员来访，重点是接待准备、住宿安排或活动规划。",
    "family_reunion_planning": "家庭聚会计划，重点是时间地点、参与人员或传统习俗。",
    
    # 生活作息 - 纪律规范
    "screen_time_limit": "屏幕使用时间限制，重点是规则说明、执行监督或超时处理。",
    "homework_enforcement": "作业监督执行，重点是作业完成检查、学习习惯培养或辅导安排。",
    "chore_assignment": "家务分配调整，重点是任务分配、责任轮换或完成度检查。",
    
    # 生活作息 - 家务活动
    "cleaning_schedule": "清洁打扫安排，重点是区域划分、清洁频率或特殊清洁需求。",
    "laundry_reminder": "洗衣提醒，重点是衣物分类、洗涤方式或晾晒收衣安排。",
    "grocery_shopping": "采购或买菜，重点是购物清单、库存检查或预算控制。",
    
    # 生活作息 - 家庭娱乐
    "leisure_activity_preference": "休闲活动类型偏好，重点是室内、户外、社交、文化娱乐或亲子活动中成员更喜欢哪类。",
    "leisure_time_preference": "休闲时间偏好，重点是周末节奏、活动时段、活动时长、固定空闲时间和休息缓冲。",
    "member_personal_leisure_preference": "成员个人休闲偏好，重点是用户、父母、孩子、老人或宠物相关的个性化活动偏好。",
    "group_leisure_preference": "家庭组合休闲偏好，重点是全家、父母二人、兄弟姐妹、亲子、祖孙等组合的共同偏好。",
    "leisure_comfort_constraint": "休闲舒适度约束，重点是体力强度、人群密度、距离、天气、噪声或健康限制。",
    "leisure_dining_budget_preference": "休闲餐饮和消费偏好，重点是吃什么、忌口、预算、外食/在家、甜品饮品等。",
    "leisure_preference_change": "休闲偏好变化，重点是长期偏好、近期新偏好、临时状态、季节性偏好或旧偏好被更新。",
    "leisure_conflict_compromise": "休闲偏好冲突与折中，重点是成员偏好冲突、优先级、轮流机制、避免项和可兼顾的折中方案。",
    "movie_night_planning": "家庭电影夜，重点是影片选择、零食准备或时间安排。",
    "game_activity_arrangement": "家庭游戏活动，重点是游戏选择、参与人员或竞技规则。",
    "holiday_celebration": "节日庆祝活动，重点是节日装饰、礼物准备或节日传统活动。",
}


HOUSEHOLD_SINGLE_EVENT_PROMPT = """
你是家庭多用户 AI 助手测评数据集的事件记忆点生成器。

请根据已经由程序规划好的 event_plan，为这个家庭生成一个周末/休闲主题事件。

要求：
- 输出必须是 JSON 对象，不要输出 markdown。
- 必须保留 event_plan 中的 id、date、scenario_type、participants、mentioned_members、caused_by、memory_dimensions，不要改动。
- 只需要生成或补充 "sub-event"。
- sub-event 使用中文，30-60字，必须具体、自然、可用于后续用户与 AI 助手对话。
- sub-event 必须符合 scenario_type、参与成员角色、家庭关系、宠物信息和时间先后逻辑。
- 如果 caused_by 非空，sub-event 要自然体现它是由 previous_events 中的前置事件引发或调整而来。
- 不要引入 household_profile 中不存在的新成员。
- 宠物只能作为照护对象，不能作为 participants。

关键信息:
{context}

previous_events:
{previous_events}

event_plan:
{event_plan}
""".strip()


def parse_json_array(text):
    text = text.strip().replace("```json", "").replace("```", "").strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if not match:
            raise
        data = json.loads(match.group())
    if not isinstance(data, list):
        raise ValueError("Expected a JSON array")
    return data


def parse_json_object(text):
    text = text.strip().replace("```json", "").replace("```", "").strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise
        data = json.loads(match.group())
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object")
    return data


def member_names(profile, ids):
    names = {member["person_id"]: member["name"] for member in profile["members"]}
    return [names[person_id] for person_id in ids if person_id in names]


def members_by_stage(profile, stages):
    return [member for member in profile["members"] if member.get("life_stage") in stages]


def parent_child_relation_pairs(profile):
    member_ids = {member["person_id"] for member in profile.get("members", [])}
    return [
        (rel["from"], rel["to"])
        for rel in profile.get("relations", [])
        if (
            rel.get("type") == "PARENT_OF"
            and rel.get("from") in member_ids
            and rel.get("to") in member_ids
        )
    ]


def choose_participants(profile, scenario_type):
    adults = members_by_stage(profile, {"adult"})
    elders = members_by_stage(profile, {"elderly"})
    children = members_by_stage(profile, {"child", "teenager"})
    members = profile["members"]

    if scenario_type in {"family_relationship_confirmation", "kinship_relation_reasoning"}:
        relation_pairs = parent_child_relation_pairs(profile)
        if relation_pairs:
            parent_id, child_id = random.choice(relation_pairs)
            return [parent_id, child_id]
    if scenario_type == "child_weekend_activity" and children:
        return [random.choice(children)["person_id"]] + [random.choice(adults or members)["person_id"]]
    if scenario_type == "elderly_weekend_activity" and elders:
        return [random.choice(elders)["person_id"]] + [random.choice(adults or members)["person_id"]]
    if scenario_type == "pet_weekend_care" and profile.get("pets"):
        return [profile["pets"][0]["caretaker_id"]]
    if scenario_type == "couple_leisure_plan" and len(adults) >= 2:
        return [adults[0]["person_id"], adults[1]["person_id"]]
    if scenario_type in {"conflicting_plans", "changed_weekend_plan"}:
        sample_size = min(3, len(members))
        return [m["person_id"] for m in random.sample(members, sample_size)]
    sample_size = min(random.choice([2, 3]), len(members))
    return [m["person_id"] for m in random.sample(members, sample_size)]


def scenario_is_applicable(profile, scenario_type):
    if scenario_type in {"family_relationship_confirmation", "kinship_relation_reasoning"}:
        return bool(parent_child_relation_pairs(profile))
    if scenario_type == "child_weekend_activity":
        return bool(members_by_stage(profile, {"child", "teenager"}))
    if scenario_type == "elderly_weekend_activity":
        return bool(members_by_stage(profile, {"elderly"}))
    if scenario_type == "pet_weekend_care":
        return bool(profile.get("pets"))
    if scenario_type == "couple_leisure_plan":
        return len(members_by_stage(profile, {"adult"})) >= 2
    return True


def build_event_scenario_sequence(profile, num_events, dependent_scenarios=None):
    if dependent_scenarios is None:
        dependent_scenarios = DEPENDENT_SCENARIOS
    required = dependent_scenarios if num_events >= 2 else []
    candidates = [scenario for scenario in SCENARIOS if scenario_is_applicable(profile, scenario)]
    sequence = []
    for scenario in required:
        if scenario_is_applicable(profile, scenario):
            sequence.append(scenario)
    remaining_slots = max(0, num_events - len(sequence))
    remaining_candidates = [scenario for scenario in candidates if scenario not in sequence]
    if remaining_slots:
        if len(remaining_candidates) >= remaining_slots:
            sequence.extend(random.sample(remaining_candidates, remaining_slots))
        else:
            sequence.extend(remaining_candidates)
    while len(sequence) < num_events:
        sequence.append(random.choice(remaining_candidates or candidates or ["weekend_home_relaxation"]))
    # Keep changed_weekend_plan after at least one event so it can refer backward.
    if "changed_weekend_plan" in sequence and sequence.index("changed_weekend_plan") == 0 and len(sequence) > 1:
        sequence[0], sequence[1] = sequence[1], sequence[0]
    return sequence[:num_events]


def build_event_plan(profile, idx, scenario_type, start_date, num_days, num_events, previous_events):
    spacing = max(2, num_days // max(1, num_events))
    event_date = start_date + timedelta(days=min(num_days, idx * spacing))
    participants = choose_participants(profile, scenario_type)
    mentioned = [
        member["person_id"] for member in profile["members"]
        if member["person_id"] not in participants and random.random() < 0.35
    ]
    caused_by = []
    if previous_events and scenario_type == "changed_weekend_plan":
        caused_by = [previous_events[-1]["id"]]
    elif previous_events and scenario_type == "conflicting_plans" and random.random() < 0.5:
        caused_by = [previous_events[-1]["id"]]
    return {
        "id": f"E{idx}",
        "date": dateObj2Str(event_date),
        "scenario_type": scenario_type,
        "scenario_category": scenario_type,
        "scenario_label": SCENARIO_LABELS[scenario_type],
        "scenario_guidance": SCENARIO_GUIDANCE.get(scenario_type, ""),
        "participants": participants,
        "mentioned_members": mentioned,
        "caused_by": caused_by,
        "memory_dimensions": SCENARIO_DIMENSIONS[scenario_type],
    }


def compact_member_for_event(member):
    member = strip_generation_prompts(member)
    traits = member.get("traits", {})
    preferences = "、".join(traits.get("preferences", [])[:2])
    routines = "、".join(traits.get("daily_routines", [])[:1])
    return {
        "person_id": member["person_id"],
        "name": member["name"],
        "age": member.get("age"),
        "life_stage": member.get("life_stage"),
        "family_role_label": member.get("family_role_label"),
        "summary": member.get("persona_summary", ""),
        "traits": "；".join([item for item in [preferences, routines] if item]),
    }


def build_event_prompt_context(profile, event_plan, previous_events):
    profile = strip_generation_prompts(profile)
    previous_events = strip_generation_prompts(previous_events)
    relevant_ids = set(event_plan.get("participants", [])) | set(event_plan.get("mentioned_members", []))
    members = [
        compact_member_for_event(member)
        for member in profile.get("members", [])
        if member["person_id"] in relevant_ids
    ]
    relations = [
        rel for rel in profile.get("relations", [])
        if rel.get("from") in relevant_ids and rel.get("to") in relevant_ids
    ]
    pets = [
        pet for pet in profile.get("pets", [])
        if pet.get("caretaker_id") in relevant_ids
    ]
    responsibilities = [
        item for item in profile.get("role_responsibilities", [])
        if item.get("person_id") in relevant_ids
    ]
    previous_event_summaries = [
        {
            "id": event["id"],
            "date": event["date"],
            "scenario_type": event["scenario_type"],
            "sub-event": event["sub-event"],
        }
        for event in previous_events[-3:]
        if event["id"] in event_plan.get("caused_by", []) or event_plan.get("scenario_type") in {"changed_weekend_plan", "conflicting_plans"}
    ]
    return {
        "family": {
            "family_id": profile.get("family", {}).get("family_id"),
            "family_name": profile.get("family", {}).get("family_name"),
            "household_type": profile.get("family", {}).get("household_type"),
            "weekend_context": profile.get("family", {}).get("weekend_context"),
        },
        "relevant_members": members,
        "relevant_relations": relations,
        "relevant_pets": pets,
        "relevant_responsibilities": responsibilities,
        "previous_events": previous_event_summaries,
    }


def format_event_context_text(prompt_context):
    family = prompt_context["family"]
    lines = [
        f"家庭: {family.get('family_name')}，类型={family.get('household_type')}。",
    ]
    if family.get("weekend_context"):
        lines.append(f"周末背景: {family['weekend_context']}")
    if prompt_context["relevant_members"]:
        member_text = []
        for member in prompt_context["relevant_members"]:
            desc = f"{member['person_id']}={member['name']}({member.get('age')}岁,{member.get('family_role_label')},{member.get('life_stage')})"
            if member.get("traits"):
                desc += f"，特征:{member['traits']}"
            if member.get("summary"):
                desc += f"，简介:{member['summary']}"
            member_text.append(desc)
        lines.append("相关成员: " + "；".join(member_text))
    if prompt_context["relevant_relations"]:
        relations = [
            f"{rel['from']}-{rel['type']}-{rel['to']}"
            for rel in prompt_context["relevant_relations"][:4]
        ]
        lines.append("相关关系: " + "；".join(relations))
    if prompt_context["relevant_pets"]:
        pets = [
            f"{pet.get('pet_id')}={pet.get('name')}({pet.get('species')}),照护人={pet.get('caretaker_id')}"
            for pet in prompt_context["relevant_pets"]
        ]
        lines.append("相关宠物: " + "；".join(pets))
    if prompt_context["relevant_responsibilities"]:
        responsibilities = [
            f"{item.get('person_id')}:{item.get('responsibility', '')}"
            for item in prompt_context["relevant_responsibilities"][:4]
        ]
        lines.append("相关责任: " + "；".join(responsibilities))
    return "\n".join(lines)


def compact_previous_events_for_prompt(previous_events):
    return "\n".join([
        f"{event['id']}({event['date']},{event['scenario_type']}): {event['sub-event']}"
        for event in previous_events[-2:]
    ]) or "无"


def compact_event_plan_for_prompt(event_plan):
    return {
        "id": event_plan["id"],
        "date": event_plan["date"],
        "scenario_type": event_plan["scenario_type"],
        "scenario_label": event_plan["scenario_label"],
        "scenario_guidance": event_plan["scenario_guidance"],
        "participants": event_plan["participants"],
        "mentioned_members": event_plan["mentioned_members"],
        "caused_by": event_plan["caused_by"],
        "memory_dimensions": event_plan["memory_dimensions"],
    }


def render_event(profile, scenario_type, participants):
    names = member_names(profile, participants)
    pet = profile.get("pets", [{}])[0] if profile.get("pets") else None
    primary = names[0] if names else "家人"
    secondary = names[1] if len(names) > 1 else "其他家人"

    templates = {
        "family_relationship_confirmation": f"{primary}和{secondary}确认家庭称谓和监护关系，方便之后准确提醒谁是谁的爸爸、妈妈或孩子。",
        "family_member_presence_update": f"{primary}提到{secondary}这个周末会回家或来住几天，需要把家里临时多出的成员记下来。",
        "kinship_relation_reasoning": f"{primary}向助手确认{secondary}和其他家人的亲属称谓，后续可以回答谁是谁的爸爸、妈妈或长辈。",
        "family_nickname_reference": f"{primary}说明家里常用昵称或称呼习惯，例如{secondary}的小名，之后用昵称也能指到同一个人。",
        "family_interaction_pattern": f"{primary}提醒安排活动时要考虑{secondary}的沟通习惯和亲疏关系，避免触发家庭成员间的小冲突。",
        "caregiving_responsibility_update": f"{primary}和{secondary}重新确认照顾或家务分工，明确谁负责接送、提醒或照看家人。",
        "recurring_family_event": f"{'、'.join(names)}确认一个固定家庭活动或特殊日期，之后提醒时要结合每周或纪念日安排。",
        "leisure_activity_preference": f"{'、'.join(names)}讨论周末更喜欢室内、户外、社交或亲子活动，形成家庭休闲偏好记忆。",
        "leisure_time_preference": f"{primary}说明周末活动更适合安排在某个时段，{secondary}也需要保留休息缓冲。",
        "member_personal_leisure_preference": f"{primary}提到自己或{secondary}的个人休闲偏好，之后推荐周末活动时要个性化考虑。",
        "group_leisure_preference": f"{'、'.join(names)}讨论不同成员组合适合的活动，例如全家、亲子或祖孙一起做什么更合适。",
        "leisure_comfort_constraint": f"{primary}提醒周末活动要考虑{secondary}的体力、距离、天气、人群或噪声限制。",
        "leisure_dining_budget_preference": f"{'、'.join(names)}讨论周末休闲时吃什么和花多少钱，包含餐饮口味、忌口或预算偏好。",
        "leisure_preference_change": f"{primary}说明最近休闲偏好发生变化，过去喜欢的活动这段时间可能不再优先。",
        "leisure_conflict_compromise": f"{'、'.join(names)}的休闲偏好不完全一致，需要按优先级或轮流机制找到折中方案。",
        "weekend_family_outing": f"{'、'.join(names)}计划周末上午一起去公园或商场，出门前需要确认天气和交通。",
        "weekend_home_relaxation": f"{primary}提议周末在家休息，{secondary}想安排电影、整理房间或简单运动。",
        "family_meal_plan": f"{'、'.join(names)}讨论周末家庭聚餐，决定提前准备食材或选择外卖。",
        "child_weekend_activity": f"{primary}周末有兴趣班或作业安排，{secondary}需要提醒时间并协调接送。",
        "elderly_weekend_activity": f"{primary}想周末去社区活动或散步，{secondary}需要关注出门时间和身体状况。",
        "pet_weekend_care": f"{primary}负责周末照看宠物{pet['name'] if pet else '宠物'}，需要安排喂食、清洁或遛宠。",
        "couple_leisure_plan": f"{primary}和{secondary}想安排一次夫妻二人的休闲活动，但要避开家庭其他事项。",
        "visit_relatives": f"{'、'.join(names)}计划周末探亲或接待亲友来访，需要提前协调用餐和到达时间。",
        "conflicting_plans": f"{'、'.join(names)}的周末安排出现冲突，有人想外出，有人更想在家休息。",
        "changed_weekend_plan": f"{primary}临时改变周末计划，{secondary}需要重新调整家庭活动和提醒事项。",
    }
    return templates.get(
        scenario_type,
        f"{'、'.join(names) or '家人'}围绕{SCENARIO_LABELS.get(scenario_type, scenario_type)}进行安排，需要确认参与人员、时间和具体事项。",
    )


def generate_template_household_events(profile, num_events, num_days=60, start_date=None, dependent_scenarios=None):
    if start_date is None:
        start_date = get_random_date()
    end_date = start_date + timedelta(days=num_days)

    graph = []
    selected_scenarios = build_event_scenario_sequence(profile, num_events, dependent_scenarios=dependent_scenarios)
    for idx, scenario_type in enumerate(selected_scenarios[:num_events], start=1):
        event_plan = build_event_plan(profile, idx, scenario_type, start_date, num_days, num_events, graph)
        graph.append({
            "id": event_plan["id"],
            "sub-event": render_event(profile, scenario_type, event_plan["participants"]),
            "date": event_plan["date"],
            "caused_by": event_plan["caused_by"],
            "scenario_type": scenario_type,
            "scenario_category": scenario_type,
            "scenario_label": SCENARIO_LABELS[scenario_type],
            "participants": event_plan["participants"],
            "mentioned_members": event_plan["mentioned_members"],
            "memory_dimensions": SCENARIO_DIMENSIONS[scenario_type],
        })

    profile["events_start_date"] = dateObj2Str(start_date)
    profile["graph"] = graph
    profile["events_end_date"] = dateObj2Str(end_date)
    applicable_scenarios = [scenario for scenario in SCENARIOS if scenario_is_applicable(profile, scenario)]
    generated_scenarios = [event["scenario_type"] for event in graph]
    profile["event_scenario_catalog"] = {
        scenario: {
            "label": SCENARIO_LABELS[scenario],
            "memory_dimensions": SCENARIO_DIMENSIONS[scenario],
            "guidance": SCENARIO_GUIDANCE[scenario],
            "applicable": scenario in applicable_scenarios,
        }
        for scenario in SCENARIOS
    }
    profile["event_scenario_coverage"] = {
        "generated": generated_scenarios,
        "covered": sorted(set(generated_scenarios)),
        "applicable": applicable_scenarios,
        "missing_applicable": [scenario for scenario in applicable_scenarios if scenario not in generated_scenarios],
        "dependent_scenarios": list(DEPENDENT_SCENARIOS if dependent_scenarios is None else dependent_scenarios),
    }
    return graph


def normalize_event_graph(raw_events, profile, num_events, start_date, end_date):
    member_ids = {member["person_id"] for member in profile["members"]}
    normalized = []
    existing_ids = set()

    for idx, event in enumerate(raw_events[:num_events], start=1):
        if not isinstance(event, dict):
            continue
        event_id = str(event.get("id") or f"E{idx}")
        if not re.match(r"^E\d+$", event_id) or event_id in existing_ids:
            event_id = f"E{idx}"
        existing_ids.add(event_id)

        scenario_type = event.get("scenario_type")
        if scenario_type not in SCENARIOS:
            scenario_type = SCENARIOS[(idx - 1) % len(SCENARIOS)]

        participants = [pid for pid in event.get("participants", []) if pid in member_ids]
        if not participants:
            participants = choose_participants(profile, scenario_type)
        mentioned = [
            pid for pid in event.get("mentioned_members", [])
            if pid in member_ids and pid not in participants
        ]

        caused_by = [
            eid for eid in event.get("caused_by", [])
            if eid in existing_ids and eid != event_id
        ]

        date_text = event.get("date") or dateObj2Str(start_date + timedelta(days=idx))
        try:
            event_date = catch_date(date_text)
            if event_date < catch_date(dateObj2Str(start_date)) or event_date > catch_date(dateObj2Str(end_date)):
                date_text = dateObj2Str(start_date + timedelta(days=idx))
        except Exception:
            date_text = dateObj2Str(start_date + timedelta(days=idx))

        normalized.append({
            "id": event_id,
            "sub-event": event.get("sub-event") or render_event(profile, scenario_type, participants),
            "date": date_text,
            "caused_by": caused_by,
            "scenario_type": scenario_type,
            "participants": participants,
            "mentioned_members": mentioned,
            "memory_dimensions": event.get("memory_dimensions") or SCENARIO_DIMENSIONS[scenario_type],
        })

    if len(normalized) < num_events:
        fallback = generate_template_household_events(profile, num_events, (end_date - start_date).days, start_date)
        seen = {event["id"] for event in normalized}
        normalized.extend([event for event in fallback if event["id"] not in seen][:num_events - len(normalized)])

    scenario_types = {event["scenario_type"] for event in normalized}
    if num_events >= 2 and "conflicting_plans" not in scenario_types:
        normalized[0]["scenario_type"] = "conflicting_plans"
        normalized[0]["memory_dimensions"] = SCENARIO_DIMENSIONS["conflicting_plans"]
    if num_events >= 2 and "changed_weekend_plan" not in scenario_types:
        normalized[1]["scenario_type"] = "changed_weekend_plan"
        normalized[1]["memory_dimensions"] = SCENARIO_DIMENSIONS["changed_weekend_plan"]

    return normalized[:num_events]


def normalize_single_event(raw_event, event_plan, profile):
    member_ids = {member["person_id"] for member in profile["members"]}
    event = dict(event_plan)
    if isinstance(raw_event, dict) and raw_event.get("sub-event"):
        event["sub-event"] = raw_event["sub-event"]
    else:
        event["sub-event"] = render_event(profile, event_plan["scenario_type"], event_plan["participants"])
    event["participants"] = [pid for pid in event_plan["participants"] if pid in member_ids]
    event["mentioned_members"] = [pid for pid in event_plan["mentioned_members"] if pid in member_ids and pid not in event["participants"]]
    event["caused_by"] = list(event_plan.get("caused_by", []))
    event["memory_dimensions"] = SCENARIO_DIMENSIONS[event_plan["scenario_type"]]
    event["scenario_category"] = event_plan["scenario_type"]
    event["scenario_label"] = SCENARIO_LABELS[event_plan["scenario_type"]]
    event.pop("scenario_guidance", None)
    return event


def validate_event_timeline(graph, profile):
    member_ids = {member["person_id"] for member in profile.get("members", [])}
    event_dates = {}
    previous_date = None
    for event in graph:
        event_date = catch_date(event["date"])
        if previous_date and event_date < previous_date:
            raise ValueError(f"Event dates are not non-decreasing at {event['id']}")
        previous_date = event_date
        event_dates[event["id"]] = event_date
        unknown_participants = set(event.get("participants", [])) - member_ids
        if unknown_participants:
            raise ValueError(f"Event {event['id']} has unknown participants: {unknown_participants}")
        for cause_id in event.get("caused_by", []):
            if cause_id not in event_dates:
                raise ValueError(f"Event {event['id']} caused_by references missing or future event: {cause_id}")
            if event_dates[cause_id] > event_date:
                raise ValueError(f"Event {event['id']} caused_by {cause_id} occurs after event date")
    return True


def generate_household_events(profile, num_events, num_days=60, start_date=None, use_llm=True, on_event_generated=None, dependent_scenarios=None):
    if start_date is None:
        start_date = get_random_date()
    end_date = start_date + timedelta(days=num_days)

    if not use_llm:
        logging.info("LLM disabled; generating household events with template fallback")
        return generate_template_household_events(profile, num_events, num_days, start_date, dependent_scenarios=dependent_scenarios)

    from global_methods import run_chatgpt

    graph = []
    scenario_sequence = build_event_scenario_sequence(profile, num_events, dependent_scenarios=dependent_scenarios)
    applicable_scenarios = [scenario for scenario in SCENARIOS if scenario_is_applicable(profile, scenario)]
    profile["events_start_date"] = dateObj2Str(start_date)
    profile["events_end_date"] = dateObj2Str(end_date)
    profile["event_generation_mode"] = "planned_single_event_llm"
    profile["dependent_scenarios"] = list(DEPENDENT_SCENARIOS if dependent_scenarios is None else dependent_scenarios)
    profile["event_scenario_catalog"] = {
        scenario: {
            "label": SCENARIO_LABELS[scenario],
            "memory_dimensions": SCENARIO_DIMENSIONS[scenario],
            "guidance": SCENARIO_GUIDANCE[scenario],
            "applicable": scenario in applicable_scenarios,
        }
        for scenario in SCENARIOS
    }
    profile["graph"] = []

    for idx, scenario_type in enumerate(scenario_sequence, start=1):
        event_plan = build_event_plan(profile, idx, scenario_type, start_date, num_days, num_events, graph)
        prompt_context = build_event_prompt_context(profile, event_plan, graph)
        prompt = HOUSEHOLD_SINGLE_EVENT_PROMPT.format(
            context=format_event_context_text(prompt_context),
            previous_events=compact_previous_events_for_prompt(prompt_context["previous_events"]),
            event_plan=json.dumps(compact_event_plan_for_prompt(event_plan), ensure_ascii=False, separators=(",", ":")),
        )
        logging.info(
            "Calling LLM for household event %s/%s: family_id=%s, scenario=%s, date=%s, caused_by=%s, prompt_chars=%s",
            idx,
            num_events,
            profile.get("family", {}).get("family_id"),
            scenario_type,
            event_plan["date"],
            event_plan["caused_by"],
            len(prompt),
        )
        try:
            response = run_chatgpt(prompt, num_gen=1, num_tokens_request=700, temperature=0.9)
            logging.info("LLM household event %s response received: chars=%s", event_plan["id"], len(response or ""))
            raw_event = parse_json_object(response)
            event = normalize_single_event(raw_event, event_plan, profile)
        except Exception as exc:
            logging.warning("LLM household event %s generation failed, using event fallback: %s", event_plan["id"], exc)
            event = normalize_single_event({}, event_plan, profile)

        graph.append(event)
        profile["graph"] = list(graph)
        logging.info(
            "Generated event %s [%s] date=%s participants=%s caused_by=%s",
            event["id"],
            event["scenario_type"],
            event["date"],
            event["participants"],
            event["caused_by"],
        )
        if on_event_generated:
            on_event_generated(profile, event)

    profile["events_start_date"] = dateObj2Str(start_date)
    profile["graph"] = graph
    profile["events_end_date"] = dateObj2Str(end_date)
    generated_scenarios = [event["scenario_type"] for event in graph]
    profile["event_scenario_coverage"] = {
        "generated": generated_scenarios,
        "covered": sorted(set(generated_scenarios)),
        "applicable": applicable_scenarios,
        "missing_applicable": [scenario for scenario in applicable_scenarios if scenario not in generated_scenarios],
        "dependent_scenarios": list(DEPENDENT_SCENARIOS if dependent_scenarios is None else dependent_scenarios),
    }
    validate_event_timeline(graph, profile)
    return graph


def sort_events_by_time(events):
    return sorted(events, key=lambda event: catch_date(event["date"]))


def get_household_session_date(events, num_events_per_session=2, prev_date=None):
    sorted_events = sort_events_by_time(events)
    eligible = []
    for event in sorted_events:
        event_date = catch_date(event["date"])
        if prev_date is None or event_date >= prev_date:
            eligible.append(event_date)
        if len(eligible) >= num_events_per_session:
            break
    if eligible:
        return eligible[-1] + timedelta(days=random.choice([1, 2]))
    if prev_date:
        return prev_date + timedelta(days=random.choice([3, 5, 7]))
    if sorted_events:
        return catch_date(sorted_events[0]["date"]) + timedelta(days=1)
    return get_random_date()


def get_relevant_household_events(events, curr_date, prev_date=None):
    selected = []
    for event in sort_events_by_time(events):
        event_date = catch_date(event["date"])
        if prev_date is not None:
            if prev_date <= event_date <= curr_date:
                selected.append(event)
        elif event_date <= curr_date:
            selected.append(event)
    return selected[-4:]
