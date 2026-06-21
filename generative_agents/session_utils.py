"""
会话生成相关工具函数。

包括会话摘要、事件处理、对话提示生成、会话生成等功能。
"""

import os
import json
import random
import pickle as pkl
from global_methods import run_chatgpt, run_chatgpt_with_examples
from generative_agents.conversation_utils import clean_dialog, CASUAL_DIALOG_PROMPT
from generative_agents.memory_utils import get_recent_context, get_relevant_context
from generative_agents.event_utils import sort_events_by_time
from generative_agents.time_utils import catch_date


# 用户对话提示模板（默认模板，当场景库中没有对应模板时使用）
USER_CONV_PROMPT_SESS_1 = """%s

你是 %s，一位在家中准备出门上班的用户。今天是 %s，现在是早上出门前。请扮演用户 %s 的角色，写下你对AI助手 %s 要说的下一句话。如果开始对话，可以从讨论今日工作安排、检查日程、提醒事项或家庭事务开始。不要重复之前已分享的信息。让对话围绕上班前的准备，例如谈论今日会议、待办事项、通勤安排或家庭琐事。包括时间参考，如"今天早上"、"上午会议"、"出门前"等。回复不超过20个字。

要结束对话，请写'再见！'。

对话：

"""

USER_CONV_PROMPT_SESS_1_W_EVENTS = """
使用给定的PERSONALITY写下对话中你要说的下一句话。
- 如果开始对话，请从讨论今日工作安排、检查日程、提醒事项或家庭事务开始。
- 不要重复之前对话中已分享的信息。
- 包括时间参考，如"今天早上"、"上午会议"、"出门前"等。
- 回复不超过20个字。
- 提出后续问题跟进之前的对话。

PERSONALITY: %s

你是用户 %s，在家中准备出门上班前与AI助手 %s 交谈。今天是 %s，现在是早上出门前。以下是你最近发生的事件。
事件：%s

请扮演用户 %s 的角色，与AI助手 %s 就这些事件进行对话，围绕上班前的准备。%s
"""

USER_CONV_PROMPT = """%s

你是用户 %s，上次与AI助手 %s 交谈是在 %s。%s

今天是 %s，现在是早上出门上班前。请扮演用户 %s 的角色，写下你对AI助手 %s 要说的下一句话。如果开始对话，可以从讨论今日工作安排、检查日程、提醒事项或家庭事务开始。不要重复已分享的信息。让对话围绕上班前的准备，例如谈论今日会议、待办事项、通勤安排或家庭琐事。包括时间参考，如"今天早上"、"上午会议"、"出门前"等。回复不超过20个字。

要结束对话，请写'再见！'。

对话：

"""

USER_CONV_PROMPT_W_EVENTS = """
使用给定的PERSONALITY写下对话中你要说的下一句话。
- 如果开始对话，请从讨论今日工作安排、检查日程、提醒事项或家庭事务开始。
- 不要重复之前对话中已分享的信息。
- 让对话围绕上班前的准备，例如谈论今日会议、待办事项、通勤安排或家庭琐事。
- 包括时间参考，如"今天早上"、"上午会议"、"出门前"等。
- 回复不超过20个字。
- 提出后续问题跟进之前的对话。

PERSONALITY: %s

你是用户 %s，上次与AI助手 %s 交谈是在 %s。

%s

今天是 %s，现在是早上出门上班前。以下是你最近发生的事件：
%s

在对话中使用这些事件。请根据你的PERSONALITY写下你在与AI助手 %s 的对话中要说的下一句话：
"""

USER_CONV_PROMPT_W_EVENTS_V2_INIT = """
使用给定的PERSONALITY写下对话中你要说的下一句话。
- 回复不超过20个字。
- 让对话围绕上班前的准备，例如讨论今日会议、待办事项、通勤安排或家庭琐事。详细讨论重要的事件。
- 不要重复之前对话中已分享的信息。
- 包括时间参考，如"今天早上"、"上午会议"、"出门前"等。
- 有时，提出后续问题跟进之前的对话或当前话题。
- 不要谈论户外活动。

PERSONALITY: %s


你是用户 %s，上次与AI助手 %s 交谈是在 %s。今天是 %s，现在是早上出门上班前。

这是到目前为止的对话摘要。
摘要：
%s

以下是你最近发生的事件：
事件：
%s


请扮演用户 %s，写下你在与AI助手 %s 的对话中要说的下一句深思熟虑的话。在对话中只讨论给定的事件及其对你上班前准备的影响。如果事件有负面影响，请表达担忧。
"""

