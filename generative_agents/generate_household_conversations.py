"""
Generate household multi-user conversations with an AI assistant.

This script follows the original staged generation flow:
persona/household profile -> event memory graph -> sessions grounded in events
and time -> session facts -> QA pairs.
"""

import argparse
import copy
import json
import logging
import os
import sys
from datetime import datetime
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from generative_agents.household_event_utils import (
    generate_household_events,
    get_household_session_date,
    get_relevant_household_events,
)
from generative_agents.household_qa_utils import generate_household_qa_pairs
from generative_agents.household_session_utils import (
    extract_household_session_facts,
    generate_household_session,
    summarize_session,
)
from generative_agents.household_utils import (
    HOUSEHOLD_TYPES,
    create_assistant,
    load_json,
    sample_household_profile,
    save_json,
    validate_household,
)
from generative_agents.time_utils import datetimeObj2Str, get_random_time


logging.basicConfig(level=logging.INFO)


DEFAULT_PERSONA_SOURCE = str(Path(__file__).parent.parent / "data" / "msc_speakers_single.json")


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", required=True, type=str)
    parser.add_argument("--prompt-dir", required=True, type=str)
    parser.add_argument("--persona-source", type=str, default=DEFAULT_PERSONA_SOURCE)
    parser.add_argument("--household-type", type=str, default="nuclear_family", choices=HOUSEHOLD_TYPES)
    parser.add_argument("--num-households", type=int, default=1)
    parser.add_argument("--num-sessions", type=int, default=5)
    parser.add_argument("--num-events", type=int, default=10)
    parser.add_argument("--num-days", type=int, default=60)
    parser.add_argument("--num-events-per-session", type=int, default=2)
    parser.add_argument("--max-turns-per-session", type=int, default=8)
    parser.add_argument("--with-pet", "--with-pets", dest="with_pet", action="store_true")
    parser.add_argument("--persona", action="store_true")
    parser.add_argument("--events", action="store_true")
    parser.add_argument("--session", action="store_true")
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--reflection", action="store_true")
    parser.add_argument("--qa-pairs", action="store_true")
    parser.add_argument("--no-llm", action="store_true", help="Disable LLM generation and use deterministic fallback templates")
    parser.add_argument("--overwrite-persona", action="store_true")
    parser.add_argument("--overwrite-events", action="store_true")
    parser.add_argument("--overwrite-session", action="store_true")
    parser.add_argument("--parallel-runs", type=int, default=1)
    parser.add_argument("--max-workers", type=int, default=4)
    return parser.parse_args()


def household_profile_path(out_dir):
    return os.path.join(out_dir, "household_profile.json")


def agent_a_path(out_dir):
    return os.path.join(out_dir, "agent_a.json")


def sessions_path(out_dir):
    return os.path.join(out_dir, "sessions.json")


def members_dir(out_dir):
    return os.path.join(out_dir, "members")


def load_profile(out_dir):
    return load_json(household_profile_path(out_dir))


def save_profile(profile, out_dir):
    validate_household(profile)
    save_json(profile, household_profile_path(out_dir))
    logging.info("Saved household profile: %s", household_profile_path(out_dir))


def save_members(profile, out_dir):
    target_dir = members_dir(out_dir)
    os.makedirs(target_dir, exist_ok=True)
    for member in profile.get("members", []):
        save_json(member, os.path.join(target_dir, f"{member['person_id']}.json"))
    logging.info("Saved %s member files under %s", len(profile.get("members", [])), target_dir)


def ensure_assistant(out_dir, overwrite=False):
    path = agent_a_path(out_dir)
    if os.path.exists(path) and not overwrite:
        logging.info("Loading existing assistant profile: %s", path)
        return load_json(path)
    assistant = create_assistant()
    save_json(assistant, path)
    logging.info("Saved assistant profile: %s", path)
    return assistant


