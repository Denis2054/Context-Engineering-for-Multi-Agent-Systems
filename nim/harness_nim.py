# =============================================================================
# harness_nim.py  —  The Two Gates
# Universal Context Engine — DAG Edition · NIM
#
# Copyright 2025-2026, Denis Rothman
#
# ROLE IN THE SYSTEM
# ------------------
# Governance that runs before spending, not after. Two gates, placed at the two
# moments where a veto is still free:
#
#   GATE 1 — before planning.
#     sanitize -> moderate -> business rules
#     A veto here costs zero LLM tokens. Nothing has been generated yet.
#
#   GATE 2 — after planning, before execution.
#     Every cross-domain edge of the proposed DAG is checked against a standing
#     topology. A veto here costs one planning call and no agent calls.
#
# WHY GATE 2 EXISTS AT ALL
# ------------------------
# This is the gate that has no equivalent in a conventional agent framework,
# and it only becomes possible because the planner emits a plan as data before
# anything runs.
#
# In a ReAct-style loop the agent decides its next action, takes it, observes,
# and decides again. There is no artefact to inspect: by the time you can see
# what it chose to do, it has already done it. Governance can only be applied
# per-action, inside the loop, with no view of the shape of the whole.
#
# A plan-then-execute engine produces a complete, inspectable object first.
# That object can be validated against rules about the whole graph — "Marketing
# may not initiate Legal work" is a statement about an edge, and you need the
# edge to exist as data before you can refuse it.
#
# The cost of this design is real and worth naming: the plan is fixed before
# execution begins, so the engine cannot adapt mid-run to something a node
# discovers. Governability is bought with adaptivity.
# =============================================================================

import json
import logging
from datetime import datetime, timezone

from helpers import helper_sanitize_input, helper_moderate_content


# =============================================================================
# SECTION A — THE TOPOLOGY
#
# A directed graph of which domain may INITIATE work in which other domain.
#
# Read each entry as: "a node in domain X may be depended upon by a node in
# any domain listed in X's array." The direction matters and is easy to get
# backwards. The edge runs from the node producing output to the node consuming
# it — from the dependency to the dependent.
#
# THE FAN-IN CORRECTION
# ---------------------
# Legal and Marketing both list "General" as a permitted target, and that entry
# is the fix for a bug worth understanding, because the same mistake recurs in
# every rules engine of this shape.
#
# The intent behind the topology is to stop one department commissioning work
# from another without authority — Marketing must not be able to task Legal.
# But a Legal:Researcher whose findings flow into a General:Summarizer is not
# Legal commissioning anything. It is Legal reporting back. The data flows
# Legal -> General while the authority flowed General -> Legal.
#
# Without "General" in those arrays, Gate 2 vetoed every multi-domain plan the
# engine could produce, because every useful multi-domain plan fans back in to
# a General Writer. The rule was enforcing the letter of a policy against the
# direction of its intent.
#
# Terminal domains — those with an empty array — are the strong statement here:
# Research and Compliance can be asked for output and can never initiate work
# in anyone else's domain.
# =============================================================================

TOPOLOGY_DAG = {
    # General orchestrates. It is where user goals enter and artefacts leave.
    "General"    : ["Legal", "Finance", "HR", "Marketing", "Research", "Compliance"],

    # Legal reports back to General, escalates to Finance or Compliance.
    # It may not initiate Marketing or HR work.
    "Legal"      : ["General", "Finance", "Compliance"],

    # Finance produces compliance artefacts.
    "Finance"    : ["Compliance"],

    # HR may consult Legal and Finance.
    "HR"         : ["Legal", "Finance"],

    # Marketing reports back to General and may commission Research.
    # It may not initiate Legal, Finance, HR, or Compliance work.
    "Marketing"  : ["General", "Research"],

    # Terminal — produce output, never initiate.
    "Research"   : [],
    "Compliance" : [],
}


# Substring veto list for Gate 1. Blunt and cheap, and it runs before anything
# is spent, which is exactly the right trade at this position in the pipeline.
FORBIDDEN_TERMS = [
    "ignore all instructions",
    "bypass compliance",
    "override legal",
    "disable moderation",
    "jailbreak",
]

# Allow-list. Empty means permissive. Populate it to restrict the engine to a
# named subject area — useful when a deployment should only answer questions
# about a specific product line.
REQUIRED_TERMS = []


