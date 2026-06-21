import os, json
import time
import openai
import logging
from datetime import datetime
from global_methods import run_json_trials, get_openai_embedding
import numpy as np
import pickle as pkl
import random
logging.basicConfig(level=logging.INFO)


REFLECTION_INIT_PROMPT = "{}\n\nGiven the information above, what are the three most salient insights that {} has about {}? Give concise answers in the form of a json list where each entry is a string."

REFLECTION_CONTINUE_PROMPT = "{} has the following insights about {} from previous interactions.{}\n\nTheir next conversation is as follows:\n\n{}\n\nGiven the information above, what are the three most salient insights that {} has about {} now? Give concise answers in the form of a json list where each entry is a string."

SELF_REFLECTION_INIT_PROMPT = "{}\n\nGiven the information above, what are the three most salient insights that {} has about self? Give concise answers in the form of a json list where each entry is a string."

SELF_REFLECTION_CONTINUE_PROMPT = "{} has the following insights about self.{}\n\n{}\n\nGiven the information above, what are the three most salient insights that {} has about self now? Give concise answers in the form of a json list where each entry is a string."


CONVERSATION2FACTS_PROMPT = """
根据对话内容，为每个说话人写一份简洁的观察事实列表。对话中的每一句都包含一个对话ID（在方括号中）。每个观察事实应包含关于说话人的具体信息，并注明信息来源的对话ID。观察事实应该是客观的、可作为数据库使用的事实信息。避免抽象的观察（如"说话人很支持"、"说话人很感激"等）。不要遗漏对话中的任何信息。重要：字符串中的双引号需要用反斜杠转义。输出格式必须是JSON字典，键是说话人名字，值是该说话人的事实列表（每个事实是对话ID和事实描述的元组）。\n\n
"""


RETRIEVAL_MODEL = "text-embedding-ada-002" # contriever dragon dpr


def get_embedding(texts, model="Qwen3-Embedding-8B"):
    """
    获取文本的向量嵌入表示。
    
    使用指定的嵌入模型将文本转换为向量表示，用于后续的
    相似度计算和上下文检索。
    
    Args:
        texts: 文本字符串或文本列表
        model: 嵌入模型名称，默认为"Qwen3-Embedding-8B"
        
    Returns:
        numpy.ndarray: 文本的嵌入向量表示
    """
    return get_openai_embedding(texts, model)


def get_session_facts(args, agent_a, agent_b, session_idx, return_embeddings=True):
    """
    从会话对话中提取事实信息。
    
    使用ChatGPT分析对话内容，为每个说话人提取客观的事实陈述。
    每个事实包含对话ID作为引用来源。同时生成对应的事实嵌入向量。
    
    Args:
        args: 包含prompt_dir等配置的命令行参数
        agent_a: 第一个说话人对象
        agent_b: 第二个说话人对象
        session_idx: 会话索引
        return_embeddings: 是否返回嵌入向量，默认为True
        
    Returns:
        dict: 以说话人名字为键的事实列表字典；如果return_embeddings为True，
              同时将嵌入向量保存到文件
    """
    # Step 1: get events
    task = json.load(open(os.path.join(args.prompt_dir, 'fact_generation_examples_new.json'), encoding='utf-8'))
    query = CONVERSATION2FACTS_PROMPT
    examples = [[task['input_prefix'] + e["input"], json.dumps(e["output"], indent=2)] for e in task['examples']]

    conversation = ""
    conversation += agent_a['session_%s_date_time' % session_idx] + '\n'
    for i, dialog in enumerate(agent_a['session_%s' % session_idx]):
        try:
            conversation += "[%s] " % dialog["dia_id"] + dialog['speaker'] + ' said, \"' + dialog['clean_text'] + '\"'
        except KeyError:
            conversation += "[%s] " % dialog["dia_id"] + dialog['speaker'] + ' said, \"' + dialog['text'] + '\"'

        if 'blip_caption' in dialog:
            conversation += ' and shared ' + dialog['blip_caption']
        conversation += '\n'
    
    # print(conversation)
    
    input = task['input_prefix'] + conversation
    facts = run_json_trials(query, num_gen=1, num_tokens_request=500, use_16k=False, examples=examples, input=input)

    if not return_embeddings:
        return facts

    agent_a_embeddings = get_embedding([agent_a['session_%s_date_time' % session_idx] + ', ' + f for f, _ in facts[agent_a['name']]])
    agent_b_embeddings = get_embedding([agent_b['session_%s_date_time' % session_idx] + ', ' + f for f, _ in facts[agent_b['name']]])

    if session_idx > 1:
        with open(args.emb_file, 'rb') as f:
            embs = pkl.load(f)
    
        embs[agent_a['name']] = np.concatenate([embs[agent_a['name']], agent_a_embeddings], axis=0)
        embs[agent_b['name']] = np.concatenate([embs[agent_b['name']], agent_b_embeddings], axis=0)
    else:
        embs = {}
        embs[agent_a['name']] = agent_a_embeddings
        embs[agent_b['name']] = agent_b_embeddings
    
    with open(args.emb_file, 'wb') as f:
        pkl.dump(embs, f)
    
    return facts


