"""
多会话对话生成主程序。

生成AI助手与用户之间的多轮对话，支持场景化配置和设备选择。
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import logging
import argparse
import os, json, random
from datetime import date, timedelta, datetime

# 导入重构后的模块
from generative_agents.file_utils import save_agents, load_agents
from generative_agents.time_utils import get_random_time, get_random_date, datetimeObj2Str, dateObj2Str, get_session_date
from generative_agents.device_utils import select_devices_for_user
from generative_agents.device_events_utils import generate_all_device_events, save_device_events, get_device_events_summary
from generative_agents.device_trajectory_utils import generate_all_device_trajectories
from generative_agents.session_utils import get_session, get_session_summary, get_relevant_events
from generative_agents.conversation_utils import get_msc_persona, get_datetime_string
from generative_agents.event_utils import get_events
from generative_agents.memory_utils import save_embeddings
from generative_agents.html_utils import convert_to_chat_html
from global_methods import run_chatgpt

logging.basicConfig(level=logging.INFO)


def parse_args():
    """
    解析命令行参数。
    
    Returns:
        argparse.Namespace: 解析后的参数对象
    """
    parser = argparse.ArgumentParser()

    parser.add_argument('--out-dir', required=True, type=str, help="Path to directory containing agent files for a conversation")
    parser.add_argument('--prompt-dir', required=True, type=str, help="Path to the dirctory containing in-context examples")
    
    parser.add_argument('--start-session', type=int, default=1, help="Start iterating from this index; first session is 1")
    parser.add_argument('--num-sessions', type=int, default=20, help="Maximum number of sessions in the conversation")
    parser.add_argument('--num-days', type=int, default=240, help="Desired temporal span of the multi-session conversation")
    parser.add_argument('--num-events', type=int, default=15, help="Total number of events to generate for each agent; 1 per session works best")
    parser.add_argument('--max-turns-per-session', type=int, default=20, help="Maximum number of total turns in each session")
    parser.add_argument('--num-events-per-session', type=int, default=50, help="Total number of events to be assigned to each agent per session; 1-2 works best")

    parser.add_argument('--persona', action="store_true", help="Set flag to sample a new persona from MSC and generate details")
    parser.add_argument('--session', action="store_true", help="Set flag to generate sessions based on the generated/existing personas")
    parser.add_argument('--events', action="store_true", help="Set flag to generate and events suited to the generated/existing personas")
    parser.add_argument('--overwrite-persona', action='store_true', help="Overwrite existing persona summaries saved in the agent files")
    parser.add_argument('--overwrite-events', action='store_true', help="Overwrite existing events saved in the agent files")
    parser.add_argument('--overwrite-session', action='store_true', help="Overwrite existing sessions saved in the agent files")
    parser.add_argument('--summary', action="store_true", help="Set flag to generate and use summaries in the conversation generation prompt")

    parser.add_argument('--emb-file', type=str, default='embeddings.pkl', help="Name of the file used to save embeddings for the fine-grained retrieval-based memory module")
    parser.add_argument('--reflection', action="store_true", help="Set flag to use reflection module at the end of each session and include in the conversation generation prompt for context")
    
    # 场景相关参数
    parser.add_argument('--scenario', type=str, default='male_leave_work', 
                        choices=['male_leave_work', 'elderly_outdoor', 'child_return', 'family_return', 
                                 'visitor_arrival', 'all_leave_arm', 'anomaly_detection'],
                        help="指定对话场景类型，默认为 male_leave_work (男主人上班离家)")
    parser.add_argument('--scenario-file', type=str, default='./data/scenarios/scenarios.json',
                        help="场景配置文件路径，默认为 ./data/scenarios/scenarios.json")
    
    # 设备相关参数
    parser.add_argument('--device', action="store_true", 
                        help="Set flag to select relevant devices based on user persona and scenario")
    parser.add_argument('--device-file', type=str, default='./data/devices/home_devices.json',
                        help="家庭设备库文件路径，默认为 ./data/devices/home_devices.json")
    parser.add_argument('--device-events', action="store_true",
                        help="Set flag to generate device events based on dialogue and scenario")
    parser.add_argument('--device-trajectory', action="store_true",
                        help="Set flag to generate device operation trajectory with tool calls")

    args = parser.parse_args()
    return args


def main():
    """
    主流程函数。
    
    执行多会话对话生成的完整流程：
    1. 生成/加载人物角色
    2. 选择相关设备
    3. 生成事件图
    4. 生成多会话对话
    5. 生成摘要
    """
    args = parse_args()
    
    # 创建输出目录
    if not os.path.exists(args.out_dir):
        os.makedirs(args.out_dir)
    
    args.agent_a_file = os.path.join(args.out_dir, 'agent_a.json')
    args.agent_b_file = os.path.join(args.out_dir, 'agent_b.json')

    
    # Step 1: Get personalities for the agents; get a randomly selected sample from the MSC dataset and expand the few-liner personas into detailed personas.
    if args.persona:
        agent_a, agent_b = get_msc_persona(args)
        if agent_a is not None and agent_b is not None:
            save_agents([agent_a, agent_b], args)

    # Step 1.1: Get device records for the agents
    if args.device:
        agent_a, agent_b = load_agents(args)
        user_devices = agent_b.get('devices', {})  # 初始化 user_devices
        
        # 根据用户特点挑选相关设备
        if agent_b and 'persona_summary' in agent_b:
            # 如果已存在设备列表且不需要覆盖，则跳过
            if 'devices' in agent_b and agent_b['devices'] and not args.overwrite_persona:
                logging.info("Devices already exist in agent_b, skipping device selection")
            else:
                user_persona = agent_b['persona_summary']
                scenario = args.scenario if hasattr(args, 'scenario') else 'male_leave_work'
                
                # 加载场景描述
                scenario_desc = scenario
                try:
                    with open(args.scenario_file, 'r', encoding='utf-8') as f:
                        scenarios_data = json.load(f)
                    scenario_info = scenarios_data.get('scenarios', {}).get(scenario, {})
                    scenario_desc = scenario_info.get('description', scenario)
                except Exception as e:
                    logging.warning(f"Failed to load scenario description: {e}")
                
                # 挑选与用户相关的设备（使用模型智能选择）
                user_devices = select_devices_for_user(user_persona, scenario, scenario_desc, args.device_file)
                
                # 记录到 agent_b 中
                agent_b['devices'] = user_devices
            
            # AI助手也需要知道可用的设备列表
            if 'devices' not in agent_a:
                agent_a['devices'] = {}
            
            # 保存更新
            save_agents([agent_a, agent_b], args)
            logging.info(f"Selected {len(user_devices)} devices for user: {list(user_devices.keys())}")

    # Step 2: check if events exist; if not, generate event graphs for each of the agents 
    if args.events:

        agent_a, agent_b = load_agents(args)

        if ('graph' in agent_a and 'graph' in agent_b) and not args.overwrite_events:
            pass
        else:
            # if 'session_1_date_time' not in agent_a:
            start_date = get_random_date() # select a random date in 2022-2023
            end_date = start_date + timedelta(days=args.num_days)
            start_date = dateObj2Str(start_date)
            end_date = dateObj2Str(end_date)
            agent_a['events_start_date'] = start_date
            agent_b['events_start_date'] = start_date
            logging.info(f"Generating a random start date:{start_date} and end date:{end_date} for the conversation")
            save_agents([agent_a, agent_b], args)

            
            agent_a_events = []  # AI助手不产生事件，保留为空列表
            agent_b_events = []

            logging.info("Generating events for Agent B (user)")
            trials = 0
            while len(agent_b_events) < args.num_events:
                logging.info("(Re)trying to generate events with dense causal connections: trial %s" % trials)
                agent_b_events = get_events(agent_b, start_date, end_date, args)
                agent_b["graph"] = agent_b_events
            save_agents([agent_a, agent_b], args)

        # make sure keys are all lower case
        # agent_a 是 AI助手，不产生事件，确保 graph 字段存在
        if 'graph' not in agent_a:
            agent_a['graph'] = []
        agent_a_events = agent_a['graph']
        agent_a_events = [{k.lower(): v for k,v in e.items()} for e in agent_a_events]
        agent_a["graph"] = agent_a_events
        agent_b_events = agent_b['graph']
        agent_b_events = [{k.lower(): v for k,v in e.items()} for e in agent_b_events]
        agent_b["graph"] = agent_b_events
        save_agents([agent_a, agent_b], args)

    # Step 3: generate conversations session by session
    if args.session:

        agent_a, agent_b = load_agents(args)

        # 加载场景配置
        scenario_config = None
        try:
            with open(args.scenario_file, 'r', encoding='utf-8') as f:
                scenarios_data = json.load(f)
            scenario_config = scenarios_data.get('scenarios', {}).get(args.scenario, {})
        except Exception as e:
            logging.warning(f"Failed to load scenario config: {e}")

        # 初始化会话日期
        if 'session_1_date_time' not in agent_b:
            # 使用场景配置的时间范围生成随机时间
            session_time = get_random_time(scenario_config)
            session_date = get_session_date((agent_a['graph'], agent_b['graph']), args)
            session_date_time = datetimeObj2Str(datetime(session_date.year, session_date.month, session_date.day) + session_time)
            agent_a['session_1_date_time'] = session_date_time
            agent_b['session_1_date_time'] = session_date_time
            save_agents([agent_a, agent_b], args)

        # 生成多会话对话
        for sess_id in range(args.start_session, args.num_sessions+1):

            # 检查是否已存在该会话
            if 'session_%s' % sess_id in agent_b and not args.overwrite_session:
                logging.info("Session %s already exists in agent_b, skipping" % sess_id)
                continue

            logging.info("Generating session %s" % sess_id)

            # 获取当前和前一个会话的日期时间
            curr_date_time_string = agent_b['session_%s_date_time' % sess_id]
            prev_date_time_string = agent_b['session_%s_date_time' % (sess_id-1)] if sess_id > 1 else ''

            # 分配事件到当前会话
            if args.events:
                curr_date = datetime.strptime(curr_date_time_string.split(' on ')[1], "%d %B, %Y")
                prev_date = datetime.strptime(prev_date_time_string.split(' on ')[1], "%d %B, %Y") if sess_id > 1 else None
                agent_b['events_session_%s' % sess_id] = get_relevant_events(agent_b['graph'], curr_date, prev_date)

            # 生成会话对话
            session = get_session(
                agent_a, agent_b, args, 
                prev_date_time_string=prev_date_time_string,
                curr_date_time_string=curr_date_time_string,
                curr_sess_id=sess_id,
                reflection=args.reflection
            )

            # 保存会话
            agent_a['session_%s' % sess_id] = session
            agent_b['session_%s' % sess_id] = session
            save_agents([agent_a, agent_b], args)

            # 生成会话摘要
            if args.summary:
                curr_date = datetime.strptime(curr_date_time_string.split(' on ')[1], "%d %B, %Y")
                previous_summary = agent_b.get('session_%s_summary' % (sess_id-1), '')
                summary = get_session_summary(session, agent_a, agent_b, curr_date, previous_summary)
                agent_a['session_%s_summary' % sess_id] = summary
                agent_b['session_%s_summary' % sess_id] = summary
                save_agents([agent_a, agent_b], args)

            # 保存嵌入向量
            if args.reflection:
                save_embeddings([agent_a, agent_b], args, sess_id)
                save_agents([agent_a, agent_b], args)

            # 计算下一个会话的日期时间
            if sess_id < args.num_sessions:
                session_time = get_random_time(scenario_config)
                session_date = get_session_date((agent_a['graph'], agent_b['graph']), args, 
                                               prev_date=datetime.strptime(curr_date_time_string.split(' on ')[1], "%d %B, %Y"))
                session_date_time = datetimeObj2Str(datetime(session_date.year, session_date.month, session_date.day) + session_time)
                agent_a['session_%s_date_time' % (sess_id+1)] = session_date_time
                agent_b['session_%s_date_time' % (sess_id+1)] = session_date_time
                save_agents([agent_a, agent_b], args)

        # 转换为HTML格式
        html_outfile = os.path.join(args.out_dir, 'conversation.html')
        convert_to_chat_html(agent_a, agent_b, html_outfile)

    # Step 4: 生成场景指令设备操作行为轨迹
    if args.device_trajectory:
        logging.info("Generating device operation trajectory with tool calls...")
        
        # 加载 agent 数据
        agent_a, agent_b = load_agents(args)
        
        # 检查是否已有设备
        if not agent_b.get('devices'):
            logging.warning("No devices found in agent_b. Please run with --device flag first.")
        else:
            # 检查是否已生成过轨迹（存在 session_1_device_trajectory）
            if 'session_1_device_trajectory' in agent_b and not args.overwrite_session:
                logging.info("Device trajectory already exists in agent_b, skipping. Use --overwrite-session to regenerate.")
            else:
                # 生成所有会话的设备操作轨迹
                device_trajectories = generate_all_device_trajectories([agent_a, agent_b], args)
                
                if device_trajectories:
                    # 保存设备轨迹到 agent 对象
                    for sess_id, trajectory in device_trajectories.items():
                        agent_b[f'session_{sess_id}_device_trajectory'] = trajectory
                    
                    # 保存更新到 agent 对象
                    save_agents([agent_a, agent_b], args)
                    
                    # 输出摘要
                    logging.info(f"Device trajectory generation complete for {len(device_trajectories)} sessions")
                else:
                    logging.warning("No device trajectories were generated.")

    # Step 5: 根据场景以及对话的内容生成设备events记录
    if args.device_events:
        logging.info("Generating device events based on dialogue and scenario...")
        
        # 加载 agent 数据
        agent_a, agent_b = load_agents(args)
        
        # 检查是否已有设备
        if not agent_b.get('devices'):
            logging.warning("No devices found in agent_b. Please run with --device flag first.")
        else:
            # 检查是否已生成过设备事件（存在 session_1_device_events）
            if 'session_1_device_events' in agent_b and not args.overwrite_events:
                logging.info("Device events already exist in agent_b, skipping. Use --overwrite-events to regenerate.")
            else:
                # 生成所有会话的设备事件
                device_events = generate_all_device_events([agent_a, agent_b], args)
                
                if device_events and device_events.get('sessions'):
                    # 保存设备事件到文件
                    save_device_events([agent_a, agent_b], args, device_events)
                    
                    # 保存更新到 agent 对象
                    save_agents([agent_a, agent_b], args)
                    
                    # 输出摘要
                    summary = get_device_events_summary(device_events)
                    logging.info(f"Device events generation complete:\n{summary}")
                else:
                    logging.warning("No device events were generated.")



if __name__ == '__main__':
    main()