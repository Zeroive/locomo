"""
测试工具定义一致性
验证 tools_schema.json 和 home_devices.json 中的工具定义是否匹配
"""
import json
from pathlib import Path

# 文件路径
TOOLS_SCHEMA_PATH = Path("/Users/zhouyuchao/Workplace/MemData/locomo/data/devices/tools_schema.json")
HOME_DEVICES_PATH = Path("/Users/zhouyuchao/Workplace/MemData/locomo/data/devices/home_devices.json")


def load_json(path: Path) -> dict:
    """加载 JSON 文件"""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def test_tools_schema_structure():
    """测试 tools_schema.json 结构是否正确"""
    schema = load_json(TOOLS_SCHEMA_PATH)

    assert "global_tools" in schema, "缺少 global_tools 字段"
    assert "device_tools" in schema, "缺少 device_tools 字段"

    # 验证全局工具
    for tool_name, tool_def in schema["global_tools"].items():
        assert "tool_name" in tool_def
        assert "category" in tool_def
        assert "description" in tool_def
        assert "parameters" in tool_def
        assert "risk_level" in tool_def

    # 验证设备工具
    for device_id, tools in schema["device_tools"].items():
        assert isinstance(tools, dict), f"{device_id} 的工具应该是字典类型"
        for action, tool_def in tools.items():
            assert "tool_name" in tool_def
            assert "category" in tool_def
            assert "description" in tool_def
            assert "parameters" in tool_def

    print("✓ tools_schema.json 结构验证通过")


def get_all_tools_in_schema(schema: dict) -> set:
    """获取 tools_schema.json 中的所有工具名"""
    tools = set()

    # 全局工具
    for tool_def in schema["global_tools"].values():
        tools.add(tool_def["tool_name"])

    # 设备工具
    for device_tools in schema["device_tools"].values():
        for tool_def in device_tools.values():
            tools.add(tool_def["tool_name"])

    return tools


def get_all_tools_in_home_devices(devices: dict) -> set:
    """获取 home_devices.json 中声明的所有工具名"""
    tools = set()

    # device_categories 是设备类别字典
    device_categories = devices.get("device_categories", {})
    for category_name, category_data in device_categories.items():
        if not isinstance(category_data, dict) or "devices" not in category_data:
            continue

        for device_data in category_data["devices"].values():
            if "tools" in device_data:
                for tool in device_data["tools"]:
                    tools.add(tool)

    return tools


def test_schema_tools_in_home_devices():
    """测试 tools_schema.json 中的设备工具都在 home_devices.json 中有声明（全局工具除外）"""
    schema = load_json(TOOLS_SCHEMA_PATH)
    devices = load_json(HOME_DEVICES_PATH)

    schema_device_tools = set()
    for device_tools in schema["device_tools"].values():
        for tool_def in device_tools.values():
            schema_device_tools.add(tool_def["tool_name"])

    device_tools = get_all_tools_in_home_devices(devices)

    # 找出 schema 中有但 devices 中没有的设备工具（不包括全局工具）
    missing_in_devices = schema_device_tools - device_tools

    if missing_in_devices:
        print("\n✗ 以下设备工具在 schema 中定义但未在 home_devices.json 中声明:")
        for tool in sorted(missing_in_devices):
            print(f"  - {tool}")
        raise AssertionError(f"有 {len(missing_in_devices)} 个设备工具未在 home_devices.json 中声明")
    else:
        print(f"✓ 所有 schema 设备工具都在 home_devices.json 中声明 ({len(schema_device_tools)} 个)")


def test_home_devices_tools_in_schema():
    """测试 home_devices.json 中声明的工具都在 tools_schema.json 中有定义"""
    schema = load_json(TOOLS_SCHEMA_PATH)
    devices = load_json(HOME_DEVICES_PATH)

    schema_tools = get_all_tools_in_schema(schema)
    device_tools = get_all_tools_in_home_devices(devices)

    # 找出 devices 中有但 schema 中没有的工具
    missing_in_schema = device_tools - schema_tools

    if missing_in_schema:
        print("\n✗ 以下工具在 home_devices.json 中声明但未在 tools_schema.json 中定义:")
        for tool in sorted(missing_in_schema):
            print(f"  - {tool}")
        raise AssertionError(f"有 {len(missing_in_schema)} 个工具未在 tools_schema.json 中定义")
    else:
        print(f"✓ 所有 home_devices.json 工具都在 tools_schema.json 中定义 ({len(device_tools)} 个)")


