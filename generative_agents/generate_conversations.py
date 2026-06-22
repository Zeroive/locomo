"""
多会话对话生成主程序。

生成AI助手与用户之间的多轮对话，支持场景化配置和设备选择。
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import logging
import argparse
import os, json, random, re
from datetime import date, timedelta, datetime
from multiprocessing import Pool

# 导入重构后的模块
from generative_agents.file_utils import save_agents, load_agents
from generative_agents.time_utils import get_random_time, get_random_date, datetimeObj2Str, dateObj2Str, get_session_date
from generative_agents.device_utils import select_devices_for_user
from generative_agents.device_events_utils import generate_all_device_events, save_device_events, get_device_events_summary
from generative_agents.device_trajectory_utils import generate_all_device_trajectories
from generative_agents.session_utils import get_session, get_session_summary, get_relevant_events
from generative_agents.conversation_utils import get_msc_persona, get_datetime_string
from generative_agents.event_utils import get_events
from generative_agents.memory_utils import get_session_facts, save_embeddings
from generative_agents.html_utils import convert_to_chat_html
from generative_agents.qa_utils import generate_qa_pairs
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
                        help="指定对话场景类型，默认为 male_leave_work\n"
                             "场景说明：\n"
                             "  male_leave_work    - 男主人上班离家：早上出门上班前与AI助手的对话\n"
                             "  elderly_outdoor     - 老人独自外出：老人准备外出活动前与AI助手的对话\n"
                             "  child_return        - 小孩放学回家：小孩放学回家后与AI助手的对话\n"
                             "  family_return       - 家庭成员下班回家：家庭成员下班回家后与AI助手的对话\n"
                             "  visitor_arrival     - 访客到家：访客到达家中时与AI助手的对话\n"
                             "  all_leave_arm       - 全员离家布防：全员离家时启动安防模式的对话\n"
                             "  anomaly_detection   - 异常活动检测：检测到异常活动时AI助手与用户的对话")
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
    parser.add_argument('--qa-pairs', action="store_true",
                        help="Set flag to generate QA pairs from session facts")

    # 并发执行相关参数
    parser.add_argument('--parallel-runs', type=int, default=1, 
                        help="Number of parallel conversation runs to execute (default: 1)")
    parser.add_argument('--max-workers', type=int, default=4, 
                        help="Maximum number of worker processes for parallel execution (default: 4)")
    
    args = parser.parse_args()
    return args


def run_conversation(run_args):
    """
    执行单次对话生成任务（用于并发执行）
    
    Args:
        run_args: 包含运行参数的字典，包括 run_index, base_out_dir, 和原始 args 对象
    """
    run_index = run_args['run_index']
    base_out_dir = run_args['base_out_dir']
    args = run_args['args']
    
    # 创建当前运行的输出目录
    run_out_dir = os.path.join(base_out_dir, str(run_index))
    if not os.path.exists(run_out_dir):
        os.makedirs(run_out_dir)
    
    # 创建 args 的副本，避免并发执行时共享对象导致问题
    import copy
    local_args = copy.deepcopy(args)
    
    # 更新 local_args 的输出目录
    local_args.out_dir = run_out_dir
    local_args.agent_a_file = os.path.join(run_out_dir, 'agent_a.json')
    local_args.agent_b_file = os.path.join(run_out_dir, 'agent_b.json')
    
    logging.info(f"Starting conversation run {run_index} in directory: {run_out_dir}")
    
    try:
        # 调用原始的对话生成逻辑
        generate_conversation(local_args)
        logging.info(f"Conversation run {run_index} completed successfully")
        return (run_index, True, None)
    except Exception as e:
        logging.error(f"Conversation run {run_index} failed: {str(e)}")
        return (run_index, False, str(e))


def generate_conversation(args):
    """
    执行多会话对话生成的完整流程（抽取出来的核心逻辑）
    
    Args:
        args: 命令行参数对象
    """
    # Step 1: Get personalities for the agents; get a randomly selected sample from the MSC dataset and expand the few-liner personas into detailed personas.
    if args.persona:
        # 加载场景配置（如果有），用于生成符合场景的人物角色
        scenario_info = None
        try:
            with open(args.scenario_file, 'r', encoding='utf-8') as f:
                scenarios_data = json.load(f)
            scenario_info = scenarios_data.get('scenarios', {}).get(args.scenario, None)
        except Exception as e:
            logging.warning(f"Failed to load scenario config for persona generation: {e}")
        
        agent_a, agent_b = get_msc_persona(args, scenario_info)
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

            # 生成会话事实（每轮都生成，不受 reflection 参数控制）
            if 'session_%s_facts' % sess_id not in agent_b or args.overwrite_session:
                facts = get_session_facts(args, agent_a, agent_b, sess_id)
                agent_a['session_%s_facts' % sess_id] = facts
                agent_b['session_%s_facts' % sess_id] = facts
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

    # Step 6: 生成QA对
    if args.qa_pairs:
        logging.info("Generating QA pairs...")
        
        # 加载 agent 数据
        try:
            agent_a, agent_b = load_agents(args)
        except Exception as e:
            logging.error(f"Failed to load agents: {e}")
            return
        
        # 检查 agent 是否加载成功
        if agent_a is None or agent_b is None:
            logging.error("Failed to load agents: agent_a or agent_b is None")
            return
        
        # 检查是否已有会话事实
        has_facts = any(f'session_{i}_facts' in agent_a for i in range(1, args.num_sessions + 1))
        if not has_facts:
            logging.warning("No session facts found. Please run with session generation first.")
        else:
            # 检查是否已生成过QA对
            qa_path = os.path.join(args.out_dir, 'qa_pairs.json')
            if os.path.exists(qa_path) and not args.overwrite_session:
                logging.info(f"QA pairs already exist at {qa_path}, skipping. Use --overwrite-session to regenerate.")
            else:
                # 生成QA对
                generate_qa_pairs(agent_a, agent_b, args)


def main():
    """
    主流程函数。
    
    支持并发执行多轮对话生成。
    """
    args = parse_args()
    
    # 创建基础输出目录
    if not os.path.exists(args.out_dir):
        os.makedirs(args.out_dir)
    
    # 如果需要并发执行多轮对话
    if args.parallel_runs > 1:
        logging.info(f"Starting {args.parallel_runs} parallel conversation runs...")
        
        # 准备任务参数
        tasks = []
        for i in range(1, args.parallel_runs + 1):
            task_args = {
                'run_index': i,
                'base_out_dir': args.out_dir,
                'args': args
            }
            tasks.append(task_args)
        
        # 使用进程池并发执行
        with Pool(processes=min(args.parallel_runs, args.max_workers)) as pool:
            results = pool.map(run_conversation, tasks)
        
        # 汇总结果
        success_count = sum(1 for _, success, _ in results if success)
        fail_count = args.parallel_runs - success_count
        
        logging.info(f"Parallel execution complete. Success: {success_count}, Failed: {fail_count}")
        
        # 输出失败的运行信息
        for run_index, success, error in results:
            if not success:
                logging.error(f"Run {run_index} failed: {error}")
    
    else:
        # 单轮执行，直接调用生成函数
        args.agent_a_file = os.path.join(args.out_dir, 'agent_a.json')
        args.agent_b_file = os.path.join(args.out_dir, 'agent_b.json')
        generate_conversation(args)


if __name__ == '__main__':
    main()