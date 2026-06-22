"""
时间处理相关工具函数。

包括随机时间生成、日期转换、会话日期计算等功能。
"""

import random
import json
from datetime import date, timedelta, datetime

# 默认起始日期（用于生成随机日期和会话日期）
DEFAULT_START_DATE = date(2025, 1, 1)


def get_random_time(scenario_config=None):
    """
    生成一个随机的日内时间。
    
    根据场景配置中的时间范围生成随机时间，用于模拟会话发生时间。
    如果没有场景配置，默认在上午9点到晚上9:59之间生成。
    
    Args:
        scenario_config: 场景配置字典，包含 time_range 字段（可选）
        
    Returns:
        timedelta: 随机生成的时间差对象
    """
    # 默认时间范围：上午9点到晚上9:59
    start_hour, end_hour = 9, 21
    
    # 如果提供了场景配置，使用场景指定的时间范围
    if scenario_config and 'time_range' in scenario_config:
        time_range = scenario_config['time_range']
        start_hour = time_range.get('start_hour', 9)
        end_hour = time_range.get('end_hour', 21)
    
    # 处理跨天的时间范围（如异常检测场景：22:00-04:00）
    if start_hour > end_hour:
        # 随机选择前一天晚上或当天凌晨
        if random.choice([True, False]):
            # 前一天晚上
            start_time = timedelta(hours=start_hour, minutes=0, seconds=0)
            end_time = timedelta(hours=23, minutes=59, seconds=59)
        else:
            # 当天凌晨
            start_time = timedelta(hours=0, minutes=0, seconds=0)
            end_time = timedelta(hours=end_hour, minutes=59, seconds=59)
    else:
        start_time = timedelta(hours=start_hour, minutes=0, seconds=0)
        end_time = timedelta(hours=end_hour, minutes=59, seconds=59)
    
    random_seconds = random.randint(int(start_time.total_seconds()), int(end_time.total_seconds()))
    hours = random_seconds // 3600
    minutes = (random_seconds - (hours * 3600)) // 60
    return timedelta(hours=hours, minutes=minutes, seconds=0)


def datetimeStr2Obj(dateStr):
    """
    将日期时间字符串转换为datetime对象。
    
    支持带am/pm标记的12小时制时间格式。
    
    Args:
        dateStr: 日期时间字符串，格式如 "9:30 am on 5 January, 2023"
        
    Returns:
        datetime: 解析后的datetime对象
    """
    if 'am' in dateStr:
        datetimeObj = datetime.strptime(dateStr, "%H:%M am on %d %B, %Y")
    else:
        datetimeObj = datetime.strptime(dateStr, "%H:%M pm on %d %B, %Y")
    return datetimeObj


def datetimeObj2Str(datetimeObj):
    """
    将datetime对象转换为日期时间字符串。
    
    转换为12小时制格式，添加am/pm标记。
    
    Args:
        datetimeObj: datetime对象
        
    Returns:
        str: 格式化的时间字符串，格式如 "9:30 am on 5 January, 2023"
    """
    time_mod = 'am' if datetimeObj.hour <= 12 else 'pm'
    hour = datetimeObj.hour if datetimeObj.hour <= 12 else datetimeObj.hour-12
    min = str(datetimeObj.minute).zfill(2)
    return str(hour) + ':' + min + ' ' + time_mod + ' on ' + str(datetimeObj.day) + ' ' + datetimeObj.strftime("%B") + ', ' + str(datetimeObj.year)


def dateObj2Str(dateObj):
    """
    将date对象转换为日期字符串。
    
    Args:
        dateObj: date对象
        
    Returns:
        str: 格式化日期字符串，格式如 "5 January, 2023"
    """
    return dateObj.strftime("%d") + ' ' + dateObj.strftime("%B") + ', ' + dateObj.strftime("%Y")


def get_random_date():
    """
    在指定范围内生成随机日期。
    
    在2025年1月1日到2026年6月1日之间随机选择一个日期。
    
    Returns:
        date: 随机生成的日期对象
    """
    # initializing dates ranges
    test_date1, test_date2 = DEFAULT_START_DATE, date(2026, 6, 1)
    # getting days between dates
    dates_bet = test_date2 - test_date1
    total_days = dates_bet.days
    delta_days = random.choice(range(1, total_days))
    random_date = test_date1 + timedelta(days=int(delta_days))
    return random_date


