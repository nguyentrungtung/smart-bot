import logging
from langgraph.graph import StateGraph, START, END
from app.workflows.state import GraphState
from app.workflows.nodes.generate import generate_response
from app.workflows.nodes.tools import execute_basic_tools, execute_xweb_tool
from app.workflows.nodes.rag_search import rag_search
from app.workflows.nodes.fetch_profile import fetch_profile
from app.workflows.nodes.profile_analyzer import profile_analyzer
from app.workflows.nodes.summarizer import summarize_history
from app.config.settings import settings

logger = logging.getLogger("langgraph_builder")

def should_continue(state: GraphState):
    """
    Conditional routing deciding whether to execute basic tools, heavy tools, or perform profile syncing.
    """
    messages = state.get("messages", [])
    summary = state.get("summary", "")
    metadata = state.get("metadata", {})
    profile = metadata.get("profile", {})

    # DEBUG LOGS: Detailed Memory State (As requested by user)
    logger.info(f"""
    --- [MEMORY DEBUG] ---
    Thread ID: {state.get('session_id')}
    Profile: {profile.get('name', 'N/A')} ({len(profile.get('facts', []))} facts)
    Summary: {summary[:100]}... (len={len(summary)})
    Msg History: {len(messages)} messages total
    Last Msg: {messages[-1].content[:50] if messages else 'None'}
    ----------------------
    """)

    if not messages:
        return "profile_analyzer"
        
    last_message = messages[-1]
    
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        # Check if any tool is the high-risk xweb instance
        if any(tc["name"] == "create_xweb_instance" for tc in last_message.tool_calls):
            return "xweb_tool"
        return "basic_tools"
        
    # OPTIMIZATION: Only summarize if tokens exceed threshold
    def estimate_tokens(msgs):
        text = "".join([str(m.content) for m in msgs])
        return len(text.split()) * 1.3
        
    if estimate_tokens(messages) > settings.SUMMARY_THRESHOLD:
        logger.info(f"MEMORY: Tokens exceed {settings.SUMMARY_THRESHOLD}, routing to summarizer.")
        return "summarize_history"
        
    # When no more tools are called and no summary needed, we finish the turn
    return END

workflow = StateGraph(GraphState)

# Nodes
workflow.add_node("fetch_profile", fetch_profile)
workflow.add_node("rag_search", rag_search)
workflow.add_node("agent", generate_response)
workflow.add_node("basic_tools", execute_basic_tools)
workflow.add_node("xweb_tool", execute_xweb_tool)
workflow.add_node("profile_analyzer", profile_analyzer)
workflow.add_node("summarize_history", summarize_history)

# Edges
# Full Lifecycle: Start -> Fetch Profile -> RAG Search -> Agent Generation
workflow.add_edge(START, "fetch_profile")
workflow.add_edge("fetch_profile", "rag_search")
workflow.add_edge("rag_search", "agent")

workflow.add_conditional_edges("agent", should_continue, {
    "basic_tools": "basic_tools", 
    "xweb_tool": "xweb_tool", 
    "profile_analyzer": "profile_analyzer",
    "summarize_history": "summarize_history",
    END: END
})

# After doing any tool, we go back to agent for generating final message
workflow.add_edge("basic_tools", "agent")
workflow.add_edge("xweb_tool", "agent")

# After summarization, we finish the turn
workflow.add_edge("summarize_history", END)

# After syncing profile, finish the turn
workflow.add_edge("profile_analyzer", END)

# --- Lazy-init compiled graph with checkpointer ---
_compiled_graph = None

def get_agent_graph():
    """
    Returns the compiled agent graph WITH the Postgres checkpointer.
    Must be called AFTER app lifespan has initialized db.checkpointer.
    This enables short-term memory: LangGraph auto-loads/saves message history per thread_id.
    """
    global _compiled_graph
    if _compiled_graph is None:
        from app.utils.db import get_checkpointer
        checkpointer = get_checkpointer()
        if checkpointer is None:
            logger.error("CRITICAL: Checkpointer is None! Memory will NOT work. Is the DB pool initialized?")
            # Fallback: compile without checkpointer (no memory)
            _compiled_graph = workflow.compile(interrupt_before=["xweb_tool"])
        else:
            logger.info("Compiling LangGraph with AsyncPostgresSaver checkpointer — Short-Term Memory ENABLED")
            _compiled_graph = workflow.compile(
                checkpointer=checkpointer,
                interrupt_before=["xweb_tool"]
            )
    return _compiled_graph
