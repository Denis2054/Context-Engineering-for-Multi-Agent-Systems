# =============================================================================
# agents_nim.py  —  The Four Specialist Agents
# Universal Context Engine — DAG Edition · NIM
#
# Copyright 2025-2026, Denis Rothman
#
# ROLE IN THE SYSTEM
# ------------------
# Four functions. Each takes an MCP envelope, does one thing, and returns an
# MCP envelope. None of them knows the DAG exists, which node called it, or
# what runs next. That ignorance is the design: the Foreman can schedule these
# in any order, in parallel, or across process boundaries, because none of them
# holds state between calls.
#
#   Librarian    ContextLibrary -> a Semantic Blueprint (how to write)
#   Researcher   KnowledgeStore -> synthesised findings with citations (what is true)
#   Summarizer   long text      -> short text against a stated objective
#   Writer       blueprint + facts -> the finished artefact
#
# THE LIBRARIAN / RESEARCHER SPLIT
# --------------------------------
# Both are retrieval agents; they read different namespaces for different
# reasons and that separation is the core idea of the Context Engine.
#
#   ContextLibrary holds blueprints — brand voice, document structure, tone
#   rules. Style. There is one right answer, so top_k=1.
#
#   KnowledgeStore holds source documents — specs, contracts, press releases.
#   Substance. Synthesis benefits from corroboration, so top_k=3.
#
# Collapsing the two would mean asking a single similarity search to serve two
# incompatible notions of relevance. Keeping them apart is what lets the Writer
# apply Marketing's voice to Legal's facts without either contaminating the
# other.
#
# WHERE SANITISATION LIVES
# ------------------------
# The Harness sanitises the user's GOAL at Gate 1, before the planner runs.
# The Researcher sanitises RETRIEVED CHUNKS, individually, before they enter a
# prompt. These are different threats and both gates are required.
#
# A goal-level check cannot protect you from a poisoned document, because the
# poisoned text was not in the goal — it arrived later, from your own vector
# store, selected by a similarity search. The Legal fixture in this repo
# includes exactly that case: a chunk of NDA text carrying an embedded
# instruction. Watch the Researcher drop it and continue with the survivors.
# =============================================================================

import json
import logging

from helpers import query_pinecone, call_llm_robust, create_mcp_message


# =============================================================================
# AGENT 1 — CONTEXT LIBRARIAN
#
# Retrieves the Semantic Blueprint: a JSON object describing how the output
# should read, retrieved by meaning rather than by key. Asking for "an
# authoritative legal summary" finds the right blueprint without anyone
# maintaining a lookup table of intent strings.
#
# Has no dependencies, so it is always in the first ready set and runs
# concurrently with the Researchers.
# =============================================================================

def agent_context_librarian(mcp_message, client, index, embedding_model,
                            namespace_context):
    """
    Retrieve a Semantic Blueprint from the ContextLibrary namespace.

    Args:
        mcp_message (dict):     envelope; content requires "intent_query".
        client:                 embedding credential holder.
        index:                  Pinecone Index handle.
        embedding_model (str):  must match the index.
        namespace_context (str): resolved by the adapter, normally "ContextLibrary".

    Returns:
        dict: MCP envelope, content {"blueprint_json": <json string>}.

    A miss is not an error. Returning a neutral default keeps the Writer
    running with no style contract rather than failing the whole DAG — a
    degraded artefact beats no artefact.
    """
    logging.info("[Librarian] activated — analysing intent.")
    try:
        requested_intent = mcp_message["content"].get("intent_query")
        if not requested_intent:
            raise ValueError("Librarian requires 'intent_query' in the input content.")

        results = query_pinecone(
            query_text      = requested_intent,
            namespace       = namespace_context,
            top_k           = 1,               # one blueprint, one voice
            index           = index,
            client          = client,
            embedding_model = embedding_model,
        )

        if results:
            match = results[0]
            logging.info(
                f"[Librarian] blueprint '{match['id']}' "
                f"(score {match['score']:.3f})"
            )
            content = {"blueprint_json": match["metadata"]["blueprint_json"]}
        else:
            logging.warning("[Librarian] no blueprint matched — using neutral default.")
            content = {
                "blueprint_json": json.dumps(
                    {"instruction": "Generate the content neutrally."}
                )
            }

        return create_mcp_message("Librarian", content)

    except Exception as e:
        logging.error(f"[Librarian] {e}")
        raise


# =============================================================================
# AGENT 2 — RESEARCHER  (High-Fidelity RAG)
#
# Four stages, and the second is the one worth studying:
#
#   1. retrieve   top_k=3 from the domain's knowledge namespace
#   2. screen     sanitise each chunk INDIVIDUALLY; drop failures, keep the rest
#   3. synthesise answer strictly from surviving chunks
#   4. attribute  append the source document names actually used
#
# Per-chunk screening rather than all-or-nothing is a deliberate choice. One
# poisoned paragraph in a three-chunk retrieval should cost you that paragraph,
# not the entire node. Only when every chunk fails does the agent give up — and
# it says so explicitly rather than returning a confident answer built on
# nothing.
#
# One function, three registry entries. The same code is registered as
# Researcher, Legal:Researcher, and Marketing:Researcher. What differs is the
# namespace the registry resolves for each domain and the governance edges the
# Harness enforces around it. The agent is generic; the domain is configuration.
# =============================================================================