# =============================================================================
# SECTION B — AUDIT TRAIL
#
# Every gate decision emits a structured, timestamped record. Vetoes log at
# WARNING so they surface in any log aggregator without a custom filter.
#
# The records are returned as well as logged. The dashboard renders them, which
# is what makes a veto legible to the person who triggered it rather than
# something that happened silently in a log file they will never read.
# =============================================================================

_audit_logger = logging.getLogger("harness.audit")


def _audit(event: str, outcome: str, detail: dict) -> dict:
    """Emit and return one structured audit record."""
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event"    : event,
        "outcome"  : outcome,
        **detail,
    }
    if outcome == "VETO":
        _audit_logger.warning(json.dumps(record))
    else:
        _audit_logger.info(json.dumps(record))
    return record


# =============================================================================
# SECTION C — THE HARNESS
# =============================================================================

class Harness:
    """
    The governance gate.

    Usage:
        gate = Harness(client=openai_client)

        g1 = gate.gate(goal)                    # before planning
        if not g1["allowed"]:
            ...

        g2 = gate.validate_topology(dag)        # after planning
        if not g2["allowed"]:
            ...

    The client is used only for the moderation call. On the NIM path that means
    the Harness holds the OpenAI client while every other component holds the
    NIM client — the one place in the notebook where the two cross.
    """

    def __init__(self, client, topology: dict = None):
        """
        Args:
            client:          OpenAI client for moderation. May be None; the
                             moderation sub-check then passes through and the
                             other two sub-checks still apply.
            topology (dict): override the default TOPOLOGY_DAG. Passing a
                             stricter graph here is how you tighten governance
                             per deployment without editing this file.
        """
        self._client   = client
        self._topology = topology if topology is not None else TOPOLOGY_DAG
        logging.info(
            f"[Harness] initialised. domains={sorted(self._topology.keys())}"
        )

    # ------------------------------------------------------------------
    # GATE 1 — before the planner
    # ------------------------------------------------------------------

    def gate(self, goal: str) -> dict:
        """
        Screen a goal before any model is called.

        Three checks in ascending order of cost: a regex pass, a network call,
        and a substring scan. Ordering by cost means the cheapest rejection
        happens first and the network call is skipped entirely for a goal that
        was never going to pass.

        Args:
            goal (str): the user's high-level goal.

        Returns:
            dict: {allowed: bool, reason: str, audit: list[dict]}
        """
        trail = []

        for check in (self._check_sanitize, self._check_moderation,
                      self._check_business_rules):
            result = check(goal)
            trail.append(result["audit"])
            if not result["allowed"]:
                return {"allowed": False, "reason": result["reason"], "audit": trail}

        _audit("gate_1", "PASS", {"goal_preview": goal[:120]})
        return {"allowed": True, "reason": "All Gate 1 checks passed.", "audit": trail}

    # ------------------------------------------------------------------
    # GATE 2 — after the planner, before the Foreman
    # ------------------------------------------------------------------

    def validate_topology(self, dag: list) -> dict:
        """
        Validate every cross-domain edge in a planned DAG.

        An edge exists wherever node B lists node A in depends_on. It is a
        cross-domain edge when the two nodes declare different domains, and it
        is permitted only when B's domain appears in TOPOLOGY_DAG[A's domain].
        Same-domain edges always pass.

        The whole graph is checked before returning, so the audit record lists
        every violation rather than only the first. Fixing a policy is easier
        with the complete set in front of you.

        Args:
            dag (list[dict]): the planner's node list.

        Returns:
            dict: {allowed, reason, forbidden_edges, audit}
        """
        domain_of = {node["id"]: node.get("domain", "General") for node in dag}
        forbidden = []

        for node in dag:
            target_id     = node["id"]
            target_domain = domain_of[target_id]

            for dep_id in node.get("depends_on", []):
                source_domain = domain_of.get(dep_id, "General")

                if source_domain == target_domain:
                    continue

                if target_domain not in self._topology.get(source_domain, []):
                    forbidden.append({
                        "source_node"  : dep_id,
                        "source_domain": source_domain,
                        "target_node"  : target_id,
                        "target_domain": target_domain,
                    })
                    logging.warning(
                        f"[Harness] topology violation: '{dep_id}' "
                        f"({source_domain}) -> '{target_id}' ({target_domain})"
                    )

        if forbidden:
            first = forbidden[0]
            reason = (
                f"Topology violation: {len(forbidden)} forbidden cross-domain "
                f"edge(s). First: {first['source_domain']} -> "
                f"{first['target_domain']} is not permitted."
            )
            audit = _audit("gate_2_topology", "VETO",
                           {"forbidden_edges": forbidden, "reason": reason})
            return {"allowed": False, "reason": reason,
                    "forbidden_edges": forbidden, "audit": audit}

        audit = _audit("gate_2_topology", "PASS", {
            "nodes_checked": len(dag),
            "edges_checked": sum(len(n.get("depends_on", [])) for n in dag),
        })
        return {"allowed": True, "reason": "All topology edges are permitted.",
                "forbidden_edges": [], "audit": audit}

    # ------------------------------------------------------------------
    # UTILITY
    # ------------------------------------------------------------------

    def describe_topology(self) -> dict:
        """Return the topology plus derived facts, for display and audit."""
        return {
            "topology"        : self._topology,
            "terminal_domains": [d for d, t in self._topology.items() if not t],
            "total_domains"   : len(self._topology),
        }

    # ==================================================================
    # GATE 1 SUB-CHECKS
    # ==================================================================

    def _check_sanitize(self, goal: str) -> dict:
        """Regex screen for injection phrasing. Free, local, first."""
        try:
            helper_sanitize_input(goal)
            audit = _audit("gate_1_sanitize", "PASS", {"goal_preview": goal[:120]})
            return {"allowed": True, "reason": "Sanitization passed.", "audit": audit}
        except ValueError as e:
            reason = f"Input sanitization failed: {e}"
            audit = _audit("gate_1_sanitize", "VETO",
                           {"goal_preview": goal[:120], "reason": reason})
            return {"allowed": False, "reason": reason, "audit": audit}

    def _check_moderation(self, goal: str) -> dict:
        """
        OpenAI moderation. The only Gate 1 check that touches the network, and
        the only one that can be unavailable.

        When it is unavailable the report carries available=False and the goal
        passes. The audit record preserves that distinction so "clean" and
        "unchecked" never look the same in the trail.
        """
        report = helper_moderate_content(goal, self._client)

        if report.get("flagged", False):
            hits = [c for c, v in report.get("categories", {}).items() if v]
            reason = f"Content moderation flagged this goal. Categories: {hits}"
            audit = _audit("gate_1_moderation", "VETO", {
                "goal_preview": goal[:120],
                "flagged_categories": hits,
                "moderation_report": report,
            })
            return {"allowed": False, "reason": reason, "audit": audit}

        if not report.get("available", True):
            audit = _audit("gate_1_moderation", "PASS_UNCHECKED", {
                "goal_preview": goal[:120],
                "note": "Moderation endpoint unavailable — failed open.",
            })
            return {"allowed": True,
                    "reason": "Moderation unavailable — passed without checking.",
                    "audit": audit}

        audit = _audit("gate_1_moderation", "PASS", {"goal_preview": goal[:120]})
        return {"allowed": True, "reason": "Moderation passed.", "audit": audit}

    def _check_business_rules(self, goal: str) -> dict:
        """Deployment-specific substring policy: a veto list and an allow-list."""
        goal_lower = (goal or "").lower()

        for term in FORBIDDEN_TERMS:
            if term.lower() in goal_lower:
                reason = f"Business rule violation: goal contains forbidden term '{term}'."
                audit = _audit("gate_1_business_rules", "VETO",
                               {"goal_preview": goal[:120], "forbidden_term": term})
                return {"allowed": False, "reason": reason, "audit": audit}

        if REQUIRED_TERMS and not any(t.lower() in goal_lower for t in REQUIRED_TERMS):
            reason = (f"Business rule violation: goal must reference at least one "
                      f"of {REQUIRED_TERMS}.")
            audit = _audit("gate_1_business_rules", "VETO",
                           {"goal_preview": goal[:120], "required_terms": REQUIRED_TERMS})
            return {"allowed": False, "reason": reason, "audit": audit}

        audit = _audit("gate_1_business_rules", "PASS", {"goal_preview": goal[:120]})
        return {"allowed": True, "reason": "Business rules passed.", "audit": audit}


logging.info("Harness loaded — Gate 1 (business rules) and Gate 2 (topology).")
