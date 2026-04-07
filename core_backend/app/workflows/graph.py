import logging
from langgraph.graph import StateGraph, START, END
from app.workflows.state import GraphState
from app.workflows.nodes.generate import generate_response
from app.workflows.nodes.tools import execute_tools
from app.workflows.nodes.rag_search import rag_search
from app.workflows.nodes.fetch_profile import fetch_profile
from app.workflows.nodes.profile_analyzer import profile_analyzer
from app.workflows.nodes.summarizer import summarize_history
from app.workflows.nodes.vision_scrubber import scrub_multimodal_content
from app.config.settings import settings
from app.utils.tokens import estimate_tokens

logger = logging.getLogger("langgraph_builder")

MAX_TOOL_CALLS_PER_TURN = 3

# Run profile_analyzer every N turns — avoids LLM call on every message.
# Short messages like "ok", "cảm ơn" are skipped regardless of interval.
PROFILE_ANALYZE_EVERY_N_TURNS = 3
PROFILE_ANALYZE_MIN_CHARS = 30  # Skip extraction if user message too short


def _should_run_profile_analyzer(messages: list) -> bool:
    """
    Returns True only when it's worth spending an LLM call to extract user facts.
    Conditions (both must be true):
      1. Last user message is long enough to contain useful information.
      2. Current turn is a multiple of PROFILE_ANALYZE_EVERY_N_TURNS.
    """
    if not messages:
        return False

    # Find last HumanMessage text
    from langchain_core.messages import HumanMessage
    last_human = next(
        (m for m in reversed(messages) if isinstance(m, HumanMessage)), None
    )
    if not last_human:
        return False

    text = last_human.content if isinstance(last_human.content, str) else ""
    if len(text) < PROFILE_ANALYZE_MIN_CHARS:
        logger.debug(f"PROFILE: Skipping analyzer — message too short ({len(text)} chars).")
        return False

    # Use message pair count as a turn proxy (each turn = 1 human + 1 AI message)
    turn_number = len(messages) // 2
    if turn_number % PROFILE_ANALYZE_EVERY_N_TURNS != 0:
        logger.debug(f"PROFILE: Skipping analyzer — turn {turn_number} not a multiple of {PROFILE_ANALYZE_EVERY_N_TURNS}.")
        return False

    return True


def should_continue(state: GraphState):
    """
    Conditional edge after the agent node.
    Priority order:
      1. Tool calls pending → execute them (with loop guard)
      2. Unprocessed multimodal content → scrub image/audio to text (saves tokens in future turns)
      3. Token threshold exceeded → summarize history
      4. Profiling conditions met → extract user facts
      5. Otherwise → END immediately (no extra LLM call)

    NOTE: vision_scrubber MUST run after agent (not in parallel from START) so the agent
    can see the original image/audio before the scrubber replaces it with a text description.
    """
    messages = state.get("messages", [])
    summary = state.get("summary", "")
    metadata = state.get("metadata", {})
    profile = metadata.get("profile", {})
    tool_call_count = state.get("tool_call_count", 0)

    logger.info(
        f"[MEMORY DEBUG] sid={state.get('session_id')} | "
        f"msgs={len(messages)} | tokens=? | "
        f"profile={profile.get('name', 'N/A')}({len(profile.get('facts', []))} facts) | "
        f"summary_len={len(summary)} | tool_calls={tool_call_count}/{MAX_TOOL_CALLS_PER_TURN}"
    )

    if not messages:
        return END

    last_message = messages[-1]

    # ── 1. Tool call branch ───────────────────────────────────
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        if tool_call_count >= MAX_TOOL_CALLS_PER_TURN:
            logger.warning(
                f"LOOP GUARD: tool_call_count={tool_call_count} hit max={MAX_TOOL_CALLS_PER_TURN}. Forcing END."
            )
            return END  # Drop to END — don't waste another LLM call on loop exit
        if any(tc["name"] == "create_xweb_instance" for tc in last_message.tool_calls):
            return "sensitive_tools"
        return "tools"

    # ── 2. Vision scrubber — runs AFTER agent has seen original image ─
    # Check for any HumanMessage with raw multimodal content (list with image_url/input_audio blocks)
    # that hasn't been scrubbed yet. Client already received message_complete at this point.
    from langchain_core.messages import HumanMessage
    has_unprocessed_multimodal = any(
        isinstance(m, HumanMessage)
        and isinstance(m.content, list)
        and not m.additional_kwargs.get("scrubbed")
        and any(
            isinstance(block, dict) and block.get("type") in ("image_url", "input_audio")
            for block in m.content
        )
        for m in messages
    )
    if has_unprocessed_multimodal:
        logger.info("SCRUBBER: Detected unprocessed multimodal content — routing to vision_scrubber.")
        return "vision_scrubber"

    # ── 3. Summarize if context is getting large ──────────────
    est_tokens = estimate_tokens(messages)
    if est_tokens > settings.SUMMARY_THRESHOLD:
        logger.info(f"MEMORY: {est_tokens} tokens > threshold {settings.SUMMARY_THRESHOLD}. Summarizing.")
        return "summarize_history"

    # ── 4. Profile extraction — only when worthwhile ──────────
    if _should_run_profile_analyzer(messages):
        logger.info("PROFILE: Conditions met — running profile_analyzer.")
        return "profile_analyzer"

    # ── 5. Nothing to do — end immediately ───────────────────
    logger.debug("ROUTER: Normal turn, no side-tasks needed. Ending.")
    return END