def generate_persona_step(args):
    profile_path = household_profile_path(args.out_dir)
    if os.path.exists(profile_path) and not args.overwrite_persona:
        logging.info("household_profile.json already exists, skipping persona step")
        return load_profile(args.out_dir)

    logging.info(
        "Starting persona/profile step: household_type=%s, with_pet=%s, use_llm=%s",
        args.household_type,
        args.with_pet,
        not args.no_llm,
    )
    profile = sample_household_profile(
        household_type=args.household_type,
        persona_source=args.persona_source,
        family_id="family_001",
        with_pet=args.with_pet,
        use_llm=not args.no_llm,
    )
    save_profile(profile, args.out_dir)
    save_members(profile, args.out_dir)
    ensure_assistant(args.out_dir, overwrite=args.overwrite_persona)
    logging.info(
        "Generated household profile: family_id=%s, members=%s, pets=%s",
        profile["family"]["family_id"],
        len(profile["members"]),
        len(profile.get("pets", [])),
    )
    return profile


def generate_events_step(args, profile):
    if profile.get("graph") and not args.overwrite_events:
        logging.info("Household events already exist, skipping events step")
        return profile
    logging.info(
        "Starting events step: num_events=%s, num_days=%s, use_llm=%s",
        args.num_events,
        args.num_days,
        not args.no_llm,
    )
    generate_household_events(profile, args.num_events, num_days=args.num_days, use_llm=not args.no_llm)
    save_profile(profile, args.out_dir)
    logging.info("Generated %s household events", len(profile.get("graph", [])))
    for event in profile.get("graph", []):
        logging.info(
            "Event %s [%s] %s participants=%s date=%s",
            event.get("id"),
            event.get("scenario_type"),
            event.get("sub-event"),
            event.get("participants"),
            event.get("date"),
        )
    return profile


def ensure_session_dates(profile, args, sess_id, prev_date_time_string=""):
    key = f"session_{sess_id}_date_time"
    if key in profile and not args.overwrite_session:
        return profile[key]

    prev_date = None
    if prev_date_time_string:
        prev_date = datetime.strptime(prev_date_time_string.split(" on ")[1], "%d %B, %Y")
    session_date = get_household_session_date(
        profile.get("graph", []),
        num_events_per_session=args.num_events_per_session,
        prev_date=prev_date,
    )
    session_time = get_random_time({"time_range": {"start_hour": 9, "end_hour": 21}})
    date_time = datetimeObj2Str(datetime(session_date.year, session_date.month, session_date.day) + session_time)
    profile[key] = date_time
    logging.info("Assigned %s=%s", key, date_time)
    return date_time


def generate_session_step(args, profile):
    assistant = ensure_assistant(args.out_dir)
    if not profile.get("graph"):
        logging.warning("No household events found; sessions will be generated without event grounding")

    logging.info(
        "Starting session step: num_sessions=%s, max_turns=%s, use_llm=%s",
        args.num_sessions,
        args.max_turns_per_session,
        not args.no_llm,
    )
    profile["sessions"] = [] if args.overwrite_session else profile.get("sessions", [])
    existing_session_ids = {session.get("session_id") for session in profile.get("sessions", [])}

    prev_date_time_string = ""
    for sess_id in range(1, args.num_sessions + 1):
        if sess_id in existing_session_ids and not args.overwrite_session:
            prev_date_time_string = profile.get(f"session_{sess_id}_date_time", prev_date_time_string)
            continue

        curr_date_time_string = ensure_session_dates(profile, args, sess_id, prev_date_time_string)
        curr_date = datetime.strptime(curr_date_time_string.split(" on ")[1], "%d %B, %Y")
        prev_date = datetime.strptime(prev_date_time_string.split(" on ")[1], "%d %B, %Y") if prev_date_time_string else None

        profile[f"events_session_{sess_id}"] = get_relevant_household_events(profile.get("graph", []), curr_date, prev_date)
        logging.info(
            "Session %s relevant events: %s",
            sess_id,
            [event.get("id") for event in profile[f"events_session_{sess_id}"]],
        )
        previous_summary = profile.get(f"session_{sess_id - 1}_summary", "") if sess_id > 1 else ""
        session = generate_household_session(
            profile=profile,
            assistant=assistant,
            sess_id=sess_id,
            curr_date_time=curr_date_time_string,
            prev_date_time=prev_date_time_string,
            previous_summary=previous_summary,
            max_turns=args.max_turns_per_session,
            use_llm=not args.no_llm,
        )
        profile["sessions"].append(session)
        profile[f"session_{sess_id}"] = session["turns"]
        logging.info(
            "Session %s generated: current_user=%s(%s), turns=%s, mode=%s",
            sess_id,
            session["current_user_name"],
            session["current_user_id"],
            len(session["turns"]),
            session.get("turn_generation_mode"),
        )
        profile[f"session_{sess_id}_facts"] = extract_household_session_facts(profile, session, use_llm=not args.no_llm)
        logging.info(
            "Session %s facts extracted for speakers=%s",
            sess_id,
            list(profile[f"session_{sess_id}_facts"].keys()) if isinstance(profile[f"session_{sess_id}_facts"], dict) else type(profile[f"session_{sess_id}_facts"]),
        )
        if args.summary:
            profile[f"session_{sess_id}_summary"] = summarize_session(session)
            logging.info("Session %s summary: %s", sess_id, profile[f"session_{sess_id}_summary"])

        prev_date_time_string = curr_date_time_string
        logging.info("Generated household session %s for %s", sess_id, session["current_user_name"])

    save_profile(profile, args.out_dir)
    save_json(profile.get("sessions", []), sessions_path(args.out_dir))
    logging.info("Saved sessions file: %s", sessions_path(args.out_dir))
    return profile


