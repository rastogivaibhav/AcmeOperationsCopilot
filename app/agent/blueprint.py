"""Versioned prompts and role-specific *tool visibility*, never an auth source.

MCP enforces the actual Keycloak permissions. A blueprint cannot grant them.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from acme_shared.policies import ROLE_PERMISSIONS
from app.agent.tool_probe import READ_TOOLS
from app.skills.escalation import SKILL_NAME, SKILL_SPEC
from app.actions import PROPOSAL_TOOL_SPECS

ROOT = Path(__file__).resolve().parents[2] / "blueprints"


@dataclass(frozen=True)
class Blueprint:
    role: str
    name: str
    version: str
    persona: str
    mission: str
    principles: tuple[str, ...]
    response_sections: tuple[str, ...]
    tools: frozenset[str]
    skills: frozenset[str] = frozenset()
    action_requests: frozenset[str] = frozenset()

    @property
    def system_prompt(self) -> str:
        principles = "\n".join(f"- {item}" for item in self.principles)
        sections = ", ".join(self.response_sections)
        skills = ", ".join(sorted(self.skills)) or "none"
        return (
            f"You are {self.persona}, a role-scoped Acme Operations assistant. "
            f"Your purpose: {self.mission}\n"
            f"Operating principles:\n{principles}\n"
            f"Available reusable Skills: {skills}. Invoke a Skill when the question "
            f"requests an escalation summary or risk assessment; first look up a "
            f"customer by name to obtain their verified customer_id, unless the Skill "
            f"can resolve the name through authenticated MCP itself. "
            f"Skill risk and evidence are computed from authenticated MCP records, "
            f"not by guessing. "
            f"Use the approved MCP tools dynamically based on the question. "
            f"Use exact UUIDs in MCP results, not placeholders. If a tool returns "
            f"validation_error, retry using the verified ID; it does not mean "
            f"the customer or issue was not found. "
            f"Do not call unrelated tools; do not claim findings absent from tool results. "
            f"When answering an operational question, use these headings where relevant: {sections}. "
            f"A recommendation is not permission to persist a change. "
            f"Agent MCP execution is read-only. For permitted roles, request_issue_update and "
            f"request_next_action are PROPOSALS ONLY: they cannot modify business records. "
            f"Only the authenticated user can confirm a proposal through the website, "
            f"after which a separately authorised backend operation may commit it. "
            f"Never describe a proposal as completed."
        )


def _mapping(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Blueprint must be an object")
    return data


def load_blueprint(role: str, root: Path = ROOT) -> Blueprint:
    if role not in ROLE_PERMISSIONS:
        raise ValueError("UNKNOWN_AGENT_ROLE")
    enterprise = _mapping(root / "enterprise.yaml")
    profile = _mapping(root / f"{role}.yaml")
    if profile.get("role") != role:
        raise ValueError("ROLE_PROFILE_MISMATCH")
    tools = profile.get("tools")
    if not isinstance(tools, list) or not tools:
        raise ValueError("ROLE_TOOLS_MISSING")
    if len(set(tools)) != len(tools):
        raise ValueError("DUPLICATE_ROLE_TOOL")
    # A role profile is only allowed to *reduce* model-visible capabilities.
    allowed = READ_TOOLS.intersection(ROLE_PERMISSIONS[role])
    if not set(tools).issubset(allowed):
        raise ValueError("BLUEPRINT_TOOL_ESCALATION")
    enterprise_skills = enterprise.get("skills", [])
    profile_skills = profile.get("skills", [])
    if (not isinstance(enterprise_skills, list) or not isinstance(profile_skills, list)
            or len(set(profile_skills)) != len(profile_skills)
            or not set(profile_skills).issubset(set(enterprise_skills))
            or not set(profile_skills).issubset({SKILL_NAME})):
        raise ValueError("BLUEPRINT_SKILL_ESCALATION")
    action_requests = profile.get("action_requests", [])
    if not isinstance(action_requests, list) or len(set(action_requests)) != len(action_requests):
        raise ValueError("BLUEPRINT_ACTION_ESCALATION")
    action_permission = {"request_issue_update": "update_issue_status",
                         "request_next_action": "create_next_action"}
    if (not set(action_requests).issubset(PROPOSAL_TOOL_SPECS) or
            any(action_permission[name] not in ROLE_PERMISSIONS[role]
                for name in action_requests)):
        raise ValueError("BLUEPRINT_ACTION_ESCALATION")
    return Blueprint(
        role=role,
        name=str(enterprise["name"]),
        version=f"{enterprise['version']}:{role}:{profile['version']}",
        persona=str(profile["persona"]),
        mission=str(profile["mission"]),
        principles=tuple(str(p) for p in enterprise["principles"]),
        response_sections=tuple(str(p) for p in enterprise["response_sections"]),
        tools=frozenset(tools),
        skills=frozenset(profile_skills),
        action_requests=frozenset(action_requests),
    )


def tool_specs_for_profile(mcp_tools: list[dict], blueprint: Blueprint) -> list[dict]:
    """Convert actual MCP schemas to Ollama format and restrict to permitted role tools."""
    if blueprint.role not in ROLE_PERMISSIONS or not blueprint.tools.issubset(
            READ_TOOLS.intersection(ROLE_PERMISSIONS[blueprint.role])):
        raise ValueError("BLUEPRINT_TOOL_ESCALATION")
    indexed = {t.get("name"): t for t in mcp_tools}
    if any(name not in indexed for name in blueprint.tools):
        raise ValueError("MCP_PROFILE_TOOL_MISSING")
    specs = []
    for name in sorted(blueprint.tools):
        item = indexed[name]
        schema = item.get("inputSchema")
        if not isinstance(schema, dict) or schema.get("type") != "object":
            raise ValueError("INVALID_MCP_TOOL_SCHEMA")
        specs.append({"type": "function", "function": {
            "name": name, "description": item.get("description") or name,
            "parameters": schema,
        }})
    return specs


def agent_specs_for_profile(mcp_tools: list[dict], blueprint: Blueprint) -> list[dict]:
    """Authenticated MCP read tools, local Skills, and non-mutating proposals."""
    specs = tool_specs_for_profile(mcp_tools, blueprint)
    if not blueprint.skills.issubset({SKILL_NAME}):
        raise ValueError("BLUEPRINT_SKILL_ESCALATION")
    if SKILL_NAME in blueprint.skills:
        import copy
        specs.append(copy.deepcopy(SKILL_SPEC))
    if not blueprint.action_requests.issubset(PROPOSAL_TOOL_SPECS):
        raise ValueError("BLUEPRINT_ACTION_ESCALATION")
    action_permission = {"request_issue_update": "update_issue_status",
                         "request_next_action": "create_next_action"}
    if any(action_permission[name] not in ROLE_PERMISSIONS[blueprint.role]
           for name in blueprint.action_requests):
        raise ValueError("BLUEPRINT_ACTION_ESCALATION")
    import copy
    for name in sorted(blueprint.action_requests):
        specs.append(copy.deepcopy(PROPOSAL_TOOL_SPECS[name]))
    return specs
