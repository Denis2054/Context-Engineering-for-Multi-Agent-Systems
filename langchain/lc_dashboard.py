# lc_dashboard.py
# =============================================================================
# Universal Context Engine — LangChain Edition
# The HTML trace dashboard.
#
# The CSS and layout are carried over from the original notebook unchanged.
# Three additions:
#   * the metrics bar shows the provider's own billed token counts (LLM IN /
#     LLM OUT) from usage_metadata, alongside the context-size pills;
#   * a step that failed renders in the failure colour with its error text,
#     instead of the run ending with no visible cause;
#   * a moderation line appears when a pre- or post-flight check ran.
#
# Expect the token numbers to differ from the original notebook's screenshots.
# They are measuring different things, and these ones are exact.
#
# There is no LangChain equivalent for this file. LangSmith is a hosted run
# viewer; this is a self-contained, offline, embeddable audit artifact.
# =============================================================================

import html
import json

import markdown
from IPython.display import HTML, display

CSS = """
<style>
    .dashboard-container {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        background-color: #ffffff;
        border: 3px solid #cbd5e0;
        border-radius: 12px;
        padding: 30px;
        max-width: 100%;
        margin-top: 25px;
        color: #1a202c;
    }
    .header-section {
        border-bottom: 3px solid #2d3748;
        padding-bottom: 20px;
        margin-bottom: 25px;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    .header-title { margin: 0; font-size: 1.8rem; color: #1a202c; font-weight: 900; }
    .header-goal { margin: 10px 0 0 0; color: #2d3748; font-size: 1.2rem; font-style: italic; font-weight: 600;}
    .header-engine { margin: 6px 0 0 0; color: #2b6cb0; font-size: 0.9rem; font-weight: 900; text-transform: uppercase; letter-spacing: 1px;}

    .status-badge {
        padding: 10px 20px;
        border-radius: 8px;
        font-weight: 900;
        font-size: 1rem;
        color: white;
        text-transform: uppercase;
    }
    .status-success { background-color: #22543d; }
    .status-failure { background-color: #742a2a; }

    .metrics-summary {
        margin-top: 10px;
        font-size: 1.1rem;
        font-weight: 900;
        color: #1a202c;
        background: #edf2f7;
        padding: 5px 12px;
        border-radius: 6px;
    }

    .metrics-bar { display: flex; gap: 12px; margin-top: 12px; flex-wrap: wrap; }
    .metric-pill {
        background-color: #ebf4ff;
        color: #1a365d;
        padding: 6px 14px;
        border-radius: 8px;
        border: 2px solid #2b6cb0;
        font-size: 0.95rem;
        font-weight: 900;
    }
    .metric-saved { background-color: #f0fff4; color: #1c4532; border-color: #2f855a; }
    .metric-llm   { background-color: #faf5ff; color: #44337a; border-color: #6b46c1; }
    .metric-error { background-color: #fff5f5; color: #742a2a; border-color: #742a2a; }
    .metric-grow  { background-color: #fffaf0; color: #7b341e; border-color: #c05621; }

    .governance-banner {
        background-color: #fffaf0;
        border: 2px solid #c05621;
        border-left: 8px solid #c05621;
        border-radius: 8px;
        padding: 16px 20px;
        margin-bottom: 25px;
        color: #7b341e;
        font-weight: 700;
        line-height: 1.6;
    }
    .governance-banner .gv-title {
        display: block;
        font-weight: 900;
        text-transform: uppercase;
        letter-spacing: 1px;
        margin-bottom: 8px;
        font-size: 0.9rem;
    }

    .step-card {
        background-color: #ffffff;
        border: 2px solid #2d3748;
        border-radius: 12px;
        margin-bottom: 25px;
        overflow: hidden;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
    }
    .step-card-error { border-color: #742a2a; }
    summary.step-header {
        padding: 20px;
        background-color: #f8fafc;
        cursor: pointer;
        list-style: none;
        display: flex;
        align-items: center;
        justify-content: space-between;
        border-bottom: 2px solid #e2e8f0;
    }
    .step-card-error summary.step-header { background-color: #fff5f5; }
    .agent-badge {
        background-color: #1a202c;
        color: #ffffff;
        padding: 5px 14px;
        border-radius: 6px;
        font-size: 0.85rem;
        font-weight: 900;
        text-transform: uppercase;
        margin-left: 15px;
    }
    .step-card-error .agent-badge { background-color: #742a2a; }

    .step-content { padding: 25px; background-color: #ffffff; }

    .data-label {
        font-size: 1rem;
        text-transform: uppercase;
        color: #1a202c;
        font-weight: 900;
        margin-bottom: 12px;
        display: block;
        border-left: 4px solid #1a202c;
        padding-left: 10px;
    }

    .rendered-content {
        background-color: #ffffff;
        border: 2px solid #e2e8f0;
        border-left: 8px solid #2b6cb0;
        padding: 20px;
        color: #1a202c !important;
        line-height: 1.7;
        font-size: 1.1rem;
        font-weight: 500;
    }
    .rendered-content h1, .rendered-content h2, .rendered-content h3,
    .rendered-content h4, .rendered-content h5, .rendered-content h6 {
        color: #1a202c !important;
        font-weight: 900 !important;
        margin-top: 1.5em;
        margin-bottom: 0.5em;
    }
    .rendered-content strong, .rendered-content b { font-weight: 900; color: #000000; }
    .rendered-error { border-left-color: #742a2a; color: #742a2a !important; font-weight: 700; }

    .json-box {
        background-color: #1a202c;
        color: #f7fafc;
        padding: 20px;
        border-radius: 10px;
        font-family: "SFMono-Regular", Consolas, monospace;
        font-size: 0.95rem;
        overflow-x: auto;
        white-space: pre-wrap;
    }

    .final-output-card {
        border: 5px solid #22543d;
        background-color: #f0fff4;
        border-radius: 12px;
        padding: 30px;
        margin-top: 50px;
        color: #1a202c;
    }
</style>
"""