def agent_researcher(mcp_message, client, index, generation_model,
                     embedding_model, namespace_knowledge):
    """
    Retrieve, screen, and synthesise factual content with source citations.

    Args:
        mcp_message (dict):      envelope; content requires "topic_query".
        client:                  credential holder for embeddings and generation.
        index:                   Pinecone Index handle.
        generation_model (str):  agent model — Nano on the NIM path.
        embedding_model (str):   must match the index.
        namespace_knowledge (str): resolved per domain by the registry.

    Returns:
        dict: MCP envelope, content {"answer_with_sources": <str>}.
    """
    # Imported locally so the second sanitisation site is impossible to miss
    # when reading this function on its own.
    from helpers import helper_sanitize_input

    logging.info("[Researcher] activated — high-fidelity retrieval.")
    try:
        topic = mcp_message["content"].get("topic_query")
        if not topic:
            raise ValueError("Researcher requires 'topic_query' in the input content.")

        # ---- 1. retrieve -------------------------------------------------
        results = query_pinecone(
            query_text      = topic,
            namespace       = namespace_knowledge,
            top_k           = 3,               # corroboration, not just recall
            index           = index,
            client          = client,
            embedding_model = embedding_model,
        )

        if not results:
            logging.warning("[Researcher] no matches in the knowledge store.")
            return create_mcp_message(
                "Researcher",
                {"answer_with_sources": "No data found on the topic.", "sources": []},
            )

        # ---- 2. screen each chunk independently ---------------------------
        sanitized_texts, sources, rejected = [], set(), 0
        for match in results:
            try:
                clean = helper_sanitize_input(match["metadata"].get("text", ""))
                sanitized_texts.append(clean)
                if "source" in match["metadata"]:
                    sources.add(match["metadata"]["source"])
            except ValueError as e:
                rejected += 1
                logging.warning(
                    f"[Researcher] chunk '{match['id']}' rejected by the "
                    f"sanitizer and dropped. Reason: {e}"
                )
                continue

        if rejected:
            logging.warning(
                f"[Researcher] {rejected} of {len(results)} chunk(s) dropped. "
                f"Synthesising from the {len(sanitized_texts)} that survived."
            )

        if not sanitized_texts:
            # Every chunk failed. Say so plainly. Do not invent an answer.
            logging.error("[Researcher] all chunks failed screening — aborting node.")
            return create_mcp_message(
                "Researcher",
                {
                    "answer_with_sources": (
                        "Could not generate a reliable answer — every retrieved "
                        "chunk failed injection screening."
                    ),
                    "sources": [],
                },
            )

        # ---- 3. synthesise, grounded only in what survived ----------------
        logging.info(f"[Researcher] synthesising {len(sanitized_texts)} clean chunk(s).")

        system_prompt = (
            "You are an expert research synthesis AI. Provide a clear, factual "
            "answer to the user's topic based *only* on the provided source texts. "
            "Do not introduce facts that are not present in the sources. "
            "After the answer, provide a 'Sources' section listing the unique "
            "source document names you used."
        )

        source_material = "\n\n---\n\n".join(sanitized_texts)
        user_prompt = (
            f"Topic: {topic}\n\n"
            f"Sources:\n{source_material}\n\n"
            f"---\nSynthesize your answer and list the source documents now."
        )

        findings = call_llm_robust(
            system_prompt, user_prompt,
            client           = client,
            generation_model = generation_model,
        )

        # ---- 4. attribute -------------------------------------------------
        # Citations come from Pinecone metadata, not from the model. A model
        # asked to cite its sources will cheerfully invent a plausible filename.
        final_output = (
            f"{findings}\n\n**Sources:**\n"
            + "\n".join(f"- {s}" for s in sorted(sources))
        )

        return create_mcp_message("Researcher", {"answer_with_sources": final_output})

    except Exception as e:
        logging.error(f"[Researcher] {e}")
        raise


# =============================================================================
# AGENT 3 — SUMMARIZER
#
# The token gatekeeper, and the node that most clearly justifies having a DAG
# rather than a chain.
#
# A Researcher returning three full document chunks can hand the Writer several
# thousand tokens of raw material. Inserting a Summarizer between them turns
# that into a few hundred tokens aimed at a stated objective. The trace records
# the difference as `tokens_saved`, which is the only number in the dashboard
# that maps directly to money.
#
# The objective matters as much as the text. "Summarise this" produces a
# generic abstract; "summarise this for a compliance reviewer checking
# confidentiality obligations" produces a summary that keeps the clauses the
# Writer will actually need.
# =============================================================================