USER_CONV_PROMPT_W_EVENTS_V2 = """
使用给定的PERSONALITY写下对话中你要说的下一句话。
- 回复不超过20个字。
- 让对话围绕上班前的准备，例如讨论今日会议、待办事项、通勤安排或家庭琐事。详细讨论重要的事件。
- 不要重复之前对话中已分享的信息。
- 包括时间参考，如"今天早上"、"上午会议"、"出门前"等。
- 有时，提出后续问题跟进之前的对话或当前话题。
- 不要谈论户外活动。

PERSONALITY: %s

你是用户 %s，上次与AI助手 %s 交谈是在 %s。今天是 %s，现在是早上出门上班前。

这是到目前为止的对话摘要。
摘要：
%s

以下是你最近发生的事件：
事件：
%s

以下是双方都知道的信息。
相关上下文：
%s

请扮演用户 %s，写下你在与AI助手 %s 的对话中要说的下一句深思熟虑的话，围绕上班前的准备。在对话中只讨论给定的事件及其对你上班前准备的影响。如果事件有负面影响，请表达担忧。
"""


def get_session_summary(session, speaker_1, speaker_2, curr_date, previous_summary=""):
    """
    生成单个会话的摘要。
    
    分析会话对话内容，生成简洁的摘要，包含关键事实和时间参考。
    可基于前一个会话的摘要进行增量总结。
    
    Args:
        session: 会话对话列表，每个元素包含speaker和text字段
        speaker_1: 第一个说话人对象
        speaker_2: 第二个说话人对象
        curr_date: 当前会话日期
        previous_summary: 前一个会话的摘要，可选
        
    Returns:
        str: 会话摘要字符串
    """
    from generative_agents.conversation_utils import SESSION_SUMMARY_PROMPT, SESSION_SUMMARY_INIT_PROMPT
    
    session_query = ''
    for c in session:
        session_query += "%s: %s\n" % (c["speaker"], c["text"])
        if "image" in c:
            session_query += "[%s shares %s]\n" % (c["speaker"], c["image"])

    if previous_summary:
        query = SESSION_SUMMARY_PROMPT % (speaker_1['name'], speaker_2['name'], previous_summary, curr_date,
                                               speaker_1['name'], speaker_2['name'], session_query, speaker_1['name'], speaker_2['name'])
    else:
        query = SESSION_SUMMARY_INIT_PROMPT % (speaker_1['name'], speaker_2['name'], curr_date, session_query)

    query += '\n\n'
    output = run_chatgpt(query, 1, 150, 'chatgpt')
    output = output.strip()
    return output


def get_all_session_summary(speaker, curr_sess_id):
    """
    获取指定说话人的所有历史会话摘要。
    
    从第一个会话到当前会话之前的所有会话摘要汇总。
    
    Args:
        speaker: 说话人对象，包含各会话的摘要数据
        curr_sess_id: 当前会话ID
        
    Returns:
        str: 包含日期和摘要的汇总字符串
    """
    summary = "\n"
    for sess_id in range(1, curr_sess_id):
        sess_date = speaker['session_%s_date_time' % sess_id]
        sess_date = sess_date[2] + ' ' + sess_date[1] + ', ' + sess_date[0]
        summary += sess_date + ': ' + speaker["session_%s_summary" % sess_id] + '\n'
    return summary


