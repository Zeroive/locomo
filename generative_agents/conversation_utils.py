import json, re, os, logging
import random
import secrets
from global_methods import run_chatgpt, run_chatgpt_with_examples

# 全局场景配置缓存
SCENARIO_CONFIG = None

def load_scenario_config(scenario_file='./data/scenarios/scenarios.json'):
    """
    加载场景配置文件。
    
    Args:
        scenario_file: 场景配置文件路径
        
    Returns:
        dict: 场景配置字典
    """
    global SCENARIO_CONFIG
    if SCENARIO_CONFIG is None:
        try:
            SCENARIO_CONFIG = json.load(open(scenario_file, encoding='utf-8'))
            logging.info(f"Loaded scenario config from {scenario_file}")
        except FileNotFoundError:
            logging.warning(f"Scenario file not found: {scenario_file}, using default prompts")
            SCENARIO_CONFIG = None
    return SCENARIO_CONFIG

def get_scenario_prompt(scenario_id, prompt_type, role='agent'):
    """
    根据场景ID和prompt类型获取对应的prompt模板。
    
    Args:
        scenario_id: 场景ID，如 'male_leave_work'
        prompt_type: prompt类型，如 'sess_1', 'sess_1_w_events', 'sess_continue', 'sess_w_events_v2_init', 'sess_w_events_v2'
        role: 角色，'agent' 或 'user'
        
    Returns:
        str: prompt模板字符串，如果场景不存在则返回默认模板
    """
    config = load_scenario_config()
    if config is None or scenario_id not in config['scenarios']:
        # 返回默认模板
        return get_default_prompt(prompt_type, role)
    
    scenario = config['scenarios'][scenario_id]
    template_key = 'agent_prompt_template' if role == 'agent' else 'user_prompt_template'
    
    try:
        return scenario[template_key][prompt_type]
    except KeyError:
        logging.warning(f"Prompt type {prompt_type} not found for scenario {scenario_id}, using default")
        return get_default_prompt(prompt_type, role)

def get_default_prompt(prompt_type, role='agent'):
    """
    获取默认的prompt模板（用于场景配置不存在时的fallback）。
    
    注意：此函数返回None，实际默认模板在generate_conversations.py中定义。
    
    Args:
        prompt_type: prompt类型
        role: 角色
        
    Returns:
        str: 返回None，让调用者使用内置默认模板
    """
    # 返回None，让调用者使用内置的默认模板
    return None

PERSONA_FROM_MSC_PROMPT = """
根据给定的生活属性描述和场景信息来编写人物角色描述。示例：
%s

注意：请在人物描述中添加关键细节，如姓名、年龄、婚姻状况、性别、职业等。在适当情况下添加额外细节，如家人/朋友的名字、特定活动、爱好和厌恶、经历等。人物描述应与场景相符，考虑该人物在特定场景下的行为和需求。

根据以下属性，编写一个人物描述。输出一个包含'persona'和'name'键的JSON文件。

场景：用户在家中与AI助手互动的日常场景，包括早晨出门、下班回家、周末休息等家庭生活场景。

%s
输出格式示例：
{
  "persona": "人物描述",
  "name": "姓名"
}
请以花括号开始回答。
"""

PERSONA_FROM_MSC_PROMPT_WITH_SCENARIO = """
根据给定的生活属性描述和特定场景信息来编写人物角色描述。示例：
%s

注意：请在人物描述中添加关键细节，如姓名、年龄、婚姻状况、性别、职业等。在适当情况下添加额外细节，如家人/朋友的名字、特定活动、爱好和厌恶、经历等。

## 当前场景信息
场景名称：%s
场景描述：%s
时间上下文：%s

人物描述必须与上述场景高度相关，考虑该人物在特定场景下的身份、行为和需求。例如：
- 如果是"男主人上班离家"场景，人物应该是家庭中的男性成员，年龄适中，有工作
- 如果是"老人独自外出"场景，人物应该是老年人，需要关注健康和安全
- 如果是"小孩放学回家"场景，人物应该是学生，年龄较小

根据以下属性，编写一个与场景相符的人物描述。输出一个包含'persona'和'name'键的JSON文件。

%s
输出格式示例：
{
  "persona": "人物描述",
  "name": "姓名"
}
请以花括号开始回答。
"""


# 默认prompt模板（保留作为fallback）
AGENT_CONV_PROMPT_SESS_1 = """%s

%s 在家中，准备出门上班前与AI助手 %s 交谈。今天是 %s，现在是早上出门前。请扮演AI助手 %s 的角色，根据用户的情况和对话历史，写下你对用户 %s 要说的下一句话。如果开始对话，可以从问候开始，然后询问用户今日工作安排、检查日程、提醒事项或家庭事务。不要重复之前已分享的信息。让对话围绕上班前的准备，例如谈论今日会议、待办事项、通勤安排或家庭琐事。包括时间参考，如"今天早上"、"上午会议"、"出门前"等。回复不超过20个字。

要结束对话，请写'再见！'。

对话：

"""

