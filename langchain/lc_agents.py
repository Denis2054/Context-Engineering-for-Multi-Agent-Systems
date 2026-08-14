# lc_agents.py
# =============================================================================
# Universal Context Engine — LangChain Edition
# The four specialists, rebuilt as LangChain tools backed by LCEL chains.
#
# Replaces: agents.py
#
#   agent_context_librarian() -> Librarian   (retriever, no LLM call)
#   agent_researcher()        -> Researcher  (high-fidelity RAG with citations)
#   agent_summarizer()        -> Summarizer  (context reduction)
#   agent_writer()            -> Writer      (blueprint + source -> final text)
#
# Two structural changes, both improvements:
#
#   1. The MCP envelope is gone. Tools take typed arguments and return strings,
#      so agent_writer's twenty lines of defensive unpacking (is it a dict? does
#      it have 'facts'? 'summary'? 'answer_with_sources'?) simply disappear.
#      Note that create_mcp_message() was an internal convention resembling the
#      Model Context Protocol, not an implementation of it. Replacing it with
#      typed tool signatures loses no protocol conformance.
#
#   2. The docstrings ARE the capability description. LangChain generates the
#      JSON schema the Planner sees from the function signature and docstring,
#      so registry.get_capabilities_description() no longer has to be written or
#      maintained by hand, and can never drift out of sync with the code.
#
# All system prompts are copied verbatim from the original agents.py so that
# outputs remain comparable.
# =============================================================================

from __future__ import annotations

import json
import logging

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

# =============================================================================
# Prompts (verbatim from the original engine)
#
# NOTE ON CURLY BRACES: inside a ChatPromptTemplate, { and } mark a variable.
# Any literal brace in prompt text must be doubled ({{ and }}). None of these
# prompts contain literal braces, but check any prompt you add.
# =============================================================================

RESEARCH_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "You are an expert research synthesis AI. Your task is to provide a clear, "
     "factual answer to the user's topic based *only* on the provided source "
     "texts. After the answer, you MUST provide a \"Sources\" section listing "
     "the unique source document names you used."),
    ("human",
     "Topic: {topic}\n\nSources:\n{sources}\n\n--- \n"
     "Synthesize your answer and list the source documents now."),
])

SUMMARY_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "You are an expert summarization AI. Your task is to reduce the provided "
     "text to its essential points, guided by the user's specific objective. "
     "The summary must be concise, accurate, and directly address the stated goal."),
    ("human",
     "--- OBJECTIVE ---\n{objective}\n\n"
     "--- TEXT TO SUMMARIZE ---\n{text}\n--- END TEXT ---\n\n"
     "Generate the summary now."),
])

WRITER_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "You are an expert content generation AI. Your task is to generate or "
     "rewrite content based on the provided SOURCE MATERIAL, strictly following "
     "the rules in the SEMANTIC BLUEPRINT. The SOURCE MATERIAL may contain both "
     "a synthesized answer and a list of sources; ensure the final output is a "
     "single, cohesive piece of content."),
    ("human",
     "--- SEMANTIC BLUEPRINT (JSON) ---\n{blueprint}\n\n"
     "--- SOURCE MATERIAL ({label}) ---\n{source}\n\n"
     "Generate the final content now."),
])

DEFAULT_BLUEPRINT = json.dumps({"instruction": "Generate the content neutrally."})

NO_DATA_MESSAGE = "No data found on the topic."
ALL_TAINTED_MESSAGE = (
    "Could not generate a reliable answer as retrieved data was suspect."
)


# =============================================================================
# Factory
# =============================================================================