def get_relevant_events(events, curr_date, prev_date=None):
    """
    获取在指定时间范围内发生的相关事件。
    
    过滤出发生在prev_date之后、curr_date之前的事件，
    用于在会话生成时提供上下文事件。
    
    Args:
        events: 事件列表
        curr_date: 当前会话日期
        prev_date: 前一个会话日期，可选
        
    Returns:
        list: 在时间范围内的事件列表
    """
    events = sort_events_by_time(events)
    relevant_events = []
    for e in events:
        event_date = catch_date(e['date'])
        if event_date > curr_date:
            continue
        if prev_date:
            if event_date <= prev_date:
                continue
        relevant_events.append(e)

    return relevant_events


def get_event_string(session_events, all_events):
    """
    将事件列表转换为可读的文本描述。
    
    将事件转换为包含日期的自然语言描述，如果事件有因果关联，
    还会包含原因事件的描述。
    
    Args:
        session_events: 当前会话相关的事件列表
        all_events: 所有事件的字典，用于查找因果关联
        
    Returns:
        str: 格式化的事件描述文本
    """
    id2events = {e['id']: e for e in all_events}

    event_string = ""
    for e in session_events:
        try:
            event_text = 'On' + e["date"] + ", " + e["sub-event"]
        except KeyError:
            event_text = 'On' + e["date"] + ", " + e["sub_event"]

        # if the event is caused by previous events, include them for context
        if len(e['caused_by']) > 0:
            event_text += ' Because previously'
            for e_id in e['caused_by']:
                try:
                    event_text += ', ' + id2events[e_id]["sub-event"] + ' (%s)' % id2events[e_id]["date"]
                except KeyError:
                    event_text += ', ' + id2events[e_id]["sub_event"] + ' (%s)' % id2events[e_id]["date"]
        
        event_string += event_text + "\n"

    return event_string


def remove_context(args, curr_dialog, prev_dialog, caption=None):
    """
    从当前对话中移除与历史对话重复的内容。
    
    使用ChatGPT分析当前对话和历史对话，过滤掉重复的信息，
    只保留新的独特内容，避免对话中重复已分享的信息。
    
    Args:
        args: 包含prompt_dir配置的命令行参数
        curr_dialog: 当前对话内容
        prev_dialog: 历史对话内容
        caption: 图像描述，可选
        
    Returns:
        str: 去除重复内容后的对话字符串
    """
    prompt_data = json.load(open(os.path.join(args.prompt_dir, 'remove_context_examples.json')))
    if caption:
        query = prompt_data["input_format_w_image"].format(prev_dialog, curr_dialog, caption)
    else:
        query = prompt_data["input_format"].format(prev_dialog, curr_dialog)
    output = run_chatgpt_with_examples(prompt_data["prompt"], 
                              [[prompt_data["input_format"].format(*example["input"]) if len(example["input"]) == 2 else prompt_data["input_format_w_image"].format(*example["input"]), example["output"]] for example in prompt_data['examples']], 
                              query, num_gen=1, num_tokens_request=128, use_16k=False)
    return output


