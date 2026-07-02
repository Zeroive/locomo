"""
HomeAssistant simulator generated from data/devices/tools_schema.json.

Each tool in the schema is exposed as a method whose name replaces "." with "_".
For example, "home.get_mode" is available as HomeAssistant.home_get_mode().
"""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


TOOLS_SCHEMA_PATH = Path(__file__).with_name("tools_schema.json")


def _load_tools_schema() -> Dict[str, Any]:
    with TOOLS_SCHEMA_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def _iter_tool_definitions(schema: Dict[str, Any]):
    for tool_def in schema.get("global_tools", {}).values():
        yield tool_def

    for device_tools in schema.get("device_tools", {}).values():
        for tool_def in device_tools.values():
            yield tool_def


class HomeAssistant:
    """A lightweight smart-home tool executor backed by tools_schema.json."""

    tools_schema: Dict[str, Any] = _load_tools_schema()
    tool_definitions: Dict[str, Dict[str, Any]] = {
        tool_def["tool_name"]: tool_def for tool_def in _iter_tool_definitions(tools_schema)
    }
    tool_method_map: Dict[str, str] = {
        tool_name: tool_name.replace(".", "_") for tool_name in tool_definitions
    }

    def __init__(self) -> None:
        self.devices: Dict[str, Dict[str, Any]] = {}
        self.home_modes: Dict[str, Dict[str, Any]] = {}
        self.occupancy: Dict[str, Dict[str, Any]] = {}
        self.scenes: Dict[str, Dict[str, Any]] = {}
        self.automations: Dict[str, Dict[str, Any]] = {}
        self.events: Dict[str, List[Dict[str, Any]]] = {}
        self._api_description = (
            "This tool belongs to the HomeAssistant, which provides functionality "
            "for controlling smart home devices."
        )

    def _load_scenario(self, scenario: Dict[str, Any], long_context: bool = False) -> None:
        """Load devices and optional simulator state from a scenario dictionary."""
        self.devices = {}
        for device in scenario.get("devices", []):
            device_id = (
                device.get("device_id")
                or device.get("entity_id")
                or device.get("id")
                or device.get("name")
            )
            if not device_id:
                continue

            self.devices[device_id] = {
                "device_id": device_id,
                "entity_id": device.get("entity_id", device_id),
                "name": device.get("name", device_id),
                "room": device.get("room", device.get("area", "其他")),
                "category": device.get("category", ""),
                "state": device.get("state", "off"),
                "attributes": deepcopy(device.get("attributes", {})),
            }

        self.home_modes = deepcopy(scenario.get("home_modes", {}))
        self.occupancy = deepcopy(scenario.get("occupancy", {}))
        self.scenes = deepcopy(scenario.get("scenes", {}))
        self.automations = deepcopy(scenario.get("automations", {}))
        self.events = deepcopy(scenario.get("events", {}))

    @classmethod
    def list_tools(cls) -> List[str]:
        """Return all schema tool names."""
        return sorted(cls.tool_definitions)

    @classmethod
    def list_tool_methods(cls) -> List[str]:
        """Return all HomeAssistant method names generated from tool names."""
        return sorted(cls.tool_method_map.values())

    def call_tool(self, tool_name: str, **kwargs: Any) -> Dict[str, Any]:
        """Execute a schema tool by original name, such as 'home.get_mode'."""
        if tool_name not in self.tool_definitions:
            return {"success": False, "error": f"Unknown tool: {tool_name}"}

        validation_error = self._validate_required_params(tool_name, kwargs)
        if validation_error:
            return validation_error

        domain, action = tool_name.split(".", 1)
        if domain == "home":
            return self._handle_home(action, kwargs)
        if domain == "scene":
            return self._handle_scene(action, kwargs)
        if domain == "automation":
            return self._handle_automation(action, kwargs)
        return self._handle_device_tool(tool_name, domain, action, kwargs)

    def _validate_required_params(self, tool_name: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        tool_def = self.tool_definitions[tool_name]
        model_required = (
            tool_def.get("model_call", {})
            .get("function", {})
            .get("parameters", {})
            .get("required")
        )
        required_params = (
            model_required
            if model_required is not None
            else [
                name
                for name, param_def in tool_def.get("parameters", {}).items()
                if param_def.get("required")
            ]
        )
        missing = [name for name in required_params if params.get(name) is None]
        if missing:
            return {
                "success": False,
                "tool_name": tool_name,
                "error": f"Missing required parameter(s): {', '.join(missing)}",
            }
        return None

    def _now(self) -> str:
        return datetime.now().isoformat(timespec="seconds")

    def _extract_device_id(self, params: Dict[str, Any], domain: str) -> Optional[str]:
        preferred_keys = ("device_id", "entity_id", f"{domain}_id", "name")
        for key in preferred_keys:
            if params.get(key):
                return params[key]

        for key, value in params.items():
            if key.endswith("_id") and key not in {"room_id", "rule_id", "scene_id", "user_id"} and value:
                return value
        return None

    def _is_identity_param(self, key: str) -> bool:
        return key in {"device_id", "entity_id", "name", "room", "room_id"} or key.endswith("_id")

    def _find_device(self, params: Dict[str, Any], domain: str) -> Optional[Dict[str, Any]]:
        device_id = self._extract_device_id(params, domain)
        if device_id in self.devices:
            return self.devices[device_id]

        room = params.get("room")
        candidates = [
            device
            for key, device in self.devices.items()
            if key.startswith(domain)
            or key == domain
            or device.get("category") == domain
            or device.get("entity_id", "").startswith(domain)
        ]
        if room:
            candidates = [device for device in candidates if device.get("room") == room]
        if device_id:
            candidates = [
                device
                for device in candidates
                if device_id in {device.get("device_id"), device.get("entity_id"), device.get("name")}
            ]
        return candidates[0] if candidates else None

    def _device_result(self, tool_name: str, device: Dict[str, Any], **extra: Any) -> Dict[str, Any]:
        result = {
            "success": True,
            "tool_name": tool_name,
            "device_id": device.get("device_id"),
            "state": device.get("state"),
            "attributes": deepcopy(device.get("attributes", {})),
            "updated_at": self._now(),
        }
        result.update(extra)
        return result

    def _handle_home(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        room = params.get("room", "其他")
        if action == "get_mode":
            mode = self.home_modes.get(room, {"mode": "home", "updated_at": self._now()})
            return {"success": True, "room": room, **deepcopy(mode)}

        if action == "set_mode":
            mode = params["mode"]
            self.home_modes[room] = {
                "mode": mode,
                "reason": params.get("reason"),
                "updated_at": self._now(),
            }
            return {"success": True, "room": room, "mode": mode}

        if action == "get_occupancy":
            value = deepcopy(
                self.occupancy.get(
                    room,
                    {"occupants": [], "all_away": True, "confidence": 1.0},
                )
            )
            user_id = params.get("user_id")
            if user_id:
                value["occupants"] = [
                    occupant for occupant in value.get("occupants", []) if occupant.get("user_id") == user_id
                ]
                value["all_away"] = not value["occupants"]
            return {"success": True, "room": room, **value}

        return {"success": False, "error": f"Unsupported home action: {action}"}

    def _handle_scene(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        scene_id = params.get("scene_id") or params.get("name") or params.get("scene_name")
        room = params.get("room", "其他")

        if action == "preview":
            return {
                "success": True,
                "room": room,
                "scene_id": scene_id,
                "changes": deepcopy(self.scenes.get(scene_id, {}).get("changes", [])) if scene_id else [],
            }

        if action == "activate":
            activated = []
            scene = self.scenes.get(scene_id, {})
            for change in scene.get("changes", []):
                device = self.devices.get(change.get("device_id"))
                if not device:
                    continue
                device["attributes"].update(deepcopy(change.get("attributes", {})))
                if "state" in change:
                    device["state"] = change["state"]
                activated.append(device["device_id"])
            return {
                "success": True,
                "room": room,
                "scene_id": scene_id,
                "affected_devices": activated,
                "updated_at": self._now(),
            }

        return {"success": False, "error": f"Unsupported scene action: {action}"}

    def _handle_automation(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        rule_id = params.get("rule_id") or params.get("name") or f"rule_{len(self.automations) + 1}"

        if action == "create_rule":
            self.automations[rule_id] = {"rule_id": rule_id, "enabled": True, **deepcopy(params)}
            return {"success": True, "rule_id": rule_id, "enabled": True}

        if action == "disable_rule":
            if rule_id not in self.automations:
                self.automations[rule_id] = {"rule_id": rule_id}
            self.automations[rule_id]["enabled"] = False
            return {"success": True, "rule_id": rule_id, "enabled": False}

        if action == "list_rules":
            return {"success": True, "rules": deepcopy(list(self.automations.values()))}

        return {"success": False, "error": f"Unsupported automation action: {action}"}

    def _handle_device_tool(self, tool_name: str, domain: str, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        device = self._find_device(params, domain)
        if not device:
            device_id = self._extract_device_id(params, domain) or domain
            device = {
                "device_id": device_id,
                "entity_id": device_id,
                "name": device_id,
                "room": params.get("room", "其他"),
                "category": domain,
                "state": "off",
                "attributes": {},
            }
            self.devices[device_id] = device

        attrs = device["attributes"]

        if action.startswith("get_") or action in {"list_connected_devices"}:
            if action == "list_connected_devices":
                return {"success": True, "tool_name": tool_name, "devices": deepcopy(attrs.get("connected_devices", []))}
            return self._device_result(tool_name, device)

        if action.startswith("set_"):
            for key, value in params.items():
                if not self._is_identity_param(key):
                    attrs[key] = value
            if "power" in params:
                device["state"] = "on" if params["power"] in {True, "on", "开", 1} else "off"
            if "brightness" in params:
                device["state"] = "on" if params["brightness"] > 0 else "off"
            return self._device_result(tool_name, device)

        state_by_action = {
            "lock": "locked",
            "unlock": "unlocked",
            "open": "open",
            "close": "closed",
            "stop": "stopped",
            "start": "running",
            "pause": "paused",
            "start_cleaning": "cleaning",
            "return_to_dock": "docked",
            "return_to_base": "docked",
            "start_recording": "recording",
            "stop_recording": "idle",
            "mute": "muted",
            "self_test": "testing",
            "restart": "restarting",
            "ignite": "on",
            "turn_off": "off",
            "start_brew": "brewing",
            "dispense": "dispensing",
            "pause_media": "paused",
            "stop_media": "stopped",
            "media_control": params.get("control", params.get("command", "controlled")),
            "play_media": "playing",
            "cast": "casting",
            "answer_call": "in_call",
            "end_call": "idle",
            "play_chime": "chiming",
            "activate_scene": "on",
            "reset_filter": "on",
            "reset_filter_reminder": "on",
            "block_device": "on",
            "limit_device": "on",
            "create_temp_password": "on",
            "get_unlock_logs": "on",
            "take_snapshot": "on",
            "get_stream": "on",
            "get_recent_events": "on",
        }
        if action in state_by_action:
            device["state"] = state_by_action[action]

        for key, value in params.items():
            if not self._is_identity_param(key):
                attrs[key] = value

        if action in {"get_recent_events", "get_unlock_logs"}:
            return {
                "success": True,
                "tool_name": tool_name,
                "device_id": device["device_id"],
                "events": deepcopy(self.events.get(device["device_id"], [])),
            }

        return self._device_result(tool_name, device)


def _make_tool_method(tool_name: str):
    def tool_method(self: HomeAssistant, **kwargs: Any) -> Dict[str, Any]:
        return self.call_tool(tool_name, **kwargs)

    tool_method.__name__ = tool_name.replace(".", "_")
    tool_method.__qualname__ = f"HomeAssistant.{tool_method.__name__}"
    tool_method.__doc__ = HomeAssistant.tool_definitions[tool_name].get("description", "")
    return tool_method


for _tool_name, _method_name in HomeAssistant.tool_method_map.items():
    setattr(HomeAssistant, _method_name, _make_tool_method(_tool_name))


__all__ = ["HomeAssistant"]