def build_agents(llm, blueprint_retriever, knowledge_retriever, sanitize):
    """
    Build the four specialist tools.

    Dependencies (model, retrievers, sanitizer) are captured in closures. This
    replaces registry.get_handler()'s if/elif dependency-injection ladder: each
    tool simply closes over what it needs, so there is no dispatch table and no
    chance of injecting the wrong argument set into the wrong agent.
    """

    research_chain = RESEARCH_PROMPT | llm | StrOutputParser()
    summary_chain = SUMMARY_PROMPT | llm | StrOutputParser()
    writer_chain = WRITER_PROMPT | llm | StrOutputParser()

    # -------------------------------------------------------------------------
    # 1. Librarian — retrieves a Semantic Blueprint. No LLM call.
    # -------------------------------------------------------------------------
    @tool
    def Librarian(intent_query: str, config: RunnableConfig = None) -> str:
        """Retrieve the Semantic Blueprint that defines the style, tone and
        structure of the required output. Call this FIRST whenever the goal asks
        for content to be written, rewritten, styled, or pitched — the Writer
        must never be invoked without a blueprint from this agent. Give it a
        descriptive phrase of the desired style or document type, for example
        "a formal structured legal summary" or "a persuasive marketing pitch".
        Returns the blueprint as a JSON string."""
        logging.info("[Librarian] Activated. Analyzing intent...")
        docs = blueprint_retriever.invoke(intent_query, config=config)

        if not docs:
            logging.warning("[Librarian] No specific blueprint found. Returning default.")
            return DEFAULT_BLUEPRINT

        doc = docs[0]
        # Identify the blueprint for the audit log. Ingestion does not always
        # write an 'id' field, so fall back to 'description' before giving up:
        # a trace line reading "blueprint 'unknown'" is not an audit record.
        doc_id = (getattr(doc, "id", None)
                  or doc.metadata.get("id")
                  or doc.metadata.get("description")
                  or "unidentified")

        # text_key='blueprint_json' puts the blueprint into page_content.
        # The metadata fallback covers records stored under a different key; if
        # BOTH are empty the text_key is misconfigured, which is worth saying
        # out loud rather than silently degrading to the default blueprint.
        blueprint = doc.page_content or doc.metadata.get("blueprint_json")
        if not blueprint:
            logging.error(
                "[Librarian] Blueprint '%s' retrieved with EMPTY content. This "
                "almost always means text_key is wrong for the ContextLibrary "
                "namespace (expected 'blueprint_json'). Falling back to default.",
                doc_id,
            )
            return DEFAULT_BLUEPRINT

        logging.info(f"[Librarian] Found blueprint '{doc_id}'.")
        return blueprint

    # -------------------------------------------------------------------------
    # 2. Researcher — high-fidelity RAG with per-chunk sanitization + citations.
    # -------------------------------------------------------------------------
    @tool
    def Researcher(topic_query: str, config: RunnableConfig = None) -> str:
        """Retrieve and synthesize factual information on a topic from the
        knowledge base. Use this whenever the goal requires facts, quotations,
        clauses, or any grounded content. Returns the synthesized answer
        followed by a Sources section naming the documents used."""
        logging.info("[Researcher] Activated. Investigating topic with high fidelity...")
        docs = knowledge_retriever.invoke(topic_query, config=config)

        if not docs:
            logging.warning("[Researcher] No relevant information found.")
            return NO_DATA_MESSAGE

        # Sanitize EACH chunk. A poisoned chunk is dropped; the rest still work.
        clean_texts, sources = [], set()
        skipped, empty = 0, 0
        for doc in docs:
            if not (doc.page_content or "").strip():
                empty += 1
                continue
            try:
                clean_texts.append(sanitize(doc.page_content))
                if "source" in doc.metadata:
                    sources.add(doc.metadata["source"])
            except ValueError as e:
                skipped += 1
                # Name the document and the pattern. A skipped chunk is an audit
                # event: "something was rejected" is not actionable, "this
                # document matched this pattern" is. The run continues on the
                # surviving chunks, and the rejected source is NOT cited.
                logging.warning(
                    "[Researcher] REJECTED chunk from '%s' (pattern: %s). "
                    "Continuing with the remaining chunks; this source will not "
                    "be cited.",
                    doc.metadata.get("source", "unknown source"),
                    getattr(e, "pattern", "unspecified"),
                )
                continue

        if empty:
            logging.error(
                "[Researcher] %d of %d retrieved chunks had EMPTY page_content. "
                "This almost always means text_key is wrong for the KnowledgeStore "
                "namespace (expected 'text').",
                empty, len(docs),
            )

        if not clean_texts:
            logging.error("[Researcher] No usable chunks survived. Aborting.")
            return ALL_TAINTED_MESSAGE

        logging.info(
            f"[Researcher] {len(clean_texts)} of {len(docs)} chunks usable "
            f"({skipped} sanitized out, {empty} empty). Synthesizing with citations..."
        )
        findings = research_chain.invoke(
            {"topic": topic_query, "sources": "\n\n---\n\n".join(clean_texts)},
            config=config,
        )

        # Append the source list programmatically as well, for robustness: the
        # model is instructed to cite, but the citation must not depend on it.
        cited = "\n".join(f"- {s}" for s in sorted(sources))
        return f"{findings}\n\n**Sources:**\n{cited}" if cited else findings

    # -------------------------------------------------------------------------
    # 3. Summarizer — context reduction before an expensive generation step.
    # -------------------------------------------------------------------------
    @tool
    def Summarizer(text_to_summarize: str, summary_objective: str,
                   config: RunnableConfig = None) -> str:
        """Reduce a long text to a concise summary guided by a specific
        objective, for example "Extract key technical specifications". Use this
        to control token counts before handing material to the Writer."""
        logging.info("[Summarizer] Activated. Reducing context...")
        if not text_to_summarize or not summary_objective:
            raise ValueError(
                "Summarizer requires 'text_to_summarize' and 'summary_objective'."
            )
        return summary_chain.invoke(
            {"objective": summary_objective, "text": text_to_summarize},
            config=config,
        )

    # -------------------------------------------------------------------------
    # 4. Writer — applies a blueprint to source material.
    # -------------------------------------------------------------------------
    @tool
    def Writer(blueprint: str, facts: str = "", previous_content: str = "",
               config: RunnableConfig = None) -> str:
        """Generate or rewrite the final content by applying a Semantic
        Blueprint to source material. The 'blueprint' argument MUST come from a
        preceding Librarian step, normally as $$STEP_1_OUTPUT$$; a Writer step
        with no Librarian before it is an invalid plan. Supply also either
        'facts' (from the Researcher or Summarizer) or 'previous_content'
        (existing text to be rewritten). This is normally the last step."""
        logging.info("[Writer] Activated. Applying blueprint to source material...")

        source = facts or previous_content
        label = "SOURCE MATERIAL" if facts else "PREVIOUS CONTENT (For Rewriting)"

        if not blueprint or not source:
            raise ValueError(
                "Writer requires a blueprint and either 'facts' or 'previous_content'."
            )

        return writer_chain.invoke(
            {"blueprint": blueprint, "source": source, "label": label},
            config=config,
        )

    return [Librarian, Researcher, Summarizer, Writer]


logging.info("LangChain specialist agents defined.")
