# =============================================================================
# dashboard_nim.py  —  The Glass Box
# Universal Context Engine — DAG Edition · NIM
#
# Copyright 2025-2026, Denis Rothman
#
# ROLE IN THE SYSTEM
# ------------------
# Rendering only. Every number, every gate verdict, and every node payload on
# screen is read from the ExecutionTrace; nothing here computes, infers, or
# re-derives anything. If a value is not in the trace it does not appear.
#
# That constraint is worth stating because it is what makes the dashboard
# trustworthy. A dashboard that recalculates its own totals can disagree with
# the audit record it claims to display, and when they disagree the pretty one
# usually wins the argument. Here they cannot disagree, because there is only
# one source.
#
# WHY A GLASS BOX AND NOT A PROGRESS BAR
# --------------------------------------
# The failure mode this exists to prevent is a confident answer built on
# nothing: a Researcher that retrieved zero chunks, a Librarian that fell back
# to a neutral blueprint, a Summarizer that discarded the clause the Writer
# needed. All three produce fluent, plausible final output. None is visible
# unless you can open the node and read what actually went in and came out.
#
# Hence: every node expands. The resolved input is shown as the agent received
# it, after $$ref$$ substitution, which is usually where the surprise is.
#
# The output is plain inline-styled HTML — no external CSS, no JavaScript, no
# CDN. It renders identically in Colab, JupyterLab, VS Code, and a saved .html
# export, and it keeps working when the notebook is read offline.
# =============================================================================

import html as html_lib
import json

from IPython.display import HTML, display


# =============================================================================
# SECTION A — PALETTE
#
# One colour per domain, used everywhere that domain appears: node badges, card
# borders, the topology table. On an eight-node multi-domain run the colour is
# how you see the shape of the work — which parts were Legal, which Marketing,
# where they converge — before reading a single label.
# =============================================================================

DOMAIN_COLORS = {
    "General"   : ("#2b6cb0", "#ebf8ff"),
    "Legal"     : ("#6b46c1", "#faf5ff"),
    "Marketing" : ("#c05621", "#fffaf0"),
    "Finance"   : ("#276749", "#f0fff4"),
    "HR"        : ("#b7791f", "#fffff0"),
    "Compliance": ("#702459", "#fff5f7"),
    "Research"  : ("#2c7a7b", "#e6fffa"),
}

NVIDIA_GREEN = "#76b900"


# =============================================================================
# SECTION B — COMPONENTS
# =============================================================================

def _domain_badge(domain):
    """Coloured pill naming a governance domain."""
    border, bg = DOMAIN_COLORS.get(domain, ("#4a5568", "#edf2f7"))
    return (f"<span style='background:{bg};color:{border};border:2px solid {border};"
            f"padding:3px 10px;border-radius:6px;font-weight:900;"
            f"font-size:0.8rem;text-transform:uppercase'>{html_lib.escape(str(domain))}</span>")


def _agent_badge(agent):
    """Dark pill naming the agent that ran."""
    return (f"<span style='background:#1a202c;color:#fff;padding:3px 12px;"
            f"border-radius:6px;font-weight:900;font-size:0.8rem;"
            f"text-transform:uppercase'>{html_lib.escape(str(agent))}</span>")


def _status_badge(status):
    """Overall verdict. Anything that is not a success reads as a failure."""
    ok = "success" in str(status).lower()
    bg = "#22543d" if ok else "#742a2a"
    label = "SUCCESS" if ok else "VETOED / FAILED"
    return (f"<span style='background:{bg};color:#fff;padding:6px 18px;"
            f"border-radius:8px;font-weight:900;font-size:0.9rem'>{label}</span>")


def _pill(label, value, accent="#2b6cb0", bg="#ebf8ff"):
    """A labelled metric."""
    return (f"<span style='background:{bg};color:{accent};border:2px solid {accent};"
            f"padding:4px 12px;border-radius:8px;font-weight:900;font-size:0.9rem;"
            f"margin-right:8px;display:inline-block;margin-bottom:6px'>"
            f"{label}: <b>{value}</b></span>")