AGENT_CONV_PROMPT_SESS_1_W_EVENTS = """
使用给定的PERSONALITY写下对话中你要说的下一句话。
- 如果开始对话，请从问候开始，然后询问用户今日工作安排、检查日程、提醒事项或家庭事务。
- 不要重复之前对话中已分享的信息。
- 包括时间参考，如"今天早上"、"上午会议"、"出门前"等。
- 回复不超过20个字。
- 提出后续问题跟进之前的对话。

PERSONALITY: %s

用户 %s 在家中，准备出门上班前与AI助手 %s 交谈。今天是 %s，现在是早上出门前。以下是用户 %s 最近发生的事件。
事件：%s

请扮演AI助手 %s 的角色，与用户 %s 就这些事件进行对话，围绕上班前的准备。%s
"""


AGENT_CONV_PROMPT = """%s

用户 %s 上次与AI助手 %s 交谈是在 %s。%s

今天是 %s，现在是早上出门上班前。请扮演AI助手 %s 的角色，写下你对用户 %s 要说的下一句话。如果开始对话，请从问候开始，然后询问用户今日工作安排、检查日程、提醒事项或家庭事务。不要重复已分享的信息。让对话围绕上班前的准备，例如谈论今日会议、待办事项、通勤安排或家庭琐事。包括时间参考，如"今天早上"、"上午会议"、"出门前"等。回复不超过20个字。

要结束对话，请写'再见！'。

对话：

"""


AGENT_CONV_PROMPT_W_EVENTS = """
使用给定的PERSONALITY写下对话中你要说的下一句话。
- 如果开始对话，请从问候开始，然后询问用户今日工作安排、检查日程、提醒事项或家庭事务。
- 不要重复之前对话中已分享的信息。
- 让对话围绕上班前的准备，例如谈论今日会议、待办事项、通勤安排或家庭琐事。
- 包括时间参考，如"今天早上"、"上午会议"、"出门前"等。
- 回复不超过20个字。
- 提出后续问题跟进之前的对话。

PERSONALITY: %s

用户 %s 上次与AI助手 %s 交谈是在 %s。

%s

今天是 %s，现在是早上出门上班前。你是AI助手 %s。以下是用户最近发生的事件：
%s

在对话中使用这些事件。请根据你的PERSONALITY写下你在与用户 %s 的对话中要说的下一句话：
"""


AGENT_CONV_PROMPT_W_EVENTS_V2_INIT = """
使用给定的PERSONALITY写下对话中你要说的下一句话。
- 回复不超过20个字。
- 让对话围绕上班前的准备，例如讨论今日会议、待办事项、通勤安排或家庭琐事。详细讨论重要的事件。
- 不要重复之前对话中已分享的信息。
- 包括时间参考，如"今天早上"、"上午会议"、"出门前"等。
- 有时，提出后续问题跟进之前的对话或当前话题。
- 不要谈论户外活动。

PERSONALITY: %s


用户 %s 上次与AI助手 %s 交谈是在 %s。今天是 %s，现在是早上出门上班前。你是AI助手 %s。

这是到目前为止的对话摘要。
摘要：
%s

以下是用户最近发生的事件：
事件：
%s


请扮演AI助手 %s，写下你在与用户 %s 的对话中要说的下一句深思熟虑的话。在对话中只讨论给定的事件及其对用户上班前准备的影响。如果事件有负面影响，请表达关心和建议。
"""


AGENT_CONV_PROMPT_W_EVENTS_V2 = """
使用给定的PERSONALITY写下对话中你要说的下一句话。
- 回复不超过20个字。
- 让对话围绕上班前的准备，例如讨论今日会议、待办事项、通勤安排或家庭琐事。详细讨论重要的事件。
- 不要重复之前对话中已分享的信息。
- 包括时间参考，如"今天早上"、"上午会议"、"出门前"等。
- 有时，提出后续问题跟进之前的对话或当前话题。
- 不要谈论户外活动。

PERSONALITY: %s

用户 %s 上次与AI助手 %s 交谈是在 %s。今天是 %s，现在是早上出门上班前。你是AI助手 %s。

这是到目前为止的对话摘要。
摘要：
%s

以下是用户最近发生的事件：
事件：
%s

以下是双方都知道的信息。
相关上下文：
%s

请扮演AI助手 %s，写下你在与用户 %s 的对话中要说的下一句深思熟虑的话，围绕上班前的准备。在对话中只讨论给定的事件及其对用户上班前准备的影响。如果事件有负面影响，请表达关心和建议。
"""