workflow = StateGraph(GraphState)

# Nodes
workflow.add_node("fetch_profile", fetch_profile)
workflow.add_node("rag_search", rag_search)
workflow.add_node("agent", generate_response)
workflow.add_node("tools", execute_tools)
workflow.add_node("sensitive_tools", execute_tools) # Same function, different node for HITL
workflow.add_node("profile_analyzer", profile_analyzer)
workflow.add_node("summarize_history", summarize_history)
workflow.add_node("vision_scrubber", scrub_multimodal_content)

# Edges
workflow.add_edge(START, "fetch_profile")
workflow.add_edge(START, "rag_search")
workflow.add_edge("fetch_profile", "agent")
workflow.add_edge("rag_search", "agent")

# vision_scrubber runs AFTER agent (not parallel from START).
# This ensures agent sees the original image before scrubber replaces it with text.
# Client has already received message_complete when scrubber runs (background cleanup).
workflow.add_edge("vision_scrubber", END)

workflow.add_conditional_edges("agent", should_continue, {
    "tools": "tools",
    "sensitive_tools": "sensitive_tools",
    "vision_scrubber": "vision_scrubber",
    "profile_analyzer": "profile_analyzer",
    "summarize_history": "summarize_history",
    END: END,
})

# After tools, go back to agent for final response
workflow.add_edge("tools", "agent")
workflow.add_edge("sensitive_tools", "agent")

# After summarizing, check if profile_analyzer should also run this turn.
# This fixes the mutual-exclusion bug where summarization suppressed profile extraction.
def _after_summarize(state: GraphState):
    if _should_run_profile_analyzer(state.get("messages", [])):
        logger.info("PROFILE: Running profile_analyzer after summarization.")
        return "profile_analyzer"
    return END

workflow.add_conditional_edges("summarize_history", _after_summarize, {
    "profile_analyzer": "profile_analyzer",
    END: END,
})
workflow.add_edge("profile_analyzer", END)


# --- Lazy-init compiled graph with checkpointer ---
_compiled_graph = None
_last_checkpointer_active = None

def get_agent_graph():
    """
    Returns the compiled agent graph.
    Dynamic Checkpointer Awareness: 
    If the checkpointer state changes (e.g. DB initialized or fell back), it recompiles.
    """
    global _compiled_graph, _last_checkpointer_active
    
    from app.utils.db import get_checkpointer
    current_checkpointer = get_checkpointer()
    
    # Recompile only if graph hasn't been built OR checkpointer has changed
    if _compiled_graph is None or current_checkpointer != _last_checkpointer_active:
        if current_checkpointer is None:
            logger.warning("MEM_DEBUG: No checkpointer available. Compiling in EPHEMERAL mode (no memory).")
            _compiled_graph = workflow.compile(interrupt_before=["sensitive_tools"])
        else:
            logger.info(f"MEM_DEBUG: Compiling LangGraph with {type(current_checkpointer).__name__}")
            try:
                _compiled_graph = workflow.compile(
                    checkpointer=current_checkpointer,
                    interrupt_before=["sensitive_tools"]
                )
            except Exception as e:
                logger.error(f"MEM_DEBUG: Compilation failed with checkpointer: {e}. Falling back to No-Memory mode.")
                _compiled_graph = workflow.compile(interrupt_before=["sensitive_tools"])
        
        _last_checkpointer_active = current_checkpointer
        
    return _compiled_graph