def _nim_badge(planner_model, agent_model):
    """
    Which models actually served this run.

    Worth having on screen. The two-model split is invisible in the output —
    the artefact does not announce which model wrote it — so the header is the
    only place the reader can confirm that planning and execution were served
    by different models.
    """
    def short(name):
        if not name:
            return "n/a"
        tail = name.split("/")[-1]
        return tail[:38] + ("..." if len(tail) > 38 else "")

    return (f"<span style='background:{NVIDIA_GREEN};color:#fff;padding:5px 14px;"
            f"border-radius:8px;font-weight:900;font-size:0.82rem;"
            f"font-family:monospace'>NIM &nbsp;|&nbsp; planner: "
            f"{html_lib.escape(short(planner_model))} &nbsp;|&nbsp; agents: "
            f"{html_lib.escape(short(agent_model))}</span>")


def _fmt_output(value):
    """Full agent output. Never truncated — this is the audit surface."""
    text = json.dumps(value, indent=2, default=str) if isinstance(value, (dict, list)) \
        else (str(value) if value is not None else "(none)")
    return (f"<pre style='background:#1a202c;color:#f7fafc;padding:16px;"
            f"border-radius:8px;font-size:0.9rem;overflow-x:auto;"
            f"white-space:pre-wrap;word-break:break-word'>"
            f"{html_lib.escape(text)}</pre>")


def _fmt_input(value):
    """
    Resolved input, capped at 900 characters.

    Truncated where the output is not, because a resolved input often embeds an
    entire upstream document and the useful information — which keys were
    populated, whether a $$ref$$ resolved at all — is visible in the opening
    lines. A literal "$$some_node$$" surviving into this panel is the signature
    of a planner that referenced a node it did not declare a dependency on.
    """
    text = json.dumps(value, indent=2, default=str) if isinstance(value, (dict, list)) else str(value)
    if len(text) > 900:
        text = text[:900] + "\n... [truncated for display]"
    return (f"<pre style='background:#2d3748;color:#e2e8f0;padding:14px;"
            f"border-radius:8px;font-size:0.85rem;overflow-x:auto;"
            f"white-space:pre-wrap;word-break:break-word'>"
            f"{html_lib.escape(text)}</pre>")


def render_dag_topology(dag):
    """
    The plan as the planner wrote it, before any of it ran.

    Read the dependency annotations rather than the node names: every node
    marked "no dependencies" was in the first wave and executed concurrently
    with its siblings. That is where the wall-clock saving comes from, and it
    is visible here before you look at a single timing number.
    """
    if not dag:
        return ""

    rows = []
    for node in dag:
        domain     = node.get("domain", "General")
        border, bg = DOMAIN_COLORS.get(domain, ("#4a5568", "#edf2f7"))
        deps       = node.get("depends_on", [])
        dep_str = (
            " &nbsp;&larr; depends on: <code>" + ", ".join(html_lib.escape(d) for d in deps) + "</code>"
            if deps else
            " &nbsp;<i style='color:#4a5568'>(no dependencies — runs in the first wave)</i>"
        )
        rows.append(
            f"<div style='margin:5px 0;padding:10px 16px;background:{bg};"
            f"border-left:5px solid {border};border-radius:6px;font-family:monospace'>"
            f"<b style='color:{border}'>{html_lib.escape(node['id'])}</b> &nbsp;&nbsp;"
            f"{_agent_badge(node['agent'])} {_domain_badge(domain)}"
            f"<span style='color:#4a5568;font-size:0.85rem'>{dep_str}</span></div>"
        )

    return (f"<div style='border:2px solid #2d3748;border-radius:10px;padding:20px;"
            f"margin:16px 0;background:#f8fafc'>"
            f"<div style='font-weight:900;font-size:1rem;color:#1a202c;margin-bottom:12px;"
            f"border-left:4px solid #1a202c;padding-left:10px'>"
            f"EXECUTION DAG — {len(dag)} NODE(S)</div>{''.join(rows)}</div>")


def render_gate_card(gate_num, result):
    """
    One gate verdict, with its reason.

    A veto without a reason is an outage as far as the user is concerned. The
    reason string is the difference between "the system refused" and "the
    system refused because of this, which you can change."
    """
    if not result:
        return ""
    ok     = result.get("allowed", False)
    color  = "#22543d" if ok else "#742a2a"
    bg     = "#f0fff4" if ok else "#fff5f5"
    symbol = "PASS" if ok else "VETO"
    reason = html_lib.escape(str(result.get("reason", "")))
    names  = {1: "Gate 1 — business rules (pre-planning)",
              2: "Gate 2 — topology (post-planning, pre-execution)"}
    return (f"<div style='border:2px solid {color};background:{bg};border-radius:8px;"
            f"padding:14px 20px;margin:8px 0'>"
            f"<b style='color:{color}'>{symbol} &nbsp;{names.get(gate_num, f'Gate {gate_num}')}</b>"
            f"<div style='color:{color};font-size:0.92rem;margin-top:4px'>{reason}</div></div>")


