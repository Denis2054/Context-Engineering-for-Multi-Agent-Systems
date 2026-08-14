# lc_registry.py
# =============================================================================
# Universal Context Engine — LangChain Edition
# The agent toolkit.
#
# Replaces: registry.py
#
# The original AgentRegistry did three jobs:
#   1. mapped agent names to functions            -> a plain dict of tools
#   2. injected dependencies per agent (if/elif)  -> closures in lc_agents.py
#   3. hand-wrote get_capabilities_description()  -> GENERATED from the tools
#
# Job 3 is the interesting one. In the original, the capability text listing
# every input key was maintained by hand in a 30-line f-string, and had to be
# kept in sync with four function signatures by discipline alone. Here it is
# derived from the tools' own Pydantic schemas, so it cannot drift.
#
# The rendering format below is ours, not LangChain's. LangChain can describe a
# tool to a model (render_text_description, convert_to_openai_tool); it does not
# produce the ROLE:/INPUTS: block this engine's Planner prompt expects.
# =============================================================================

from __future__ import annotations

import logging
from typing import Any, Dict, List, Set


class AgentToolkit:
    """Holds the tools and describes them to the Planner."""

    def __init__(self, tools: List):
        self.tools = list(tools)
        self.registry: Dict[str, Any] = {t.name: t for t in self.tools}
        if len(self.registry) != len(self.tools):
            raise ValueError("Duplicate tool names in the toolkit.")
        logging.info(f"Agent toolkit initialized: {', '.join(self.registry)}")

    # ------------------------------------------------------------------ #
    def get(self, name: str):
        """Look up a tool by name. Raises the same error the original did."""
        tool = self.registry.get(name)
        if tool is None:
            logging.error(f"Agent '{name}' not found in registry.")
            raise ValueError(f"Agent '{name}' not found in registry.")
        return tool

    # Backwards-compatible alias with the original API.
    get_handler = get

    def names(self) -> List[str]:
        return list(self.registry.keys())

    # ------------------------------------------------------------------ #
    @staticmethod
    def _schema(tool) -> Dict[str, Any]:
        """The tool's auto-generated JSON schema, or an empty dict."""
        schema_model = getattr(tool, "args_schema", None)
        if schema_model is None:
            return {}
        try:
            return schema_model.model_json_schema()
        except AttributeError:          # a plain dict schema
            return dict(schema_model)
        except Exception:
            return {}

    def arg_names(self, name: str) -> Set[str]:
        """
        The exact argument names a tool accepts.

        Used by the executor to drop any key the Planner produced that this
        agent does not take, rather than relying on Pydantic's silent
        extra-field behaviour.
        """
        return set((self._schema(self.get(name)).get("properties") or {}).keys())

    # ------------------------------------------------------------------ #
    def get_capabilities_description(self) -> str:
        """
        Build the capability block the Planner reads, straight from each tool's
        auto-generated schema. Nothing here is hand-written.
        """
        lines = [
            "Available Agents and their required inputs.",
            "CRITICAL: You MUST use the exact input key names provided for each agent.",
            "",
        ]
        for i, tool in enumerate(self.tools, start=1):
            schema = self._schema(tool)
            props = schema.get("properties") or {}
            required = set(schema.get("required") or [])

            role = " ".join((tool.description or "").split())
            lines.append(f"{i}. AGENT: {tool.name}")
            lines.append(f"   ROLE: {role}")
            lines.append("   INPUTS:")
            if not props:
                lines.append("     - (none)")
            for key, spec in props.items():
                kind = spec.get("type", "string")
                if "anyOf" in spec:
                    kind = "/".join(
                        o.get("type", "any")
                        for o in spec["anyOf"]
                        if o.get("type") != "null"
                    ) or "string"
                flag = "required" if key in required else "optional"
                desc = spec.get("description", "")
                suffix = f" — {desc}" if desc else ""
                lines.append(f'     - "{key}": ({kind}, {flag}){suffix}')
            lines.append("")
        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    def schema_report(self) -> str:
        """Human-readable dump used by the notebook's inspection cell."""
        out = []
        for tool in self.tools:
            args = ", ".join((self._schema(tool).get("properties") or {}).keys())
            out.append(f"{tool.name:<12} ({args})")
        return "\n".join(out)


def build_toolkit(tools) -> AgentToolkit:
    return AgentToolkit(tools)