def get_session_reflection(args, agent_a, agent_b, session_idx):
    """
    生成会话反思和洞察。
    
    分析对话内容，提取两个层面的反思：
    1. 自我反思：每个说话人对自己的认知和洞察
    2. 相互反思：每个说话人对另一个说话人的认知
    
    反思信息用于增强后续对话生成的上下文。
    
    Args:
        args: 命令行参数
        agent_a: 第一个说话人对象
        agent_b: 第二个说话人对象
        session_idx: 会话索引
        
    Returns:
        dict: 包含'a'和'b'两个键的反思字典，每个键对应包含'self'和'other'子键的结构
    """


    # Step 1: get conversation
    conversation = ""
    conversation += agent_a['session_%s_date_time' % session_idx] + '\n'
    for dialog in agent_a['session_%s' % session_idx]:
        # if 'clean_text' in dialog:
        #     writer.write(dialog['speaker'] + ' said, \"' + dialog['clean_text'] + '\"\n')
        # else:
        conversation += dialog['speaker'] + ' said, \"' + dialog['clean_text'] + '\"\n'


    # Step 2: Self-reflections
    if session_idx == 1:
        agent_a_self = run_json_trials(SELF_REFLECTION_INIT_PROMPT.format(conversation, agent_a['name']), model='chatgpt', num_tokens_request=300)
        agent_b_self = run_json_trials(SELF_REFLECTION_INIT_PROMPT.format(conversation, agent_b['name']), model='chatgpt', num_tokens_request=300)

    else:
        agent_a_self = run_json_trials(SELF_REFLECTION_CONTINUE_PROMPT.format(agent_a['name'], '\n'.join(agent_a['session_%s_reflection' % (session_idx-1)]['self']), conversation, agent_a['name']), model='chatgpt', num_tokens_request=300)
        agent_b_self = run_json_trials(SELF_REFLECTION_CONTINUE_PROMPT.format(agent_b['name'], '\n'.join(agent_b['session_%s_reflection' % (session_idx-1)]['self']), conversation, agent_b['name']), model='chatgpt', num_tokens_request=300)

    # Step 3: Reflection about other speaker
    if session_idx == 1:
        agent_a_on_b = run_json_trials(REFLECTION_INIT_PROMPT.format(conversation, agent_a['name'], agent_b['name']), model='chatgpt', num_tokens_request=300)
        agent_b_on_a = run_json_trials(REFLECTION_INIT_PROMPT.format(conversation, agent_b['name'], agent_a['name']), model='chatgpt', num_tokens_request=300)

    else:
        agent_a_on_b = run_json_trials(REFLECTION_CONTINUE_PROMPT.format(agent_a['name'], agent_b['name'], '\n'.join(agent_a['session_%s_reflection' % (session_idx-1)]['other']), conversation, agent_a['name'], agent_b['name']), model='chatgpt', num_tokens_request=300)
        agent_b_on_a = run_json_trials(REFLECTION_CONTINUE_PROMPT.format(agent_b['name'], agent_a['name'], '\n'.join(agent_b['session_%s_reflection' % (session_idx-1)]['other']), conversation, agent_b['name'], agent_a['name']), model='chatgpt', num_tokens_request=300)

    if type(agent_a_self) == dict:
        agent_a_self = list(agent_a_self.values())
    if type(agent_b_self) == dict:
        agent_b_self = list(agent_b_self.values())
    if type(agent_a_on_b) == dict:
        agent_a_on_b = list(agent_a_on_b.values())
    if type(agent_b_on_a) == dict:
        agent_b_on_a = list(agent_b_on_a.values())  

    reflections = {}
    reflections['a'] = {'self': agent_a_self, 'other': agent_a_on_b}
    reflections['b'] = {'self': agent_b_self, 'other': agent_b_on_a}

    return reflections