# Keys that may hold the readable payload when a step returns a dict rather
# than a string. Retained from the original for backward compatibility with
# traces produced by the pre-port engine.
_TEXT_KEYS = ("summary", "answer_with_sources", "answer", "output", "content")


def _md(text):
    """Render text as markdown. Empty values become an explicit placeholder."""
    return markdown.markdown(str(text)) if text else "No content recorded."


def _governance_banner(trace):
    """Render validate_plan() findings. Absent when the plan is compliant."""
    findings = getattr(trace, "plan_warnings", None) or []
    if not findings:
        return ""
    items = "".join(f"<li>{html.escape(str(f))}</li>" for f in findings)
    return (
        '<div class="governance-banner">'
        '<span class="gv-title">\u26a0 Plan governance findings</span>'
        f'<ul style="margin:0; padding-left:20px;">{items}</ul>'
        '</div>'
    )


def _moderation_line(trace):
    """One summary line covering whichever moderation checks actually ran."""
    reports = getattr(trace, "moderation", {}) or {}
    if not reports:
        return ""
    parts = []
    for phase in ("pre", "post"):
        report = reports.get(phase)
        if not report:
            continue
        if not report.get("available", True):
            verdict = "UNAVAILABLE"
        elif report.get("flagged"):
            verdict = "FLAGGED"
        else:
            verdict = "PASS"
        parts.append(f"{phase}-flight {verdict}")
    if not parts:
        return ""
    return f'<div class="metrics-summary">🛡️ MODERATION: {html.escape(" · ".join(parts))}</div>'


