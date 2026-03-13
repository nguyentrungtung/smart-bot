import logging
from langgraph.graph import StateGraph, START, END
from app.workflows.state import GraphState
from app.workflows.nodes.generate import generate_response
from app.workflows.nodes.tools import execute_tools
from app.workflows.nodes.rag_search import rag_search
from app.workflows.nodes.fetch_profile import fetch_profile
from app.workflows.nodes.profile_analyzer import profile_analyzer
from app.workflows.nodes.summarizer import summarize_history
from app.config.settings import settings

logger = logging.getLogger("langgraph_builder")

def should_continue(state: GraphState):
    """
    Conditional routing deciding whether to execute tools or perform side tasks.
    Splits between standard tools and sensitive tools (HITL).
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
    
    # Tool Calling Branch
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        # Check if any tool is high-risk (e.g. provisioning)
        if any(tc["name"] == "create_xweb_instance" for tc in last_message.tool_calls):
            return "sensitive_tools"
        return "tools"
        
    # OPTIMIZATION: Only summarize if tokens exceed threshold
    from app.utils.tokens import estimate_tokens
        
    est_tokens = estimate_tokens(messages)
    if est_tokens > settings.SUMMARY_THRESHOLD:
        logger.info(f"MEMORY: Tokens ({est_tokens}) exceed threshold ({settings.SUMMARY_THRESHOLD}). Routing to summarizer.")
        return "summarize_history"
        
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

# Edges
workflow.add_edge(START, "fetch_profile")
workflow.add_edge(START, "rag_search")
workflow.add_edge("fetch_profile", "agent")
workflow.add_edge("rag_search", "agent")

workflow.add_conditional_edges("agent", should_continue, {
    "tools": "tools", 
    "sensitive_tools": "sensitive_tools",
    "profile_analyzer": "profile_analyzer",
    "summarize_history": "summarize_history",
    END: END
})

# After tools, always go back to agent
workflow.add_edge("tools", "agent")
workflow.add_edge("sensitive_tools", "agent")

# Terminal nodes
workflow.add_edge("summarize_history", END)
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
            _compiled_graph = workflow.compile(interrupt_before=["sensitive_tools"])
        else:
            logger.info("Compiling LangGraph with AsyncPostgresSaver checkpointer — Short-Term Memory ENABLED")
            _compiled_graph = workflow.compile(
                checkpointer=checkpointer,
                interrupt_before=["sensitive_tools"]
            )
    return _compiled_graph