def agent_summarizer(mcp_message, client, generation_model):
    """
    Reduce text against an explicit objective.

    Args:
        mcp_message (dict):     envelope; content requires "text_to_summarize"
                                and "summary_objective".
        client:                 credential holder.
        generation_model (str): agent model — Nano on the NIM path.

    Returns:
        dict: MCP envelope, content {"summary": <str>}.
    """
    logging.info("[Summarizer] activated — reducing context.")
    try:
        text_to_summarize = mcp_message["content"].get("text_to_summarize")
        summary_objective = mcp_message["content"].get("summary_objective")

        if not text_to_summarize or not summary_objective:
            raise ValueError(
                "Summarizer requires both 'text_to_summarize' and "
                "'summary_objective' in the input content."
            )

        # Upstream output may arrive as a dict rather than a string, because the
        # $$node_id$$ resolver substitutes whole agent outputs. Flatten it here
        # rather than making the planner responsible for reaching into shapes.
        if isinstance(text_to_summarize, dict):
            text_to_summarize = (
                text_to_summarize.get("answer_with_sources")
                or text_to_summarize.get("summary")
                or json.dumps(text_to_summarize)
            )

        system_prompt = (
            "You are an expert summarization AI. Reduce the provided text to its "
            "essential points, guided by the user's specific objective. The summary "
            "must be concise, accurate, and directly serve the stated goal. Preserve "
            "any source attributions present in the original."
        )

        user_prompt = (
            f"--- OBJECTIVE ---\n{summary_objective}\n\n"
            f"--- TEXT TO SUMMARIZE ---\n{text_to_summarize}\n"
            f"--- END TEXT ---\n\nGenerate the summary now."
        )

        summary = call_llm_robust(
            system_prompt, user_prompt,
            client           = client,
            generation_model = generation_model,
        )

        return create_mcp_message("Summarizer", {"summary": summary})

    except Exception as e:
        logging.error(f"[Summarizer] {e}")
        raise


# =============================================================================
# AGENT 4 — WRITER
#
# The confluence node. Takes style from the Librarian and substance from the
# Researcher or Summarizer and produces the artefact. Almost always terminal,
# and therefore almost always the value in `final_output`.
#
# The input unpacking below is defensive on purpose. Upstream nodes return
# different shapes — the Researcher returns {"answer_with_sources": ...}, the
# Summarizer returns {"summary": ...}, and a planner may wire either into the
# `facts` slot. Rather than constraining the planner to know these shapes, the
# Writer accepts all of them. Tolerance at the confluence point buys freedom
# everywhere upstream.
# =============================================================================

def agent_writer(mcp_message, client, generation_model):
    """
    Apply a Semantic Blueprint to source material and produce final content.

    Args:
        mcp_message (dict):     envelope; content requires "blueprint" plus
                                either "facts" or "previous_content".
        client:                 credential holder.
        generation_model (str): agent model — Nano on the NIM path.

    Returns:
        dict: MCP envelope whose content is the finished text.
    """
    logging.info("[Writer] activated — applying blueprint to source material.")
    try:
        blueprint_data   = mcp_message["content"].get("blueprint")
        facts_data       = mcp_message["content"].get("facts")
        previous_content = mcp_message["content"].get("previous_content")

        # The blueprint may arrive as the Librarian's whole envelope content or
        # as the bare JSON string, depending on how the planner wired the ref.
        blueprint_json_string = (
            blueprint_data.get("blueprint_json")
            if isinstance(blueprint_data, dict)
            else blueprint_data
        )

        # Accept every shape an upstream node might produce.
        facts = None
        if isinstance(facts_data, dict):
            facts = (
                facts_data.get("facts")
                or facts_data.get("summary")
                or facts_data.get("answer_with_sources")
            )
        elif isinstance(facts_data, str):
            facts = facts_data

        if not blueprint_json_string or (not facts and not previous_content):
            raise ValueError(
                "Writer requires a blueprint and either 'facts' or 'previous_content'."
            )

        if facts:
            source_material, source_label = facts, "SOURCE MATERIAL"
        else:
            source_material, source_label = previous_content, "PREVIOUS CONTENT (for rewriting)"

        system_prompt = (
            "You are an expert content generation AI. Generate or rewrite content "
            "based on the provided SOURCE MATERIAL, strictly following the rules in "
            "the SEMANTIC BLUEPRINT. The SOURCE MATERIAL may contain both a "
            "synthesized answer and a list of sources; produce a single cohesive "
            "piece of content and preserve source attribution where the blueprint "
            "calls for it."
        )

        user_prompt = (
            f"--- SEMANTIC BLUEPRINT (JSON) ---\n{blueprint_json_string}\n\n"
            f"--- {source_label} ---\n{source_material}\n\n"
            f"Generate the final content now."
        )

        final_output = call_llm_robust(
            system_prompt, user_prompt,
            client           = client,
            generation_model = generation_model,
        )

        return create_mcp_message("Writer", final_output)

    except Exception as e:
        logging.error(f"[Writer] {e}")
        raise


logging.info("Specialist agents loaded (Harness owns goal sanitization).")