CASUAL_DIALOG_PROMPT = "将句子改得更短、更随意、更口语化。\n\n输入：%s\n输出："


SESSION_SUMMARY_PROMPT = "%s 和 %s 到目前为止的对话可以总结如下：%s。当前时间和日期是 %s。%s 和 %s 刚刚进行了以下对话：\n\n%s\n\n请用150字或更少的字数总结 %s 和 %s 之间之前和当前的对话。包括关于两位说话者的关键事实和时间参考。\n\n"


SESSION_SUMMARY_INIT_PROMPT = "请写一个简洁的摘要，包含在 %s 的对话中提到的关于 %s 和 %s 的关键事实：\n\n%s\n\n"


def get_msc_persona(args, scenario_info=None):
    """
    从MSC数据集中获取人物角色信息。
    
    检查已存在的角色文件，如果不存在或需要覆盖，则从单角色数据集
    msc_speakers_single.json 中随机选择一个人物角色作为用户，AI助手使用默认角色。
    
    Args:
        args: 包含文件路径和覆盖标志的命令行参数
        scenario_info: 场景信息字典，包含场景名称、描述和时间上下文等
    
    Returns:
        tuple: (agent_a, agent_b) 两个角色对象的元组，agent_a为AI助手，agent_b为用户，如果文件已存在则返回(None, None)
    """
    # 检查角色文件是否存在，如果存在且不覆盖则直接返回
    if (os.path.exists(args.agent_a_file) and os.path.exists(args.agent_b_file)) and not args.overwrite_persona:
        return None, None
    else:
        # agent_a: 默认AI助手角色 - 家庭智能助手
        agent_a = {
            'name': 'AI助手',
            'persona_summary': '你是一个友好、专业的家庭智能助手，负责管理和控制家中的智能设备。你可以操作智能灯、空调、窗帘、门锁、摄像头、温湿度传感器等设备，帮助用户实现家居自动化和安全监控。你善于倾听用户需求，提供贴心的生活建议，并能根据场景自动触发设备联动。',
            'msc_prompt': ['I am a smart home AI assistant.', 'I can control smart home devices like lights, air conditioners, curtains, and locks.', 'I monitor home security and environmental conditions.', 'I am helpful and friendly, always ready to assist with household tasks.']
        }
        
        # agent_b: 从单角色数据集中随机选择一个用户角色
        all_personas = json.load(open('./data/msc_speakers_single.json', encoding='utf-8'))
        available_indices = [idx for idx, d in enumerate(all_personas['train'])]
        if not available_indices:
            logging.warning("No available personas in msc_speakers_single.json")
            return None, None
        
        selected_idx = secrets.choice(available_indices)
        attributes = all_personas['train'][selected_idx]
        
        # 使用 Speaker 字段和场景信息生成用户角色
        agent_b = get_persona(args, attributes['Speaker'], scenario_info=scenario_info)
        agent_b['persona_summary'] = agent_b['persona']
        agent_b['msc_prompt'] = attributes['Speaker']
        del agent_b['persona']
        
        print("Agent A (AI助手) Persona: %s" % agent_a['persona_summary'])
        print("Agent B (用户) Persona: %s" % agent_b['persona_summary'])
    return agent_a, agent_b


def get_persona(args, attributes, target='human', ref_age=None, scenario_info=None):
    """
    根据给定的属性信息和场景描述生成人物角色描述。
    
    使用ChatGPT模型根据人物属性和场景信息生成详细的人格描述，包括姓名、年龄、
    婚姻状况、工作、兴趣爱好等信息，并确保人物与场景相符。
    
    Args:
        args: 包含prompt目录路径的命令行参数
        attributes: 人物的基本属性信息字典
        target: 目标类型，默认为'human'
        ref_age: 参考年龄，用于生成年龄相近的角色
        scenario_info: 场景信息字典，包含场景名称、描述和时间上下文等
    
    Returns:
        dict: 包含'persona'和'name'键的角色描述字典
    """
    # 为 json.load() 添加编码参数，避免编码问题
    task = json.load(open(os.path.join(args.prompt_dir, 'persona_generation_examples.json'), encoding='utf-8')) 
    persona_examples = [task["input_prefix"] + json.dumps(e["input"], indent=2, ensure_ascii=False) + '\n' + task["output_prefix"] + e["output"] for e in task['examples']]
    input_string = task["input_prefix"] + json.dumps(attributes, indent=2, ensure_ascii=False)

    # 根据是否有场景信息选择不同的prompt
    if scenario_info:
        scenario_name = scenario_info.get('name', '')
        scenario_desc = scenario_info.get('description', '')
        scenario_time = scenario_info.get('time_context', '')
        
        query = PERSONA_FROM_MSC_PROMPT_WITH_SCENARIO % (persona_examples, scenario_name, scenario_desc, scenario_time, input_string)
    else:
        query = PERSONA_FROM_MSC_PROMPT % (persona_examples, input_string)

    try:
        output = run_chatgpt(query, num_gen=1, num_tokens_request=1000, use_16k=True).strip()
        output = json.loads(output)
    except:
        output = run_chatgpt(query, num_gen=1, num_tokens_request=1000, use_16k=True).strip()
        output = json.loads(output)
    
    if type(output) == list:
        output = [clean_json_output(out) for out in output]
    elif type(output) == str:
        output = clean_json_output(output)
    elif type(output) == dict:
        output = {k.lower(): v for k,v in output.items()}
        pass
    else:
        raise TypeError
    
    # print(output)

    return output