def test_device_has_schema():
    """测试 home_devices.json 中的每个设备都有对应的 schema 定义"""
    schema = load_json(TOOLS_SCHEMA_PATH)
    devices = load_json(HOME_DEVICES_PATH)

    missing_schemas = []

    device_categories = devices.get("device_categories", {})
    for category_name, category_data in device_categories.items():
        if not isinstance(category_data, dict) or "devices" not in category_data:
            continue

        for device_id, device_data in category_data["devices"].items():
            if "tools" not in device_data or not device_data["tools"]:
                continue

            if device_id not in schema["device_tools"]:
                missing_schemas.append(device_id)

    if missing_schemas:
        print("\n✗ 以下设备在 home_devices.json 中有 tools 但在 schema 中无定义:")
        for device_id in sorted(missing_schemas):
            print(f"  - {device_id}")
        raise AssertionError(f"有 {len(missing_schemas)} 个设备缺少 schema 定义")
    else:
        print("✓ 所有有 tools 的设备都有对应的 schema 定义")


def test_tool_action_match():
    """测试 home_devices.json 中的 tool 名称与 schema 中的 action 名称匹配"""
    schema = load_json(TOOLS_SCHEMA_PATH)
    devices = load_json(HOME_DEVICES_PATH)

    mismatches = []

    device_categories = devices.get("device_categories", {})
    for category_name, category_data in device_categories.items():
        if not isinstance(category_data, dict) or "devices" not in category_data:
            continue

        for device_id, device_data in category_data["devices"].items():
            if "tools" not in device_data or not device_data["tools"]:
                continue

            if device_id not in schema["device_tools"]:
                continue

            schema_actions = set(schema["device_tools"][device_id].keys())

            for tool in device_data["tools"]:
                # tool 格式: device_id.action
                if "." in tool:
                    action = tool.split(".", 1)[1]
                    if action not in schema_actions:
                        mismatches.append((tool, device_id, action))

    if mismatches:
        print("\n✗ 以下工具的 action 与 schema 不匹配:")
        for tool, device_id, action in sorted(mismatches):
            print(f"  - {tool} (设备 {device_id} 缺少 action: {action})")
        raise AssertionError(f"有 {len(mismatches)} 个工具 action 不匹配")
    else:
        print("✓ 所有工具的 action 名称与 schema 匹配")


def test_summary():
    """打印统计摘要"""
    schema = load_json(TOOLS_SCHEMA_PATH)
    devices = load_json(HOME_DEVICES_PATH)

    schema_tools = get_all_tools_in_schema(schema)
    device_tools = get_all_tools_in_home_devices(devices)

    print("\n" + "=" * 50)
    print("工具统计摘要")
    print("=" * 50)
    print(f"tools_schema.json 工具总数: {len(schema_tools)}")
    print(f"  - 全局工具: {len(schema['global_tools'])}")
    print(f"  - 设备工具: {len(schema_tools) - len(schema['global_tools'])}")
    print(f"home_devices.json 工具总数: {len(device_tools)}")

    device_count = 0
    device_categories = devices.get("device_categories", {})
    for category_name, category_data in device_categories.items():
        if isinstance(category_data, dict) and "devices" in category_data:
            device_count += len(category_data["devices"])
    print(f"home_devices.json 设备总数: {device_count}")

    common_tools = schema_tools & device_tools
    print(f"两边都有的工具: {len(common_tools)}")
    print("=" * 50)


if __name__ == "__main__":
    print("开始测试工具一致性...\n")

    test_tools_schema_structure()
    test_schema_tools_in_home_devices()
    test_home_devices_tools_in_schema()
    test_device_has_schema()
    test_tool_action_match()
    test_summary()

    print("\n✅ 所有测试通过!")
