"""家庭画像上下文格式化服务。"""

from generative_agents.device_event_domain import PERSON_ID_MAPPING

def format_members_info(household_profile, person_ids):
    """
    格式化家庭成员信息。
    
    Args:
        household_profile: 家庭画像
        person_ids: 人员ID列表
        
    Returns:
        str: 格式化的家庭成员信息字符串
    """
    members = household_profile.get('members', {})
    info_lines = []
    member_map = {}
    if isinstance(members, dict):
        member_map = members
    elif isinstance(members, list):
        for member in members:
            if isinstance(member, dict):
                member_id = member.get('person_id') or member.get('id') or member.get('name')
                if member_id:
                    member_map[member_id] = member
    
    for person_id in person_ids:
        if person_id in member_map:
            member = member_map[person_id]
            name = member.get('name', person_id)
            role = member.get('role') or member.get('family_role') or member.get('family_role_label') or ''
            age = member.get('age', '')
            info_lines.append(f"- {person_id}: {name}, 角色: {role}, 年龄: {age}")
        else:
            # 使用默认映射
            if person_id in PERSON_ID_MAPPING:
                mapping = PERSON_ID_MAPPING[person_id]
                info_lines.append(f"- {person_id}: {mapping['name']}, 角色: {mapping['role']}, 年龄范围: {mapping['age_range']}")
    
    return '\n'.join(info_lines) if info_lines else "- dad: 父亲, 角色: 男主人, 年龄范围: 35-50\n- mom: 母亲, 角色: 女主人, 年龄范围: 35-50"


def format_relations_info(household_profile):
    """
    格式化家庭成员关系。
    """
    relations = household_profile.get('relations', [])
    if isinstance(relations, dict):
        relation_items = []
        for source, targets in relations.items():
            if isinstance(targets, dict):
                for target, relation_type in targets.items():
                    relation_items.append(f"- {source} --{relation_type}--> {target}")
            elif isinstance(targets, list):
                for item in targets:
                    relation_items.append(f"- {source}: {item}")
        return '\n'.join(relation_items) if relation_items else "未提供显式家庭关系"
    if isinstance(relations, list):
        lines = []
        for relation in relations:
            if isinstance(relation, dict):
                source = relation.get('from') or relation.get('source') or relation.get('subject') or ''
                target = relation.get('to') or relation.get('target') or relation.get('object') or ''
                relation_type = relation.get('type') or relation.get('relation') or ''
                if source or target or relation_type:
                    lines.append(f"- {source} --{relation_type}--> {target}")
            else:
                lines.append(f"- {relation}")
        return '\n'.join(lines) if lines else "未提供显式家庭关系"
    return "未提供显式家庭关系"


def get_person_ids_from_household(household_profile):
    """
    从家庭画像中提取人员ID列表。
    
    Args:
        household_profile: 家庭画像字典
        
    Returns:
        list: 人员ID列表
    """
    # 从家庭画像获取成员
    members = household_profile.get('members', {})
    person_ids = []
    
    # 如果有家庭成员定义，使用家庭画像中的成员
    if members:
        if isinstance(members, dict):
            for member_id, member_info in members.items():
                person_ids.append(member_id)
        elif isinstance(members, list):
            for member in members:
                if isinstance(member, dict):
                    person_ids.append(member.get('person_id') or member.get('id') or member.get('name'))
                else:
                    person_ids.append(str(member))
            person_ids = [person_id for person_id in person_ids if person_id]
    else:
        # 使用默认的人员映射
        person_ids = list(PERSON_ID_MAPPING.keys())
    
    return person_ids