# =============================================================================
# SECTION C — THE DASHBOARD
# =============================================================================

def render_trace_dashboard(trace, gate1_result=None, gate2_result=None,
                           planner_model=None, agent_model=None):
    """
    Render a complete ExecutionTrace.

    Args:
        trace:         an ExecutionTrace, or anything exposing summary().
        gate1_result:  optional override. Normally omitted — the trace carries
                       its own verdicts and those are preferred.
        gate2_result:  optional override.
        planner_model: shown in the header badge.
        agent_model:   shown in the header badge.

    Layout, top to bottom: goal and verdict, models, metrics, gate cards, the
    plan, then every node expandable, then the final output. Deliberately in
    that order — governance decisions appear above the content they governed,
    so a veto cannot be scrolled past.
    """
    s = trace.summary()

    # Trace-carried verdicts win. An explicit argument is a fallback for
    # callers that gated the goal themselves before invoking the engine.
    g1 = s.get("gate1_result") or gate1_result
    g2 = s.get("gate2_result") or gate2_result

    pills = (
        _pill("Nodes",   s["dag_nodes"]) +
        _pill("Steps",   s["steps_complete"]) +
        _pill("Tok in",  s["tokens_in"],  "#276749", "#f0fff4") +
        _pill("Tok out", s["tokens_out"], "#276749", "#f0fff4") +
        _pill("Tok saved", s["tokens_saved"], "#702459", "#fff5f7") +
        _pill("Wall clock", f"{s['duration_s']:.2f}s", "#4a5568", "#edf2f7")
    )
    # Only meaningful when the DAG had a concurrent wave; suppressed otherwise
    # rather than shown as a misleading zero.
    if s.get("wall_clock_saved_s", 0) > 0.5:
        pills += _pill("Saved by concurrency",
                       f"{s['wall_clock_saved_s']:.2f}s", NVIDIA_GREEN, "#f7fee7")

    step_cards = ""
    for step in s["steps"]:
        domain     = step.get("domain", "General")
        border, bg = DOMAIN_COLORS.get(domain, ("#4a5568", "#edf2f7"))

        step_pills = (_pill("in", step["tokens_in"], "#2b6cb0", "#ebf8ff") +
                      _pill("out", step["tokens_out"], "#276749", "#f0fff4"))
        if step.get("duration_s"):
            step_pills += _pill("time", f"{step['duration_s']:.2f}s", "#4a5568", "#edf2f7")
        if step.get("tokens_saved"):
            step_pills += _pill("saved", step["tokens_saved"], "#702459", "#fff5f7")

        step_cards += (
            f"<details style='border:2px solid {border};border-radius:10px;"
            f"margin-bottom:18px;overflow:hidden'>"
            f"<summary style='padding:16px 20px;background:{bg};cursor:pointer;"
            f"list-style:none;display:flex;align-items:center;"
            f"justify-content:space-between;flex-wrap:wrap;gap:8px'>"
            f"<span><b style='font-size:1rem;color:{border};font-family:monospace'>"
            f"{html_lib.escape(step['node_id'])}</b> &nbsp;&nbsp;"
            f"{_agent_badge(step['agent'])} {_domain_badge(domain)}</span>"
            f"<span>{step_pills}</span></summary>"
            f"<div style='padding:20px;background:#fff'>"
            f"<div style='font-weight:900;color:#1a202c;margin-bottom:6px;"
            f"border-left:4px solid #4a5568;padding-left:8px'>"
            f"RESOLVED INPUT &nbsp;<span style='font-weight:400;font-size:0.8rem;"
            f"color:#4a5568'>(after $$ref$$ substitution — exactly what the agent "
            f"received)</span></div>"
            f"{_fmt_input(step['resolved_input'])}"
            f"<div style='font-weight:900;color:#1a202c;margin:16px 0 6px;"
            f"border-left:4px solid {border};padding-left:8px'>OUTPUT</div>"
            f"{_fmt_output(step['output'])}</div></details>"
        )

    if not step_cards:
        step_cards = ("<i style='color:#4a5568'>No nodes executed. "
                      "See the gate verdicts above for why.</i>")

    nim_html = (f"<div style='margin-bottom:14px'>{_nim_badge(planner_model, agent_model)}</div>"
                if planner_model else "")

    final_html = _fmt_output(s["final_output"]) if s["final_output"] else "<i>None</i>"

    display(HTML(
        f"<div style='font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif;"
        f"background:#fff;border:3px solid #cbd5e0;border-radius:12px;padding:30px;"
        f"max-width:100%;margin-top:25px;color:#1a202c'>"

        f"<div style='border-bottom:3px solid #2d3748;padding-bottom:20px;"
        f"margin-bottom:24px;display:flex;justify-content:space-between;"
        f"align-items:flex-start;gap:16px;flex-wrap:wrap'>"
        f"<div><h2 style='margin:0;font-size:1.5rem;font-weight:900'>"
        f"Universal Context Engine — DAG Edition &middot; NIM</h2>"
        f"<p style='margin:8px 0 0;color:#2d3748;font-style:italic;font-size:1.02rem'>"
        f"{html_lib.escape(s['goal'])}</p></div>"
        f"{_status_badge(s['status'])}</div>"

        f"{nim_html}"
        f"<div style='margin-bottom:18px'>{pills}</div>"
        f"{render_gate_card(1, g1)}{render_gate_card(2, g2)}"
        f"{render_dag_topology(s.get('dag') or [])}"

        f"<div style='font-weight:900;font-size:1.05rem;border-left:5px solid #1a202c;"
        f"padding-left:12px;margin:24px 0 16px'>STEP-BY-STEP EXECUTION TRACE "
        f"<span style='font-weight:400;font-size:0.85rem;color:#4a5568'>"
        f"(click a node to expand)</span></div>"
        f"{step_cards}"

        f"<div style='border:4px solid #22543d;background:#f0fff4;border-radius:10px;"
        f"padding:24px;margin-top:30px'>"
        f"<div style='font-weight:900;font-size:1.05rem;color:#22543d;margin-bottom:12px;"
        f"border-left:5px solid #22543d;padding-left:10px'>FINAL OUTPUT</div>"
        f"{final_html}</div></div>"
    ))