def get_datetime_string(input_time=None, input_date=None):
    """
    将输入的时间和日期格式化为可读的字符串。
    
    根据提供的输入时间或日期，返回格式化的字符串表示。
    支持仅提供时间、仅提供日期或同时提供两者的情况。
    
    Args:
        input_time: 时间元组 (hour, minute)，可选
        input_date: 日期元组 (year, month, day)，可选
        
    Returns:
        str: 格式化的时间日期字符串
             - 仅时间: "9:30 am"
             - 仅日期: "5 January, 2023"
             - 完整: "9:30 am on 5 January, 2023"
    """

    assert input_time or input_date

    # 处理日期部分
    if input_date:
        year, month, day = input_date
        date_str = str(day) + ' ' + str(month) + ', ' + str(year)
    else:
        date_str = ''
    
    # 处理时间部分
    if input_time:
        hour_int, min_int = input_time
        time_mod = 'am' if hour_int <= 12 else 'pm'
        display_hour = hour_int if hour_int <= 12 else hour_int - 12
        min_str = str(min_int).zfill(2)
        time_str = str(display_hour) + ':' + min_str + ' ' + time_mod
    else:
        time_str = ''

    # 组合返回
    if input_time and not input_date:
        return time_str
    elif input_date and not input_time:
        return date_str
    else:
        return time_str + ' on ' + date_str 





def clean_dialog(output, name):
    """
    清理对话输出文本，去除说话人名字前缀。
    
    当模型输出包含说话人名字前缀时（如 "Alice: xxx"），
    将其去除以获得纯对话内容。
    
    Args:
        output: 原始输出字符串
        name: 说话人名字
        
    Returns:
        str: 清理后的对话文本
    """

    if output.startswith(name):
        output = output[len(name):]
        output = output.strip()
        if output[0] == ':':
            output = output[1:]
            output = output.strip()
    
    return output


def clean_json_output(output_string):
    """
    清理并解析JSON输出字符串。
    
    处理模型返回的JSON字符串可能存在的各种格式问题，
    如括号不平衡、前后多余字符等，确保能被正确解析。
    
    Args:
        output_string: 原始JSON字符串
        
    Returns:
        dict 或 list: 解析后的JSON对象
    """

    print(output_string)

    output_string = output_string.strip()

    if output_string[0] == '[' and output_string[-1] != ']':
        start_index = output_string.index('[')
        end_index = output_string.rindex(']')
        output_string = output_string[start_index:end_index+1]

    if output_string[0] == '{' and output_string[-1] != '}':
        start_index = output_string.index('{')
        end_index = output_string.rindex('}')
        output_string = output_string[start_index:end_index+1]

    # balance brackets in json
    num_start_bracket = len(find_indices(output_string, '{'))
    num_end_bracket = len(find_indices(output_string, '}'))

    if num_start_bracket != num_end_bracket:
        if num_end_bracket < num_start_bracket:
            output_string = output_string + ' '.join(['}']*(num_start_bracket-num_end_bracket))
        if num_start_bracket < num_end_bracket:
            output_string = ' '.join(['{']*(num_end_bracket-num_start_bracket)) + ' ' + output_string

    # balance brackets in json
    num_start_bracket = len(find_indices(output_string, '['))
    num_end_bracket = len(find_indices(output_string, ']'))

    if num_start_bracket != num_end_bracket:
        if num_end_bracket < num_start_bracket:
            output_string = output_string + ' '.join(['[']*(num_start_bracket-num_end_bracket))
        if num_start_bracket < num_end_bracket:
            output_string = ' '.join([']']*(num_end_bracket-num_start_bracket)) + ' ' + output_string

    return json.loads(output_string)


def find_indices(list_to_check, item_to_find):
    """
    查找列表中所有匹配项的索引。
    
    Args:
        list_to_check: 要搜索的列表
        item_to_find: 要查找的项
        
    Returns:
        list: 所有匹配项的索引列表
    """
    indices = []
    for idx, value in enumerate(list_to_check):
        if value == item_to_find:
            indices.append(idx)
    return indices