def render_trace_dashboard(trace, engine_label="LangGraph Plan-and-Execute"):
    """Render a LangChainTrace as the familiar Context Engine dashboard."""
    status_text = str(getattr(trace, "status", "Unknown"))
    status_class = "status-success" if status_text == "Success" else "status-failure"
    # A failure status carries the full exception text; keep the badge readable
    # and leave the detail to the step card that recorded it.
    badge_text = status_text if len(status_text) <= 40 else status_text[:37] + "..."

    usage = getattr(trace, "usage", {}) or {}
    usage_line = ""
    if usage:
        usage_line = (
            f'<div class="metrics-summary">🧠 BILLED: '
            f'{usage.get("input_tokens", 0)} in / {usage.get("output_tokens", 0)} out '
            f'({usage.get("llm_calls", 0)} calls)</div>'
        )

    out = [CSS, f"""
    <div class="dashboard-container">
        <div class="header-section">
            <div>
                <h1 class="header-title">Context Engine Trace</h1>
                <p class="header-goal">"{html.escape(str(trace.goal))}"</p>
                <p class="header-engine">LangChain Edition &middot; {html.escape(engine_label)}</p>
            </div>
            <div style="text-align: right;">
                <span class="status-badge {status_class}" title="{html.escape(status_text)}">{html.escape(badge_text)}</span>
                <div class="metrics-summary">⏱️ TIME: {getattr(trace, 'duration', 0.0):.2f}s</div>
                {usage_line}
                {_moderation_line(trace)}
            </div>
        </div>
        <div class="steps-container">
            <h2 style="color:#1a202c; margin-bottom:25px; font-size:1.4rem; font-weight:900; text-transform:uppercase;">Execution Workflow</h2>
    """]

    # ---- Governance findings, before anything else --------------------------
    out.append(_governance_banner(trace))

    # ---- The plan, shown before the steps -----------------------------------
    if getattr(trace, "plan", None):
        out.append(f"""
            <details class="step-card">
                <summary class="step-header">
                    <div><span style="font-weight:900; font-size:1.3rem; color:#1a202c;">EXECUTION PLAN</span>
                    <span class="agent-badge">Planner</span></div>
                    <span style="font-weight:900; color:#ffffff; background:#1a202c; padding:6px 14px; border-radius:6px; font-size:0.8rem;">OPEN PLAN</span>
                </summary>
                <div class="step-content">
                    <div class="json-box">{html.escape(json.dumps(trace.plan, indent=2, default=str))}</div>
                </div>
            </details>
        """)

    # ---- Each executed step -------------------------------------------------
    for step in getattr(trace, "steps", []):
        failed = step.get("status") == "error"

        try:
            resolved_ctx = json.dumps(step.get("resolved_context"), indent=2, default=str)
        except Exception:
            resolved_ctx = str(step.get("resolved_context", "N/A"))

        output_raw = step.get("output", "N/A")
        if failed:
            rendered = (
                f'<div class="rendered-content rendered-error">'
                f'{html.escape(str(output_raw))}</div>'
            )
        elif isinstance(output_raw, dict):
            for key in _TEXT_KEYS:
                if isinstance(output_raw.get(key), str):
                    rendered = f'<div class="rendered-content">{_md(output_raw[key])}</div>'
                    break
            else:
                rendered = (
                    f'<div class="json-box">'
                    f'{html.escape(json.dumps(output_raw, indent=2, default=str))}</div>'
                )
        else:
            rendered = f'<div class="rendered-content">{_md(output_raw)}</div>'

        pills = [
            f'<span class="metric-pill">📥 CTX IN: {step.get("tokens_in", "??")}</span>',
            f'<span class="metric-pill">📤 CTX OUT: {step.get("tokens_out", "??")}</span>',
        ]
        if (step.get("tokens_saved") or 0) > 0:
            pills.append(
                f'<span class="metric-pill metric-saved">📉 SAVED: {step["tokens_saved"]}</span>'
            )
        elif str(step.get("agent")) == "Summarizer":
            # A Summarizer whose output exceeds its input has saved nothing.
            # Showing no pill at all reads as a broken counter, so say what
            # actually happened: on short passages the model elaborates.
            grew = (step.get("tokens_out") or 0) - (step.get("tokens_in") or 0)
            if grew > 0:
                pills.append(
                    f'<span class="metric-pill metric-grow">📈 EXPANDED: +{grew}</span>'
                )
        if step.get("llm_in") or step.get("llm_out"):
            pills.append(
                f'<span class="metric-pill metric-llm">🧠 LLM: '
                f'{step.get("llm_in", 0)} in / {step.get("llm_out", 0)} out</span>'
            )
        else:
            pills.append('<span class="metric-pill metric-llm">🧠 LLM: retrieval only</span>')
        if failed:
            pills.append('<span class="metric-pill metric-error">⛔ FAILED</span>')

        out.append(f"""
            <details class="step-card{' step-card-error' if failed else ''}" open>
                <summary class="step-header">
                    <div style="display:flex; flex-direction:column; align-items:flex-start;">
                        <div>
                            <span style="font-weight:900; font-size:1.3rem; color:#1a202c;">STEP {step.get('step')}</span>
                            <span class="agent-badge">{html.escape(str(step.get('agent')))}</span>
                        </div>
                        <div class="metrics-bar">{''.join(pills)}</div>
                    </div>
                    <span style="font-weight:900; color:#ffffff; background:#1a202c; padding:6px 14px; border-radius:6px; font-size:0.8rem;">OPEN LOGS</span>
                </summary>
                <div class="step-content">
                    <div style="margin-bottom:30px;">
                        <span class="data-label">Input Context (State)</span>
                        <details><summary style="font-size:0.9rem; font-weight:900; color:#2b6cb0; cursor:pointer; margin-bottom:10px;">▶ View Resolved Source Data</summary>
                        <div class="json-box">{html.escape(resolved_ctx)}</div></details>
                    </div>
                    <div>
                        <span class="data-label">Agent Output</span>
                        {rendered}
                    </div>
                </div>
            </details>
        """)

    # ---- Final result -------------------------------------------------------
    if getattr(trace, "final_output", None):
        final_content = trace.final_output
        if isinstance(final_content, dict):
            final_content = final_content.get(
                "summary", final_content.get("content", str(final_content))
            )
        out.append(f"""
        <div class="final-output-card">
            <div style="color:#1c4532; font-size:1.5rem; font-weight:1000; margin-bottom:20px; text-transform:uppercase; letter-spacing:2px; border-bottom:3px solid #22543d; padding-bottom:12px;">Final Orchestration Result</div>
            <div style="font-size:1.25rem; font-weight:700; line-height:1.8;">{markdown.markdown(str(final_content))}</div>
        </div>
        """)

    out.append("</div></div>")
    display(HTML("".join(out)))
