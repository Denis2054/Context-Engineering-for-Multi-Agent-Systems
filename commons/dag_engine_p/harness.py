# =============================================================================
# harness.py  —  The Gate + Topology Validator
# commons/dag_engine/harness.py
#
# Copyright 2025-2026, Denis Rothman
#
# WHAT THIS FILE DOES:
#   Sits in front of the engine and enforces two distinct gates:
#
#   GATE 1 — Business rules (runs BEFORE the planner):
#     Sanitize input → Moderate content → Business rules check
#     If any check fails, the request is vetoed before a single LLM call.
#
#   GATE 2 — Topology validation (runs AFTER planning, BEFORE execution):
#     Every cross-domain edge in the Execution DAG is checked against the
#     standing Topology DAG. If any edge is forbidden, the plan is vetoed
#     before a single agent runs.
#
# TOPOLOGY DAG FIX (v1.1):
#   Legal and Marketing now include "General" as a permitted target.
#   Rationale: the topology governs which domains may INITIATE work in another
#   domain. A Legal:Researcher or Marketing:Researcher returning findings to a
#   General:Summarizer or General:Writer is a fan-in data flow, not an
#   initiation. Blocking it caused Gate 2 to veto every multi-domain DAG.
#   Adding Legal → General and Marketing → General restores correct behaviour.
#
# RELATIONSHIP TO OTHER FILES:
#   - Called by:  Universal notebook / call site  (before engine.py)
#   - Imports:    helpers.py → helper_sanitize_input(), helper_moderate_content()
#   - Does NOT import engine.py or run_dag.py (harness is upstream of both)
# =============================================================================

import logging
import json
from datetime import datetime, timezone

from helpers import helper_sanitize_input, helper_moderate_content


# =============================================================================
# SECTION A — TOPOLOGY DAG
# =============================================================================

TOPOLOGY_DAG = {
    # General is the home domain for all current POC agents.
    # Full outbound reach — orchestrates all other domains.
    "General"    : ["Legal", "Finance", "HR", "Marketing", "Research", "Compliance"],

    # Legal agents may return findings to General (fan-in) and escalate to
    # Finance or Compliance. They may NOT initiate Marketing or HR workflows.
    "Legal"      : ["General", "Finance", "Compliance"],

    # Finance agents may produce compliance artefacts.
    "Finance"    : ["Compliance"],

    # HR agents may consult Legal and Finance.
    "HR"         : ["Legal", "Finance"],

    # Marketing agents may return findings to General (fan-in) and commission
    # Research. They may NOT initiate Legal, Finance, HR, or Compliance directly.
    "Marketing"  : ["General", "Research"],

    # Research is terminal — produces output, never initiates calls.
    "Research"   : [],

    # Compliance is terminal — audit only, no outbound workflow triggers.
    "Compliance" : [],
}

# Business rules: goals containing any of these terms are vetoed at Gate 1.
FORBIDDEN_TERMS = [
    "ignore all instructions",
    "bypass compliance",
    "override legal",
    "disable moderation",
    "jailbreak",
]

# Required terms — empty for POC (permissive).
REQUIRED_TERMS = []


# =============================================================================
# SECTION B — AUDIT LOGGER
# =============================================================================

_audit_logger = logging.getLogger("harness.audit")

def _audit(event: str, outcome: str, detail: dict) -> dict:
    record = {
        "timestamp" : datetime.now(timezone.utc).isoformat(),
        "event"     : event,
        "outcome"   : outcome,
        **detail,
    }
    if outcome == "VETO":
        _audit_logger.warning(json.dumps(record))
    else:
        _audit_logger.info(json.dumps(record))
    return record


# =============================================================================
# SECTION C — THE HARNESS CLASS
# =============================================================================

