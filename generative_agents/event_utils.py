import os, json
import time
import openai
import logging
from datetime import datetime
from global_methods import run_chatgpt
logging.basicConfig(level=logging.INFO)



EVENT_KG_FROM_PERSONA_PROMPT_SEQUENTIAL_INIT = """
根据人物的简短性格描述，编写一个代表其生活中发生的子事件的图。节点代表子事件，边代表过去子事件对当前子事件的影响。
- 图以JSON列表形式表示。
- 每个条目是一个字典，包含以下键："sub-event"、"date"、"caused_by"、"id"。
- "sub-event"字段包含子事件的简短描述。
- "date"字段包含日期。
- "id"字段包含子事件的唯一标识符。
- "caused_by"字段表示边，是导致此子事件的现有子事件的"id"列表。"caused_by"字段中的子事件应发生在它们所导致的子事件之前的日期。尽可能生成更多的因果关系。
- 因果效应的一个例子是子事件"开始了一个菜园"导致"收获了西红柿"。
- 子事件可以是积极的或消极的生活事件。

例如，

PERSONALITY: %s
OUTPUT: %s

----------------------------------------------------------------------------------------------------------------

根据以下输入的性格描述，生成三个独立的子事件E1、E2和E3，与他们的性格相符。子事件可以是积极的或消极的生活事件，应反映人物关系、心态、性格等方面的演变。

PERSONALITY: %s
OUTPUT: 
"""



EVENT_KG_FROM_PERSONA_PROMPT_SEQUENTIAL_CONTINUE = """
根据人物的简短性格描述，编写一个代表其生活中发生的子事件的图。节点代表子事件，边代表过去子事件对当前子事件的影响。
- 图以JSON列表形式表示。
- 每个条目是一个字典，包含以下键："sub-event"、"date"、"caused_by"、"id"。
- "sub-event"字段包含子事件的简短描述。
- "date"字段包含日期。
- "id"字段包含子事件的唯一标识符。
- "caused_by"字段表示边，是导致此子事件的现有子事件的"id"列表。"caused_by"字段中的子事件应发生在它们所导致的子事件之前的日期。尽可能生成更多的因果关系。
- 因果效应的一个例子是子事件"开始了一个菜园"导致"收获了西红柿"。
- 子事件可以是积极的或消极的生活事件。

例如，

PERSONALITY: %s
OUTPUT: %s

----------------------------------------------------------------------------------------------------------------

根据以下输入的性格描述，生成新的子事件%s，这些子事件由一个或多个现有子事件引起。子事件可以是积极的或消极的生活事件，应反映人物关系、心态、性格等方面的演变。不要重复现有的子事件。用方括号开始和结束你的答案。

PERSONALITY: %s
EXISTING: %s
OUTPUT:  
"""

def num_tokens_from_string(string: str, model_name: str) -> int:
    """Returns the number of tokens in a text string."""
    # 本地简单实现：中文按字符计算，英文按单词计算
    # 这是一个近似估算，实际token数可能略有差异
    tokens = 0
    for char in string:
        if '\u4e00' <= char <= '\u9fff':
            # 中文字符
            tokens += 1
        elif char.isspace():
            # 空格不计数
            continue
        else:
            # 英文字符和其他字符，按每4个字符算1个token
            tokens += 1
    # 额外加上标点和特殊字符的开销
    tokens = int(tokens * 1.1)
    return tokens

def sort_events_by_time(graph):
    """
    将事件图按时间顺序排序。
    
    解析每个事件节点中的日期字段，按日期从早到晚排序。
    
    Args:
        graph: 事件图列表，每个元素是包含'date'键的字典
        
    Returns:
        list: 按时间排序后的事件列表
    """

    def catch_date(date_str):
        date_format1 = '%d %B, %Y'
        date_format2 = '%d %B %Y'
        try:
            return datetime.strptime(date_str, date_format1)
        except:
            return datetime.strptime(date_str, date_format2)
    
    dates = [catch_date(node['date']) for node in graph]
    sorted_dates = sorted(enumerate(dates), key=lambda t: t[1])
    graph = [graph[idx] for idx, _ in sorted_dates]
    return graph