def get_agent_query(speaker_1, speaker_2, curr_sess_id=0, 
                    prev_sess_date_time='', curr_sess_date_time='', 
                    use_events=False, instruct_stop=False, dialog_id=0, last_dialog='', embeddings=None, reflection=False,
                    scenario_id='male_leave_work', scenario_file='./data/scenarios/scenarios.json'):
    """
    为AI助手角色生成对话提示。
    
    根据当前会话状态、历史上下文和相关事件，生成用于指导AI助手
    下一轮对话的完整提示。支持从场景库动态获取prompt模板。
    
    Args:
        speaker_1: AI助手角色对象
        speaker_2: 用户角色对象
        curr_sess_id: 当前会话ID，首个会话为1
        prev_sess_date_time: 前一会话的时间日期字符串
        curr_sess_date_time: 当前会话的时间日期字符串
        use_events: 是否在提示中包含事件信息
        instruct_stop: 是否在提示中包含停止指令
        dialog_id: 当前会话中的对话轮次ID
        last_dialog: 上一轮对话内容，用于检索相关上下文
        embeddings: 嵌入向量，用于细粒度检索
        reflection: 是否包含反思信息
        scenario_id: 场景ID，默认为 'male_leave_work'
        scenario_file: 场景配置文件路径
        
    Returns:
        str: 格式化的对话提示字符串
    """
    from generative_agents.conversation_utils import load_scenario_config, get_scenario_prompt, AGENT_CONV_PROMPT_SESS_1, AGENT_CONV_PROMPT_SESS_1_W_EVENTS, AGENT_CONV_PROMPT_W_EVENTS_V2_INIT, AGENT_CONV_PROMPT_W_EVENTS_V2, AGENT_CONV_PROMPT
    
    stop_instruction = "To end the conversation, write [END] at the end of the dialog."
    if instruct_stop:
        print("**** Using stop instruction ****")

    # speaker_1 is always the AI assistant, speaker_2 is always the user
    assistant_name = speaker_1['name']
    user_name = speaker_2['name']
    user_persona = speaker_2['persona_summary']

    # 加载场景配置
    load_scenario_config(scenario_file)

    if curr_sess_id == 1:
        
        if use_events:
            events = get_event_string(speaker_2['events_session_%s' % curr_sess_id], speaker_2['graph'])
            # 尝试从场景库获取prompt
            prompt_template = get_scenario_prompt(scenario_id, 'sess_1_w_events', 'agent')
            if prompt_template:
                query = prompt_template % (speaker_1['persona_summary'],
                        user_name, assistant_name, 
                        curr_sess_date_time, user_name,  events, assistant_name, user_name, stop_instruction if instruct_stop else '')
            else:
                # 使用默认模板
                query = AGENT_CONV_PROMPT_SESS_1_W_EVENTS % (speaker_1['persona_summary'],
                        user_name, assistant_name, 
                        curr_sess_date_time, user_name,  events, assistant_name, user_name, stop_instruction if instruct_stop else '')
        else:
            # 尝试从场景库获取prompt
            prompt_template = get_scenario_prompt(scenario_id, 'sess_1', 'agent')
            if prompt_template:
                query = prompt_template % (speaker_1['persona_summary'],
                                user_name, assistant_name, 
                                curr_sess_date_time, assistant_name,  user_name, assistant_name)
            else:
                # 使用默认模板
                query = AGENT_CONV_PROMPT_SESS_1 % (speaker_1['persona_summary'],
                                user_name, assistant_name, 
                                curr_sess_date_time, assistant_name,  user_name, assistant_name)
    
    else:
        if use_events:
            events = get_event_string(speaker_2['events_session_%s' % curr_sess_id], speaker_2['graph'])
            if dialog_id == 0:
                # if a new session is starting, get information about the topics discussed in last session
                context_from_1, context_from_2 = get_recent_context(speaker_2, speaker_1, curr_sess_id, reflection=reflection)
                recent_context = '\n'.join(context_from_1) + '\n' +  '\n'.join(context_from_2) # with reflection
                # 尝试从场景库获取prompt
                prompt_template = get_scenario_prompt(scenario_id, 'sess_w_events_v2_init', 'agent')
                if prompt_template:
                    query = prompt_template % (speaker_1['persona_summary'],
                                user_name, assistant_name, prev_sess_date_time,
                                curr_sess_date_time, assistant_name,  speaker_2['session_%s_summary' % (curr_sess_id-1)], events, assistant_name, user_name)
                else:
                    query = AGENT_CONV_PROMPT_W_EVENTS_V2_INIT % (speaker_1['persona_summary'],
                                user_name, assistant_name, prev_sess_date_time,
                                curr_sess_date_time, assistant_name,  speaker_2['session_%s_summary' % (curr_sess_id-1)], events, assistant_name, user_name)
                
            else:
                # during an ongoing session, get fine-grained information from a previous session using retriever modules
                past_context = get_relevant_context(speaker_2, speaker_1, last_dialog, embeddings, curr_sess_id, reflection=reflection)
                # 尝试从场景库获取prompt
                prompt_template = get_scenario_prompt(scenario_id, 'sess_w_events_v2', 'agent')
                if prompt_template:
                    query = prompt_template % (speaker_1['persona_summary'],
                                user_name, assistant_name, prev_sess_date_time,
                                curr_sess_date_time, assistant_name, speaker_2['session_%s_summary' % (curr_sess_id-1)], events, past_context, assistant_name, user_name)
                else:
                    query = AGENT_CONV_PROMPT_W_EVENTS_V2 % (speaker_1['persona_summary'],
                                user_name, assistant_name, prev_sess_date_time,
                                curr_sess_date_time, assistant_name, speaker_2['session_%s_summary' % (curr_sess_id-1)], events, past_context, assistant_name, user_name)
        else:
            summary = get_all_session_summary(speaker_2, curr_sess_id)
            # 尝试从场景库获取prompt
            prompt_template = get_scenario_prompt(scenario_id, 'sess_continue', 'agent')
            if prompt_template:
                query = prompt_template % (speaker_1['persona_summary'],
                                            user_name, assistant_name, prev_sess_date_time, summary,
                                            curr_sess_date_time, assistant_name,  user_name, assistant_name)
            else:
                query = AGENT_CONV_PROMPT % (speaker_1['persona_summary'],
                                            user_name, assistant_name, prev_sess_date_time, summary,
                                            curr_sess_date_time, assistant_name,  user_name, assistant_name) 
    
    return query