def generate_qa_step(args, profile):
    if not profile.get("sessions"):
        logging.warning("No sessions found. Please run with --session before --qa-pairs.")
        return None
    logging.info("Starting QA step: sessions=%s, use_llm=%s", len(profile.get("sessions", [])), not args.no_llm)
    output = generate_household_qa_pairs(profile, args.out_dir, use_llm=not args.no_llm)
    if output:
        logging.info("Generated QA pairs: %s", len(output.get("QA", [])))
        logging.info("Saved QA file: %s", os.path.join(args.out_dir, "qa_pairs.json"))
    return output


def generate_household_conversation(args):
    os.makedirs(args.out_dir, exist_ok=True)
    logging.info(
        "Household generation started: out_dir=%s, household_type=%s, persona=%s, events=%s, session=%s, qa_pairs=%s, no_llm=%s",
        args.out_dir,
        args.household_type,
        args.persona,
        args.events,
        args.session,
        args.qa_pairs,
        args.no_llm,
    )

    profile = load_profile(args.out_dir) if os.path.exists(household_profile_path(args.out_dir)) else None
    if profile:
        logging.info("Loaded existing household profile: %s", household_profile_path(args.out_dir))

    if args.persona or profile is None:
        profile = generate_persona_step(args)
    else:
        ensure_assistant(args.out_dir)

    if args.events:
        profile = generate_events_step(args, profile)

    if args.session:
        profile = generate_session_step(args, profile)

    if args.qa_pairs:
        generate_qa_step(args, profile)

    logging.info("Household generation finished: out_dir=%s", args.out_dir)


def run_one(run_args):
    run_index = run_args["run_index"]
    base_args = run_args["args"]
    args = copy.deepcopy(base_args)
    args.out_dir = os.path.join(base_args.out_dir, str(run_index))
    try:
        generate_household_conversation(args)
        return run_index, True, None
    except Exception as exc:
        logging.exception("Household generation run %s failed", run_index)
        return run_index, False, str(exc)


def main():
    args = parse_args()
    logging.info("Parsed args: %s", vars(args))
    if args.num_households > 1 or args.parallel_runs > 1:
        total = max(args.num_households, args.parallel_runs)
        tasks = [{"run_index": idx, "args": args} for idx in range(1, total + 1)]
        with Pool(processes=min(total, args.max_workers)) as pool:
            results = pool.map(run_one, tasks)
        failed = [item for item in results if not item[1]]
        if failed:
            raise RuntimeError(f"{len(failed)} household generation runs failed: {failed}")
    else:
        generate_household_conversation(args)


if __name__ == "__main__":
    main()
