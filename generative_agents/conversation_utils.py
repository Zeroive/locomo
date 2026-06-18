import json, re, os
import random
from global_methods import run_chatgpt, run_chatgpt_with_examples

PERSONA_FROM_MSC_PROMPT = "Let's write speaker descriptions from a given set of life attributes. Example:\n\n%s\n\nNote: Add crucial details in the persona about the person such as their name, age, marital status, gender, job etc. Add additional details like names of family/friends or specific activities, likes and dislikes, experiences when appropriate.\n\nFor the following attributes, write a persona. Output a json file with the keys 'persona' and 'name'.\n\n%s\n\nStart your answer with a curly bracket.\n"


AGENT_CONV_PROMPT_SESS_1 = """%s

%s 站在家中，准备离家出门，正在与家庭AI助手 %s 对话。今天是 %s，全家人即将外出，需要布防。请扮演 %s 的角色，写下你对AI助手 %s 要说的下一句话。如果开始对话，可以从询问安全状态、启动布防模式、检查门窗状态、设置警报、确认监控开始。不要重复之前已分享的信息。让对话围绕离家布防的活动，例如确认布防状态、检查门窗是否关好、设置警报灵敏度、开启摄像头监控、询问异常记录等。包括时间参考，如"现在"、"这会儿"等。回复不超过20个字。

要结束对话，请写'布防完成！'。

对话：

"""

AGENT_CONV_PROMPT_SESS_1_W_EVENTS = """
使用给定的PERSONALITY写下对话中你要说的下一句话。
- 如果开始对话，可以从询问安全状态、启动布防模式、检查门窗状态、设置警报、确认监控开始。
- 不要重复之前对话中已分享的信息。
- 包括时间参考，如"现在"、"这会儿"等。
- 回复不超过20个字。
- 提出后续问题跟进之前的对话。

PERSONALITY: %s

%s 站在家中，准备离家出门，正在与家庭AI助手 %s 对话。今天是 %s，全家人即将外出。以下是最近发生的安全相关事件。
事件：%s

请扮演 %s 的角色，与AI助手 %s 就这些事件进行对话，围绕离家布防的活动。%s
"""


AGENT_CONV_PROMPT = """%s

%s 上次与家庭AI助手 %s 对话是在 %s。%s

今天是 %s，%s 站在家中，准备离家出门。请扮演 %s 的角色，写下你对AI助手 %s 要说的下一句话。如果开始对话，可以从询问安全状态、启动布防模式、检查门窗状态、设置警报、确认监控开始。不要重复已分享的信息。让对话围绕离家布防的活动，例如确认布防状态、检查门窗是否关好、设置警报灵敏度、开启摄像头监控、询问异常记录等。包括时间参考，如"现在"、"这会儿"等。回复不超过20个字。

要结束对话，请写'布防完成！'。

对话：

"""


AGENT_CONV_PROMPT_W_EVENTS = """
使用给定的PERSONALITY写下对话中你要说的下一句话。
- 如果开始对话，可以从询问安全状态、启动布防模式、检查门窗状态、设置警报、确认监控开始。
- 不要重复之前对话中已分享的信息。
- 让对话围绕离家布防的活动，例如确认布防状态、检查门窗是否关好、设置警报灵敏度、开启摄像头监控、询问异常记录等。
- 包括时间参考，如"现在"、"这会儿"等。
- 回复不超过20个字。
- 提出后续问题跟进之前的对话。

PERSONALITY: %s

%s 上次与家庭AI助手 %s 对话是在 %s。

%s

今天是 %s，%s 站在家中，准备离家出门。你是 %s。以下是最近发生的安全相关事件：
%s

在对话中使用这些事件。%s 请根据你的PERSONALITY写下你在与AI助手 %s 的对话中要说的下一句话：
"""


AGENT_CONV_PROMPT_W_EVENTS_V2_INIT = """
使用给定的PERSONALITY写下对话中你要说的下一句话。
- 回复不超过20个字。
- 让对话围绕离家布防的活动，例如确认布防状态、检查门窗是否关好、设置警报灵敏度、开启摄像头监控、询问异常记录等。详细讨论重要的事件。
- 不要重复之前对话中已分享的信息。
- 包括时间参考，如"现在"、"这会儿"等。
- 有时，提出后续问题跟进之前的对话或当前话题。

PERSONALITY: %s


%s 上次与家庭AI助手 %s 对话是在 %s。今天是 %s，%s 站在家中，准备离家出门。你是 %s。

这是到目前为止的对话摘要。
摘要：
%s

以下是最近发生的安全相关事件：
事件：
%s



%s 请写下你在与AI助手 %s 的对话中要说的下一句深思熟虑的话。在对话中只讨论给定的事件及其对离家布防的影响。如果事件有负面影响，请表达担忧。
"""