# =============================================================================
# SECTION D — STATIC INSPECTORS
#
# Live engine state, rendered without executing anything. Free to run at any
# point, and the fastest way to answer "what can this engine actually do" and
# "what is it allowed to do".
# =============================================================================

def render_registry_inspector(registry, topology_dag, adapter,
                              planner_model=None, agent_model=None,
                              embedding_model=None, max_concurrent=None):
    """
    Show the registry, the topology, the NIM configuration, and the adapter.

    Reading the registry and the topology together is the useful move: the
    registry says which agents exist, the topology says which of them may hand
    work to which others. A capability the topology forbids is, in practice,
    not a capability.
    """
    reg_rows = "".join(
        f"<tr><td style='font-family:monospace;padding:6px 12px;color:#2b6cb0'>"
        f"{html_lib.escape(k)}</td>"
        f"<td style='padding:6px 12px;font-family:monospace'>{html_lib.escape(v['function'])}</td>"
        f"<td style='padding:6px 12px'>{_domain_badge(v['domain'])}</td></tr>"
        for k, v in sorted(registry.get_registry_description().items())
    )
    reg_html = (
        "<table style='border-collapse:collapse;width:100%;font-size:0.93rem'>"
        "<thead><tr style='background:#2d3748;color:#fff'>"
        "<th style='padding:8px 12px;text-align:left'>Registry key</th>"
        "<th style='padding:8px 12px;text-align:left'>Function</th>"
        "<th style='padding:8px 12px;text-align:left'>Domain</th>"
        f"</tr></thead><tbody>{reg_rows}</tbody></table>"
    )

    topo_rows = "".join(
        f"<tr><td style='font-family:monospace;padding:6px 12px;font-weight:700'>"
        f"{html_lib.escape(src)}</td>"
        f"<td style='padding:6px 12px'>"
        f"{', '.join(html_lib.escape(t) for t in tgts) if tgts else '<i>(terminal — never initiates)</i>'}"
        f"</td></tr>"
        for src, tgts in sorted(topology_dag.items())
    )
    topo_html = (
        "<table style='border-collapse:collapse;width:100%;font-size:0.93rem;margin-top:8px'>"
        "<thead><tr style='background:#6b46c1;color:#fff'>"
        "<th style='padding:8px 12px;text-align:left'>Source domain</th>"
        "<th style='padding:8px 12px;text-align:left'>May hand work to</th>"
        f"</tr></thead><tbody>{topo_rows}</tbody></table>"
    )

    cfg_rows = "".join(
        f"<tr><td style='padding:4px 12px;font-weight:700'>{label}</td>"
        f"<td style='padding:4px 12px;font-family:monospace'>{html_lib.escape(str(value))}</td></tr>"
        for label, value in [
            ("Planner model", planner_model or "not set"),
            ("Agent model", agent_model or "not set"),
            ("Embedding model", embedding_model or "not set"),
            ("Max concurrent nodes", max_concurrent if max_concurrent is not None else "not set"),
        ]
    )
    cfg_html = (
        f"<div style='background:#f7fee7;border:2px solid {NVIDIA_GREEN};border-radius:8px;"
        f"padding:16px 20px;margin-top:20px'>"
        f"<div style='font-weight:900;color:#4d7c0f;margin-bottom:8px'>NIM configuration</div>"
        f"<table style='border-collapse:collapse;width:100%;font-size:0.9rem'>"
        f"{cfg_rows}</table></div>"
    )

    adapter_html = (
        "<pre style='background:#1a202c;color:#f7fafc;padding:16px;"
        "border-radius:8px;margin-top:8px;font-size:0.88rem;white-space:pre-wrap'>"
        + html_lib.escape(json.dumps(adapter.describe(), indent=2)) + "</pre>"
    )

    display(HTML(
        "<div style='font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif;"
        "color:#1a202c'>"
        "<h3 style='margin-top:0'>Agent registry</h3>" + reg_html +
        "<h3 style='margin-top:24px'>Governance topology</h3>" + topo_html +
        cfg_html +
        "<h3 style='margin-top:24px'>Adapter capabilities</h3>" + adapter_html +
        "</div>"
    ))