class Harness:
    """
    The governance gate for the Universal Context Engine.

    Usage:
        harness = Harness(client=openai_client)

        # Gate 1 — before planning
        result = harness.gate(goal)
        if not result["allowed"]:
            print(result["reason"])

        # Gate 2 — after planning, before execution
        topo = harness.validate_topology(dag)
        if not topo["allowed"]:
            print(topo["reason"])
    """

    def __init__(self, client, topology: dict = None):
        self._client   = client
        self._topology = topology if topology is not None else TOPOLOGY_DAG
        logging.info(
            f"[Harness] Initialised. "
            f"Topology domains: {sorted(self._topology.keys())}"
        )

    # ------------------------------------------------------------------
    # GATE 1 — Business Rules
    # ------------------------------------------------------------------

    def gate(self, goal: str) -> dict:
        audit_trail = []

        sanitize_result = self._check_sanitize(goal)
        audit_trail.append(sanitize_result["audit"])
        if not sanitize_result["allowed"]:
            return {"allowed": False, "reason": sanitize_result["reason"], "audit": audit_trail}

        moderate_result = self._check_moderation(goal)
        audit_trail.append(moderate_result["audit"])
        if not moderate_result["allowed"]:
            return {"allowed": False, "reason": moderate_result["reason"], "audit": audit_trail}

        rules_result = self._check_business_rules(goal)
        audit_trail.append(rules_result["audit"])
        if not rules_result["allowed"]:
            return {"allowed": False, "reason": rules_result["reason"], "audit": audit_trail}

        _audit("gate_1", "PASS", {"goal_preview": goal[:120]})
        return {"allowed": True, "reason": "All Gate 1 checks passed.", "audit": audit_trail}

    # ------------------------------------------------------------------
    # GATE 2 — Topology Validation
    # ------------------------------------------------------------------

    def validate_topology(self, dag: list) -> dict:
        """
        Check every cross-domain edge in the Execution DAG against TOPOLOGY_DAG.

        An edge exists when node B depends_on node A and B.domain != A.domain.
        The edge is permitted if A.domain → B.domain is in TOPOLOGY_DAG.
        Intra-domain edges always pass.
        """
        domain_of = {node["id"]: node.get("domain", "General") for node in dag}
        forbidden_edges = []

        for node in dag:
            target_id     = node["id"]
            target_domain = domain_of[target_id]

            for dep_id in node.get("depends_on", []):
                source_domain = domain_of.get(dep_id, "General")

                if source_domain == target_domain:
                    continue  # intra-domain — always permitted

                permitted_targets = self._topology.get(source_domain, [])
                if target_domain not in permitted_targets:
                    forbidden_edges.append({
                        "source_node"   : dep_id,
                        "source_domain" : source_domain,
                        "target_node"   : target_id,
                        "target_domain" : target_domain,
                    })
                    logging.warning(
                        f"[Harness] Topology violation: "
                        f"'{dep_id}' ({source_domain}) → "
                        f"'{target_id}' ({target_domain}) is FORBIDDEN."
                    )

        if forbidden_edges:
            reason = (
                f"Topology violation: {len(forbidden_edges)} forbidden "
                f"cross-domain edge(s) detected. "
                f"First violation: {forbidden_edges[0]['source_domain']} → "
                f"{forbidden_edges[0]['target_domain']} is not in TOPOLOGY_DAG."
            )
            audit_record = _audit(
                "gate_2_topology", "VETO",
                {"forbidden_edges": forbidden_edges, "reason": reason}
            )
            return {
                "allowed"         : False,
                "reason"          : reason,
                "forbidden_edges" : forbidden_edges,
                "audit"           : audit_record,
            }

        audit_record = _audit(
            "gate_2_topology", "PASS",
            {
                "nodes_checked" : len(dag),
                "edges_checked" : sum(len(n.get("depends_on", [])) for n in dag),
            }
        )
        return {
            "allowed"         : True,
            "reason"          : "All topology edges are permitted.",
            "forbidden_edges" : [],
            "audit"           : audit_record,
        }

    # ------------------------------------------------------------------
    # UTILITY
    # ------------------------------------------------------------------

    def describe_topology(self) -> dict:
        return {
            "topology"         : self._topology,
            "terminal_domains" : [d for d, t in self._topology.items() if not t],
            "total_domains"    : len(self._topology),
        }

    # ==================================================================
    # PRIVATE HELPERS
    # ==================================================================

    def _check_sanitize(self, goal: str) -> dict:
        try:
            helper_sanitize_input(goal)
            audit = _audit("gate_1_sanitize", "PASS", {"goal_preview": goal[:120]})
            return {"allowed": True, "reason": "Sanitization passed.", "audit": audit}
        except ValueError as e:
            reason = f"Input sanitization failed: {e}"
            audit  = _audit("gate_1_sanitize", "VETO",
                            {"goal_preview": goal[:120], "reason": reason})
            return {"allowed": False, "reason": reason, "audit": audit}

    def _check_moderation(self, goal: str) -> dict:
        report = helper_moderate_content(goal, self._client)
        if report.get("flagged", False):
            flagged_cats = [c for c, v in report.get("categories", {}).items() if v]
            reason = f"Content moderation flagged this goal. Categories: {flagged_cats}"
            audit  = _audit("gate_1_moderation", "VETO",
                            {"goal_preview": goal[:120], "flagged_cats": flagged_cats,
                             "moderation_report": report})
            return {"allowed": False, "reason": reason, "audit": audit}
        audit = _audit("gate_1_moderation", "PASS", {"goal_preview": goal[:120]})
        return {"allowed": True, "reason": "Moderation passed.", "audit": audit}

    def _check_business_rules(self, goal: str) -> dict:
        goal_lower = goal.lower()

        for term in FORBIDDEN_TERMS:
            if term.lower() in goal_lower:
                reason = f"Business rule violation: goal contains forbidden term '{term}'."
                audit  = _audit("gate_1_business_rules", "VETO",
                                {"goal_preview": goal[:120], "forbidden_term": term})
                return {"allowed": False, "reason": reason, "audit": audit}

        if REQUIRED_TERMS:
            if not any(t.lower() in goal_lower for t in REQUIRED_TERMS):
                reason = (f"Business rule violation: goal must reference at least "
                          f"one of {REQUIRED_TERMS}.")
                audit  = _audit("gate_1_business_rules", "VETO",
                                {"goal_preview": goal[:120], "required_terms": REQUIRED_TERMS})
                return {"allowed": False, "reason": reason, "audit": audit}

        audit = _audit("gate_1_business_rules", "PASS", {"goal_preview": goal[:120]})
        return {"allowed": True, "reason": "Business rules passed.", "audit": audit}
