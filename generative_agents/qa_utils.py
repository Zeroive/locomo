"""
QA对生成工具函数模块。

包含根据会话事实生成QA对的相关功能。
"""

import json
import re
import logging
import os

from global_methods import run_chatgpt


def build_qa_prompt(session_facts: dict, dialog_turns: list = []) -> str:
    """
    构建生成QA对的prompt
    
    Args:
        session_facts: 会话事实字典，键为说话人，值为事实列表
        dialog_turns: 原始对话轮次（可选）
    
    Returns:
        完整的prompt字符串
    """
    # 格式化事实
    facts_str = ""
    fact_id_map = {}
    fact_idx = 1
    
    for speaker, facts in session_facts.items():
        facts_str += f"## {speaker} 的事实\n"
        for fact_item in facts:
            fact_text = fact_item[0]
            fact_source = fact_item[1] if len(fact_item) > 1 else f"D{fact_idx}"
            fact_id = f"F{fact_idx}"
            fact_id_map[fact_source] = fact_id
            facts_str += f"{fact_id}: {fact_text} (来源: {fact_source})\n"
            fact_idx += 1
    
    # 格式化对话轮次
    turns_str = ""
    if dialog_turns:
        turns_str = "## 原始对话轮次\n"
        for turn in dialog_turns:
            turn_id = turn.get('dia_id', f"T{len(turns_str.split('\n'))}")
            speaker = turn.get('speaker', 'unknown')
            text = turn.get('clean_text', turn.get('text', ''))
            turns_str += f"{turn_id}: [{speaker}] {text}\n"
    
    prompt = f"""
你是长期对话记忆 QA 数据集构造助手。 

给定一组 memory facts 和原始 evidence turns，请生成候选 QA 对。 
问题必须只能根据给定证据回答，不能依赖猜测。 

## Memory Facts
{facts_str}

{turns_str}

## 请生成以下类别的问题：
1. **single-hop**：答案来自一个事实。
2. **multi-hop**：答案需要结合两个或多个事实。
3. **temporal**：答案需要时间顺序、最近一次、之前/之后等信息。
4. **tool-use**：答案涉及用户意图对应的设备操作或工具调用。
5. **adversarial**：问题看似相关，但对话中没有足够信息，答案应为"无法从对话中确定"。

## 输出格式要求
每条 QA 输出一个 JSON 对象，每行一个：
{{
  "qa_id": "QA_1",
  "category": "single-hop | multi-hop | temporal | tool-use | adversarial",
  "question": "...",
  "answer": "...",
  "evidence_turn_ids": ["T1", "T2", ...],
  "source_fact_ids": ["F1", "F2", ...],
  "difficulty": "easy | medium | hard",
  "requires_temporal_reasoning": true/false,
  "requires_tool_use": true/false
}}

## 约束：
1. answer 必须简洁。
2. evidence_turn_ids 必须足以支持 answer。
3. 不要生成常识题，除非类别是 open-domain。
4. adversarial 问题的 evidence_turn_ids 必须为空数组。
5. 不要问答案过于明显、无意义或重复的问题。
6. 不要使用今天、昨天、明天等指代时间，而应使用具体的时间。
7. 至少生成5个不同类别的QA对。

## 输出示例
{{"qa_id": "QA_1", "category": "single-hop", "question": "张强计划几点出门？", "answer": "七点", "evidence_turn_ids": ["D1:1"], "source_fact_ids": ["F1"], "difficulty": "easy", "requires_temporal_reasoning": false, "requires_tool_use": false}}
{{"qa_id": "QA_2", "category": "multi-hop", "question": "张强出门前需要检查哪些事项？", "answer": "检查伞、会议时间和门锁", "evidence_turn_ids": ["D1:1", "D1:3"], "source_fact_ids": ["F1", "F2"], "difficulty": "medium", "requires_temporal_reasoning": false, "requires_tool_use": false}}
{{"qa_id": "QA_3", "category": "adversarial", "question": "张强的会议几点开始？", "answer": "无法从对话中确定", "evidence_turn_ids": [], "source_fact_ids": [], "difficulty": "medium", "requires_temporal_reasoning": false, "requires_tool_use": false}}
"""
    
    return prompt.strip()


def parse_qa_response(response: str) -> list:
    """
    解析模型返回的QA对响应
    
    Args:
        response: 模型响应字符串
    
    Returns:
        QA对列表
    """
    qa_pairs = []
    
    try:
        # 尝试按行解析JSON
        lines = response.strip().split('\n')
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # 尝试直接解析
            try:
                qa = json.loads(line)
                qa_pairs.append(qa)
            except json.JSONDecodeError:
                # 尝试提取JSON部分
                match = re.search(r'\{.*\}', line, re.DOTALL)
                if match:
                    try:
                        qa = json.loads(match.group())
                        qa_pairs.append(qa)
                    except json.JSONDecodeError:
                        continue
    except Exception as e:
        logging.error(f"Failed to parse QA response: {e}")
    
    return qa_pairs


def generate_qa_pairs(agent_a, agent_b, args):
    """
    根据会话事实生成QA对
    
    Args:
        agent_a: AI助手对象
        agent_b: 用户对象
        args: 命令行参数
    
    Returns:
        QA对列表
    """
    all_qa_pairs = []
    qa_id = 1
    
    # 获取所有会话的事实
    num_sessions = args.num_sessions
    for sess_id in range(1, num_sessions + 1):
        # 获取会话事实
        facts_key = f'session_{sess_id}_facts'
        if facts_key not in agent_a:
            logging.warning(f"No facts found for session {sess_id}, skipping QA generation")
            continue
        
        session_facts = agent_a[facts_key]
        
        # 获取会话对话（用于获取turn IDs）
        session_key = f'session_{sess_id}'
        dialog_turns = agent_a.get(session_key, [])
        
        # 构建prompt并调用模型
        prompt = build_qa_prompt(session_facts, dialog_turns)
        response = run_chatgpt(prompt, temperature=0.7, num_tokens_request=2000)
        
        # 解析响应
        try:
            result_data = json.loads(response)
            content = result_data['choices'][0]['message']['content']
        except (json.JSONDecodeError, KeyError, IndexError):
            content = response
        
        # 解析QA对
        session_qa_pairs = parse_qa_response(content)
        
        # 更新QA ID
        for qa in session_qa_pairs:
            qa['qa_id'] = f"QA_{qa_id}"
            qa['session_id'] = sess_id
            qa_id += 1
        
        all_qa_pairs.extend(session_qa_pairs)
    
    # 保存QA对到文件
    qa_output_path = os.path.join(args.out_dir, 'qa_pairs.json')
    with open(qa_output_path, 'w', encoding='utf-8') as f:
        json.dump(all_qa_pairs, f, ensure_ascii=False, indent=2)
    
    logging.info(f"Generated {len(all_qa_pairs)} QA pairs, saved to {qa_output_path}")
    
    return all_qa_pairs