def render_plan_preview(plan_result, planner_model=None):
    """
    Render the output of engine.plan_only(): both gate verdicts and the DAG,
    with nothing executed.

    The header states the cost explicitly. One planning call is cheap enough
    that plan-only should be the default way to iterate on prompts, capability
    descriptions, and topology rules — you get the same governance verdicts
    for a fraction of the price of a run.
    """
    dag = plan_result.get("dag") or []
    g1  = plan_result.get("gate1")
    g2  = plan_result.get("gate2")

    if plan_result.get("would_execute"):
        verdict, color, bg = "WOULD EXECUTE", "#22543d", "#f0fff4"
    elif plan_result.get("error"):
        verdict, color, bg = "PLANNING FAILED", "#742a2a", "#fff5f5"
    else:
        verdict, color, bg = "WOULD BE VETOED", "#742a2a", "#fff5f5"

    err_html = (
        f"<div style='background:#fff5f5;border:2px solid #742a2a;border-radius:8px;"
        f"padding:14px 20px;margin:8px 0;color:#742a2a;font-family:monospace;"
        f"font-size:0.9rem'>{html_lib.escape(str(plan_result['error']))}</div>"
        if plan_result.get("error") else ""
    )

    model_html = (
        f"<div style='margin-bottom:14px'>{_nim_badge(planner_model, None)}</div>"
        if planner_model else ""
    )

    display(HTML(
        f"<div style='font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif;"
        f"background:#fff;border:3px solid #cbd5e0;border-radius:12px;padding:26px;"
        f"margin-top:20px;color:#1a202c'>"
        f"<div style='display:flex;justify-content:space-between;align-items:flex-start;"
        f"gap:16px;flex-wrap:wrap;border-bottom:3px solid #2d3748;padding-bottom:16px;"
        f"margin-bottom:18px'>"
        f"<div><h3 style='margin:0;font-weight:900'>Plan preview — nothing executed</h3>"
        f"<p style='margin:6px 0 0;font-style:italic;color:#2d3748'>"
        f"{html_lib.escape(plan_result.get('goal', ''))}</p>"
        f"<p style='margin:6px 0 0;font-size:0.85rem;color:#4a5568'>"
        f"Cost: one planning call. No agents ran.</p></div>"
        f"<span style='background:{color};color:#fff;padding:6px 18px;border-radius:8px;"
        f"font-weight:900;font-size:0.88rem'>{verdict}</span></div>"
        f"{model_html}{err_html}"
        f"{render_gate_card(1, g1)}{render_gate_card(2, g2)}"
        f"{render_dag_topology(dag)}"
        f"</div>"
    ))


print("Dashboard functions loaded.")
