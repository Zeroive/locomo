"""
文件操作相关工具函数。

包括角色对象的保存和加载功能。
"""

import json
import logging


def save_agents(agents, args):
    """
    保存角色对象到JSON文件。
    
    将两个角色的最新状态序列化并保存到指定路径，以便后续会话复用。
    
    Args:
        agents: (agent_a, agent_b) 角色对象元组
        args: 包含agent_a_file和agent_b_file路径的命令行参数
        
    Returns:
        None
    """
    agent_a, agent_b = agents
    logging.info("Saving updated Agent A to %s" % args.agent_a_file)
    with open(args.agent_a_file, 'w', encoding='utf-8') as f:
        json.dump(agent_a, f, indent=2, ensure_ascii=False)
    logging.info("Saving updated Agent B to %s" % args.agent_b_file)
    with open(args.agent_b_file, 'w', encoding='utf-8') as f:
        json.dump(agent_b, f, indent=2, ensure_ascii=False)


def load_agents(args):
    """
    从JSON文件加载角色对象。
    
    从指定路径读取两个角色的保存状态。
    
    Args:
        args: 包含agent_a_file和agent_b_file路径的命令行参数
        
    Returns:
        tuple: (agent_a, agent_b) 两个角色对象
    """
    agent_a = json.load(open(args.agent_a_file, encoding='utf-8'))
    agent_b = json.load(open(args.agent_b_file, encoding='utf-8'))
    return agent_a, agent_b