# get events in one initialization step and one or more continuation steps.
def get_events(agent, start_date, end_date, args):
    """
    生成人物的事件时间线。
    
    使用两阶段生成策略：首先初始化一批基础事件，然后根据需要继续生成更多事件。
    事件之间可能存在因果关系，后续事件可以由先前事件引起。
    
    Args:
        agent: 角色对象，包含persona_summary信息
        start_date: 事件开始日期字符串
        end_date: 事件结束日期字符串
        args: 包含num_events等配置的命令行参数
        
    Returns:
        list: 生成的事件列表，每个事件包含id、sub-event、date、caused_by等字段
    """


    task = json.load(open(os.path.join(args.prompt_dir, 'event_generation_examples.json'), encoding='utf-8'))
    persona_examples = [e["input"] + '\nGenerate events between 1 January, 2020 and 30 April, 2020.' for e in task['examples']]
    
    # Step 1: Get initial events
    task = json.load(open(os.path.join(args.prompt_dir, 'graph_generation_examples.json'), encoding='utf-8'))
    input = agent['persona_summary'] + '\nAssign dates between %s and %s.' % (start_date, end_date)
    query = EVENT_KG_FROM_PERSONA_PROMPT_SEQUENTIAL_INIT % (persona_examples[0], 
                                                                   json.dumps(task['examples'][0]["output"][:12], indent=2),
                                                                   input)
    logging.info("Generating initial events")
    try:
        output = run_chatgpt(query, num_gen=1, num_tokens_request=512, use_16k=False, temperature=1.0).strip()
        output = json.loads(output)
    except:
        output = run_chatgpt(query, num_gen=1, num_tokens_request=512, use_16k=False, temperature=1.0).strip()
        output = json.loads(output)

    agent_events = output
    print("The following events have been generated in the initialization step:")
    for e in agent_events:
        print(list(e.items()))

    # Step 2: continue generation
    while len(agent_events) < args.num_events:
        logging.info("Generating next set of events; current tally = %s" % len(agent_events))
        last_event_id = agent_events[-1]["id"]
        next_event_ids = ['E' + str(i) for i in list(range(int(last_event_id[1:]) + 1, int(last_event_id[1:]) + 5))]
        next_event_id_string = ', '.join(next_event_ids[:3]) + ' and ' + next_event_ids[-1] 
        query = EVENT_KG_FROM_PERSONA_PROMPT_SEQUENTIAL_CONTINUE % (persona_examples[0], 
                                                                   json.dumps(task['examples'][0]["output"][:12], indent=2),
                                                                   next_event_id_string,
                                                                   input,
                                                                   json.dumps(agent_events, indent=2)
                                                                   )
        query_length = num_tokens_from_string(query, 'gpt-3.5-turbo')
        request_length = min(1024, 4096-query_length)
        try:
            output = run_chatgpt(query, num_gen=1, num_tokens_request=request_length, use_16k=False, temperature=1.0).strip()
            output = json.loads(output)
        except:
            output = run_chatgpt(query, num_gen=1, num_tokens_request=request_length, use_16k=False, temperature=1.0).strip()
            output = json.loads(output)
        
        existing_eids = [e["id"] for e in agent_events]
        agent_events.extend([o for o in output if o["id"] not in existing_eids])
        print("Adding events:")
        for e in agent_events:
            print(list(e.items()))

        # filter out standalone events
        if len(agent_events) > args.num_events:
            agent_events = filter_events(agent_events)

    return agent_events


def filter_events(events):
    """
    过滤孤立事件，保留有因果关联的事件。
    
    孤立事件是指既不导致其他事件发生，也不由其他事件引起的节点。
    这些事件缺少上下文关联，在使用时可能缺乏意义。
    
    Args:
        events: 事件列表，每个事件包含id和caused_by字段
        
    Returns:
        list: 过滤后保留的有因果关联的事件列表
    """

    id2events = {e["id"]: e for e in events}
    remove_ids = []
    for id in id2events.keys():
        # print(id)
        has_child = False
        # check if event has parent
        if len(id2events[id]["caused_by"]) > 0:
            continue
        # check if event has children
        for e in events:
            if id in e["caused_by"]:
                # print("Found %s in %s" % (id, e['id']))
                has_child = True
        
        if not has_child:
            # print("Did not find any connections for %s" % id)
            remove_ids.append(id)
    
    print("*** Removing %s standalone events from %s events: %s ***" % (len(remove_ids), len(id2events), ', '.join(remove_ids)))
    # for id in remove_ids:
        # print(id2events[id])
    
    return [e for e in events if e["id"] not in remove_ids]