def get_user_query(user, assistant, curr_sess_id=0, 
                    prev_sess_date_time='', curr_sess_date_time='', 
                    use_events=False, instruct_stop=False, dialog_id=0, last_dialog='', embeddings=None, reflection=False,
                    scenario_id='male_leave_work', scenario_file='./data/scenarios/scenarios.json'):
    """
    为用户角色生成对话提示。
    
    根据当前会话状态、历史上下文和相关事件，生成用于指导用户角色
    下一轮对话的完整提示。支持从场景库动态获取prompt模板。
    
    Args:
        user: 用户角色对象
        assistant: AI助手角色对象
        curr_sess_id: 当前会话ID，首个会话为1
        prev_sess_date_time: 前一会话的时间日期字符串
        curr_sess_date_time: 当前会话的时间日期字符串
        use_events: 是否在提示中包含事件信息
        instruct_stop: 是否在提示中包含停止指令
        dialog_id: 当前会话中的对话轮次ID
        last_dialog: 上一轮对话内容，用于检索相关上下文
        embeddings: 嵌入向量，用于细粒度检索
        reflection: 是否包含反思信息
        scenario_id: 场景ID，默认为 'male_leave_work'
        scenario_file: 场景配置文件路径
        
    Returns:
        str: 格式化的对话提示字符串
    """
    from generative_agents.conversation_utils import load_scenario_config, get_scenario_prompt
    
    stop_instruction = "To end the conversation, write [END] at the end of the dialog."
    if instruct_stop:
        print("**** Using stop instruction ****")

    user_name = user['name']
    assistant_name = assistant['name']
    user_persona = user['persona_summary']

    # 加载场景配置
    load_scenario_config(scenario_file)

    if curr_sess_id == 1:
        
        if use_events:
            events = get_event_string(user['events_session_%s' % curr_sess_id], user['graph'])
            # 尝试从场景库获取prompt
            prompt_template = get_scenario_prompt(scenario_id, 'sess_1_w_events', 'user')
            if prompt_template:
                query = prompt_template % (user_persona,
                        user_name, assistant_name, 
                        curr_sess_date_time, events, user_name, assistant_name, stop_instruction if instruct_stop else '')
            else:
                query = USER_CONV_PROMPT_SESS_1_W_EVENTS % (user_persona,
                        user_name, assistant_name, 
                        curr_sess_date_time, events, user_name, assistant_name, stop_instruction if instruct_stop else '')
        else:
            # 尝试从场景库获取prompt
            prompt_template = get_scenario_prompt(scenario_id, 'sess_1', 'user')
            if prompt_template:
                query = prompt_template % (user_persona,
                                user_name, curr_sess_date_time, user_name, assistant_name)
            else:
                query = USER_CONV_PROMPT_SESS_1 % (user_persona,
                                user_name, curr_sess_date_time, user_name, assistant_name)
    
    else:
        if use_events:
            events = get_event_string(user['events_session_%s' % curr_sess_id], user['graph'])
            if dialog_id == 0:
                # if a new session is starting, get information about the topics discussed in last session
                context_from_1, context_from_2 = get_recent_context(user, assistant, curr_sess_id, reflection=reflection)
                recent_context = '\n'.join(context_from_1) + '\n' +  '\n'.join(context_from_2) # with reflection
                # 尝试从场景库获取prompt (user模板目前没有sess_w_events_v2_init，使用默认)
                query = USER_CONV_PROMPT_W_EVENTS_V2_INIT % (user_persona,
                            user_name, assistant_name, prev_sess_date_time,
                            curr_sess_date_time, user['session_%s_summary' % (curr_sess_id-1)], events, user_name, assistant_name)
                
            else:
                # during an ongoing session, get fine-grained information from a previous session using retriever modules
                past_context = get_relevant_context(user, assistant, last_dialog, embeddings, curr_sess_id, reflection=reflection)
                # 尝试从场景库获取prompt (user模板目前没有sess_w_events_v2，使用默认)
                query = USER_CONV_PROMPT_W_EVENTS_V2 % (user_persona,
                            user_name, assistant_name, prev_sess_date_time,
                            curr_sess_date_time, user['session_%s_summary' % (curr_sess_id-1)], events, past_context, user_name, assistant_name)
        else:
            summary = get_all_session_summary(user, curr_sess_id)
            # 尝试从场景库获取prompt
            prompt_template = get_scenario_prompt(scenario_id, 'sess_continue', 'user')
            if prompt_template:
                query = prompt_template % (user_persona,
                                            user_name, assistant_name, prev_sess_date_time, summary,
                                            curr_sess_date_time, user_name,  assistant_name)
            else:
                query = USER_CONV_PROMPT % (user_persona,
                                            user_name, assistant_name, prev_sess_date_time, summary,
                                            curr_sess_date_time, user_name,  assistant_name) 
    
    return query