def catch_date(date_str) -> datetime:
    """
    将日期字符串解析为datetime对象。
    
    支持两种日期格式：
    - '%d %B, %Y' (如 "10 January, 2023")
    - '%d %B %Y' (如 "10 January 2023")
    
    Args:
        date_str: 日期字符串，格式为 "DD Month, YYYY" 或 "DD Month YYYY"
        
    Returns:
        datetime: 解析后的datetime对象
        
    Raises:
        ValueError: 如果日期字符串格式不匹配任何支持的格式
    """
    date_format1 = '%d %B, %Y'
    date_format2 = '%d %B %Y'
    try:
        return datetime.strptime(date_str, date_format1)
    except:
        return datetime.strptime(date_str, date_format2)


def get_session_date(events, args, prev_date=None):
    """
    确定下一个会话的日期。
    
    基于事件时间线，计算包含指定数量事件的日期范围，
    返回该范围的结束日期作为会话日期。
    
    Args:
        events: (agent_a_events, agent_b_events) 两个角色的事件列表元组
        args: 包含num_events_per_session配置的命令行参数
        prev_date: 前一个会话的日期，用于确定时间顺序
        
    Returns:
        date: 会话日期，在事件范围结束后1-2天
    """
    from generative_agents.event_utils import sort_events_by_time
    
    agent_a_events, agent_b_events = events
    
    agent_a_events = sort_events_by_time(agent_a_events)
    curr_count = 0
    stop_count = args.num_events_per_session
    stop_date_a = None
    event_date = None  # 初始化 event_date
    
    # agent_a 是 AI助手，可能没有事件，需要特殊处理
    if len(agent_a_events) > 0:
        for e in agent_a_events:
            event_date = catch_date(e['date'])
            if prev_date:
                if event_date >= prev_date:
                    print("Including event %s for Agent A" % json.dumps(e, indent=2, ensure_ascii=False))
                    curr_count += 1
            else:
                print("Including event %s for Agent A" % json.dumps(e, indent=2, ensure_ascii=False))
                curr_count += 1
            if curr_count == stop_count:
                stop_date_a = event_date
                break
        # 循环结束后，确保 stop_date_a 有值
        if stop_date_a is None and event_date is not None:
            stop_date_a = event_date
    else:
        # 如果 agent_a 没有事件，使用 prev_date 或默认日期
        if prev_date:
            stop_date_a = prev_date
        else:
            stop_date_a = DEFAULT_START_DATE  # 默认起始日期

    # get date from agent_b
    agent_b_events = sort_events_by_time(agent_b_events)
    curr_count = 0
    stop_date_b = None
    event_date = None  # 初始化 event_date
    
    for e in agent_b_events:
        event_date = catch_date(e['date'])
        if prev_date:
            if event_date >= prev_date:
                print("Including event %s for Agent B" % json.dumps(e, indent=2, ensure_ascii=False))
                curr_count += 1
        else:
            print("Including event %s for Agent B" % json.dumps(e, indent=2, ensure_ascii=False))
            curr_count += 1
        if curr_count == stop_count:
            stop_date_b = event_date
            break
    
    # 确保 stop_date_b 有值
    if stop_date_b is None and event_date is not None:
        stop_date_b = event_date
    elif stop_date_b is None:
        # 如果 agent_b 也没有事件（不应该发生），使用 prev_date 或默认日期
        if prev_date:
            stop_date_b = prev_date
        else:
            stop_date_b = date(2022, 1, 1)

    # 确保 stop_date_a 和 stop_date_b 都有值（统一使用 datetime 类型）
    if stop_date_a is None:
        stop_date_a = datetime(2022, 1, 1)
    elif isinstance(stop_date_a, date) and not isinstance(stop_date_a, datetime):
        stop_date_a = datetime(stop_date_a.year, stop_date_a.month, stop_date_a.day)
    
    if stop_date_b is None:
        stop_date_b = datetime(2022, 1, 1)
    elif isinstance(stop_date_b, date) and not isinstance(stop_date_b, datetime):
        stop_date_b = datetime(stop_date_b.year, stop_date_b.month, stop_date_b.day)

    return min(stop_date_a, stop_date_b) + timedelta(days=random.choice([1, 2]))