AGENT_CONV_PROMPT_W_EVENTS_V2 = """
使用给定的PERSONALITY写下对话中你要说的下一句话。
- 回复不超过20个字。
- 让对话围绕离家布防的活动，例如确认布防状态、检查门窗是否关好、设置警报灵敏度、开启摄像头监控、询问异常记录等。详细讨论重要的事件。
- 不要重复之前对话中已分享的信息。
- 包括时间参考，如"现在"、"这会儿"等。
- 有时，提出后续问题跟进之前的对话或当前话题。

PERSONALITY: %s

%s 上次与家庭AI助手 %s 对话是在 %s。今天是 %s，%s 站在家中，准备离家出门。你是 %s。

这是到目前为止的对话摘要。
摘要：
%s

以下是最近发生的安全相关事件：
事件：
%s

以下是双方都知道的信息。
相关上下文：
%s

%s 请写下你在与AI助手 %s 的对话中要说的下一句深思熟虑的话，围绕离家布防的活动。在对话中只讨论给定的事件及其对离家布防的影响。如果事件有负面影响，请表达担忧。
"""


CASUAL_DIALOG_PROMPT = "将句子改得更短、更随意、更口语化。\n\n输入：%s\n输出："


SESSION_SUMMARY_PROMPT = "%s 和 %s 到目前为止的对话可以总结如下：%s。当前时间和日期是 %s。%s 和 %s 刚刚进行了以下对话：\n\n%s\n\n请用150字或更少的字数总结 %s 和 %s 之间之前和当前的对话。包括关于两位说话者的关键事实和时间参考。\n\n"


SESSION_SUMMARY_INIT_PROMPT = "请写一个简洁的摘要，包含在 %s 的对话中提到的关于 %s 和 %s 的关键事实：\n\n%s\n\n"


def get_msc_persona(args):
    # check if personas exist, else generate persona + summary
    if (os.path.exists(args.agent_a_file) and os.path.exists(args.agent_b_file)) and not args.overwrite_persona:
        return None, None
    else:
        all_personas = json.load(open('./data/msc_personas_all.json', encoding='utf-8'))
        selected_idx = random.choice([idx for idx, d in enumerate(all_personas['train']) if not d["in_dataset"]])
        attributes = all_personas['train'][selected_idx]
        with open('./data/msc_personas_all.json', "w", encoding='utf-8') as f:
            all_personas['train'][selected_idx]["in_dataset"] = 1
            json.dump(all_personas, f, indent=2, ensure_ascii=False)
        agent_a = get_persona(args, attributes['Speaker 1'])

        agent_a['persona_summary'] = agent_a['persona']
        agent_a['msc_prompt'] = attributes['Speaker 1']
        agent_b = get_persona(args, attributes['Speaker 2']) # setting the second agent to have age within +/- 5 years of first agent

        agent_b['persona_summary'] = agent_b['persona']
        agent_b['msc_prompt'] = attributes['Speaker 2']
        del agent_a['persona']
        del agent_b['persona']
        print("Agent A Persona: %s" % agent_a['persona_summary'])
        print("Agent B Persona: %s" % agent_b['persona_summary'])
    return agent_a, agent_b


def get_persona(args, attributes, target='human', ref_age=None):
    # 为 json.load() 添加编码参数，避免编码问题
    task = json.load(open(os.path.join(args.prompt_dir, 'persona_generation_examples.json'), encoding='utf-8')) 
    persona_examples = [task["input_prefix"] + json.dumps(e["input"], indent=2) + '\n' + task["output_prefix"] + e["output"] for e in task['examples']]
    input_string = task["input_prefix"] + json.dumps(attributes, indent=2)

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


def get_datetime_string(input_time='', input_date=''):

    assert input_time or input_date

    if input_date:
        year, month, day = input_date
    if input_time:
        hour, min = input_time
        time_mod = 'am' if hour <= 12 else 'pm'
        hour = hour if hour <= 12 else hour-12
        min = str(min).zfill(2)

    if input_time and not input_date:
        return str(hour) + ':' + min + ' ' + time_mod
    elif input_date and not input_time:
        return day + ' ' + month + ', ' + year
    else:
        return str(hour) + ':' + min + ' ' + time_mod + ' on ' + day + ' ' + month + ', ' + year 





def clean_dialog(output, name):

    if output.startswith(name):
        output = output[len(name):]
        output = output.strip()
        if output[0] == ':':
            output = output[1:]
            output = output.strip()
    
    return output


def clean_json_output(output_string):

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
    indices = []
    for idx, value in enumerate(list_to_check):
        if value == item_to_find:
            indices.append(idx)
    return indices