def get_session(agent_a, agent_b, args, prev_date_time_string='', curr_date_time_string='', curr_sess_id=0, reflection=False):
    """
    生成单个会话的完整对话内容
    
    该函数负责模拟AI助手与用户之间的一轮完整对话，通过交替调用get_agent_query和get_user_query
    构建Prompt，调用LLM生成回复，并进行口语化转换和格式清洗。
    
    Args:
        agent_a (dict): AI助手角色信息，包含persona、name、graph等字段
        agent_b (dict): 用户角色信息，包含persona、name、graph等字段
        args (argparse.Namespace): 命令行参数，包含max_turns_per_session、events、emb_file、scenario、scenario_file等配置
        prev_date_time_string (str, optional): 上一个会话的日期时间字符串，用于上下文关联
        curr_date_time_string (str, optional): 当前会话的日期时间字符串
        curr_sess_id (int, optional): 当前会话ID，从1开始递增
        reflection (bool, optional): 是否启用反思机制，默认为False
    
    Returns:
        list: 会话对话列表，每个元素是一个字典，包含text、raw_text、speaker、clean_text、dia_id字段
    
    Notes:
        - agent_a固定为AI助手角色，agent_b固定为用户角色
        - 用户默认先发起对话（curr_speaker初始值为1）
        - 对话终止条件：达到最大轮次 或 双方都发送了[END]标记
        - 场景参数从args中获取：args.scenario 和 args.scenario_file
    """
    
    # 角色分配：agent_a = AI助手，agent_b = 用户
    assistant = agent_a
    user = agent_b
    
    # 获取场景参数
    scenario_id = getattr(args, 'scenario', 'male_leave_work')
    scenario_file = getattr(args, 'scenario_file', './data/scenarios/scenarios.json')
    
    # 加载历史对话嵌入向量，用于细粒度上下文检索（仅非首次会话且文件存在时需要）
    if curr_sess_id == 1:
        embeddings = None  # 第一轮会话无历史，无需加载
    elif os.path.exists(args.emb_file):
        embeddings = pkl.load(open(args.emb_file, 'rb'))
    else:
        embeddings = None  # 嵌入文件不存在时设为 None

    # 初始化对话状态：用户先发言（1=用户，0=助手）
    curr_speaker = 1
    conv_so_far = user['name'] + ': '  # 构建对话历史前缀

    session = []  # 存储完整会话内容
    
    # 随机选择对话终止指令插入位置（10轮之后），用于引导会话自然结束
    stop_dialog_count = args.max_turns_per_session if args.max_turns_per_session <= 10 else random.choice(list(range(10, args.max_turns_per_session)))
    break_at_next_assistant = False  # 标记助手是否需要结束
    break_at_next_user = False       # 标记用户是否需要结束
    
    # 循环生成对话轮次
    for i in range(args.max_turns_per_session):
        # 终止条件：双方都发送了[END]标记
        if break_at_next_assistant and break_at_next_user:
            break

        # 根据当前发言者选择对应的Prompt生成函数
        if curr_speaker == 0:
            # AI助手发言：使用get_agent_query构建Prompt
            agent_query = get_agent_query(
                speaker_1=assistant,
                speaker_2=user,
                prev_sess_date_time=prev_date_time_string,
                curr_sess_date_time=curr_date_time_string,
                curr_sess_id=curr_sess_id,
                use_events=args.events,
                instruct_stop=i >= stop_dialog_count,  # 是否插入终止指令
                dialog_id=i,
                last_dialog='' if i == 0 else session[-1]['speaker'] + ' says, ' + session[-1]['clean_text'],
                embeddings=embeddings,
                reflection=reflection,
                scenario_id=scenario_id,
                scenario_file=scenario_file
            )
            speaker_name = assistant['name']
        else:
            # 用户发言：使用get_user_query构建Prompt
            agent_query = get_user_query(
                user=user,
                assistant=assistant,
                prev_sess_date_time=prev_date_time_string,
                curr_sess_date_time=curr_date_time_string,
                curr_sess_id=curr_sess_id,
                use_events=args.events,
                instruct_stop=i >= stop_dialog_count,
                dialog_id=i,
                last_dialog='' if i == 0 else session[-1]['speaker'] + ' says, ' + session[-1]['clean_text'],
                embeddings=embeddings,
                reflection=reflection,
                scenario_id=scenario_id,
                scenario_file=scenario_file
            )
            speaker_name = user['name']
        
        # 调用LLM生成回复
        output = run_chatgpt(agent_query + conv_so_far, 1, 100, 'chatgpt', temperature=1.2)
        output = output.strip().split('\n')[0]  # 取第一行作为回复
        output = clean_dialog(output, speaker_name)  # 清洗对话内容
        output = {"text": output, "raw_text": output}

        output["speaker"] = speaker_name
        text_replaced_caption = output["text"]
        
        # 处理回复内容：非空且未结束标记时进行口语化转换
        if not text_replaced_caption.isspace():
            if '[END]' in output["text"]:
                output["clean_text"] = text_replaced_caption  # 结束标记保留原样
            else:
                # 通过CASUAL_DIALOG_PROMPT将正式表达转为日常口语
                output["clean_text"] = run_chatgpt(CASUAL_DIALOG_PROMPT % text_replaced_caption, 1, 100, 'chatgpt').strip()
        else:
            output["clean_text"] = ""  # 空内容处理
        
        # 添加对话ID标识（格式：D{会话ID}:{轮次}）
        output["dia_id"] = 'D%s:%s' % (curr_sess_id, i+1)
        session.append(output)

        print("############ ", speaker_name, ': ', output["clean_text"])
        
        # 更新对话历史
        conv_so_far = conv_so_far + output["clean_text"] + '\n'

        # 检测结束标记：当一方发送[END]后，等待另一方也发送[END]
        if output['text'].endswith('[END]'):
            if curr_speaker == 0:
                break_at_next_assistant = True
            else:
                break_at_next_user = True

        # 准备下一轮对话历史前缀并切换发言者
        conv_so_far += f"\n{user['name']}: " if curr_speaker == 0 else f"\n{assistant['name']}: "
        curr_speaker = int(not curr_speaker)  # 切换发言者（0↔1）

    return session