def get_recent_context(agent_a, agent_b, sess_id, context_length=2, reflection=False):
    """
    获取最近会话的事实和反思上下文。
    
    从指定数量的最近会话中提取事实信息，可选择性地包含反思内容。
    用于在开始新会话时提供对话背景。
    
    Args:
        agent_a: 第一个说话人对象，包含各会话的事实和反思数据
        agent_b: 第二个说话人对象
        sess_id: 当前会话ID
        context_length: 上下文中包含的最近会话数量，默认为2
        reflection: 是否包含反思信息，默认为False
        
    Returns:
        tuple: (speaker_1上下文列表, speaker_2上下文列表)
    """

    speaker_1_facts = []
    speaker_2_facts = []
    
    # 检查是否有可用的 facts 数据
    has_facts = 'session_1_facts' in agent_a
    
    if has_facts:
        for i in range(1, sess_id):
            session_key = 'session_%s_facts' % i
            if session_key in agent_a:
                session_time = agent_a.get('session_%s_date_time' % i, '')
                facts_data = agent_a[session_key]
                if agent_a["name"] in facts_data:
                    speaker_1_facts += [session_time + ': ' + f for f, _ in facts_data[agent_a["name"]]]
                if agent_b["name"] in facts_data:
                    speaker_2_facts += [session_time + ': ' + f for f, _ in facts_data[agent_b["name"]]]
    
    if reflection:
        # 检查是否有可用的 reflection 数据
        if 'session_%s_reflection' % (sess_id-1) in agent_a:
            print(speaker_1_facts[-context_length:])
            print(agent_a['session_%s_reflection' % (sess_id-1)]['self'])
            return speaker_1_facts[-context_length:] + agent_a['session_%s_reflection' % (sess_id-1)]['self'], speaker_2_facts[-context_length:] + agent_a['session_%s_reflection' % (sess_id-1)]['other']
        else:
            return speaker_1_facts[-context_length:] if speaker_1_facts else [], speaker_2_facts[-context_length:] if speaker_2_facts else []
    else:
        return speaker_1_facts[-context_length:] if speaker_1_facts else [], speaker_2_facts[-context_length:] if speaker_2_facts else []


def get_relevant_context(agent_a, agent_b, input_dialogue, embeddings, sess_id, context_length=2, reflection=False):
    """
    基于语义相似度检索相关上下文。
    
    使用嵌入向量计算输入对话与历史事实的相似度，
    检索出最相关的上下文用于增强当前对话生成。
    
    Args:
        agent_a: 第一个说话人对象
        agent_b: 第二个说话人对象
        input_dialogue: 当前输入的对话内容
        embeddings: 历史事实的嵌入向量字典
        sess_id: 当前会话ID
        context_length: 检索的上下文数量，默认为2
        reflection: 是否在结果中包含反思内容，默认为False
        
    Returns:
        tuple: (speaker_1相关上下文列表, speaker_2相关上下文列表)
    """

    logging.info("Getting relevant context for response to %s (session %s)" % (input_dialogue, sess_id))
    
    # 获取基础上下文（现在会安全处理缺失的 facts）
    contexts_a, context_b = get_recent_context(agent_a, agent_b, sess_id, 10000)
    
    # 如果没有嵌入向量或上下文为空，返回空结果
    if embeddings is None or not contexts_a:
        return [], []
    
    # embeddings = pkl.load(open(emb_file, 'rb'))
    input_embedding = get_embedding([input_dialogue])
    sims_with_context_a = np.dot(embeddings[agent_a['name']], input_embedding[0])
    sims_with_context_b = np.dot(embeddings[agent_b['name']], input_embedding[0])
    top_k_sims_a = np.argsort(sims_with_context_a)[::-1][:context_length]
    top_k_sims_b = np.argsort(sims_with_context_b)[::-1][:context_length]
    # print(sims_with_context_a, sims_with_context_b)
    if reflection:
        # 检查是否有 reflection 数据
        if 'session_%s_reflection' % (sess_id-1) in agent_a:
            print([contexts_a[idx] for idx in top_k_sims_a])
            print(agent_a['session_%s_reflection' % (sess_id-1)]['self'])
            return [contexts_a[idx] for idx in top_k_sims_a] + random.sample(agent_a['session_%s_reflection' % (sess_id-1)]['self'], k=context_length//2), [context_b[idx] for idx in top_k_sims_b] + random.sample(agent_a['session_%s_reflection' % (sess_id-1)]['other'], k=context_length//2)
        else:
            return [contexts_a[idx] for idx in top_k_sims_a], [context_b[idx] for idx in top_k_sims_b]
    else:
        return [contexts_a[idx] for idx in top_k_sims_a], [context_b[idx] for idx in top_k_sims_b]


def save_embeddings(agents, args, sess_id):
    """
    保存会话嵌入向量到文件。
    
    从会话对话中提取事实信息，生成嵌入向量，并保存到指定文件。
    嵌入向量用于后续的细粒度检索记忆模块。
    
    Args:
        agents: 包含两个说话人对象的列表 [agent_a, agent_b]
        args: 包含emb_file等配置的命令行参数
        sess_id: 当前会话索引
    """
    agent_a, agent_b = agents[0], agents[1]
    
    # 获取会话事实并生成嵌入
    facts = get_session_facts(args, agent_a, agent_b, sess_id, return_embeddings=True)
    
    # 保存事实到agent对象
    agent_a['session_%s_facts' % sess_id] = facts
    agent_b['session_%s_facts' % sess_id] = facts

