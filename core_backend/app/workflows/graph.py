import logging
from langgraph.graph import StateGraph, START, END
from app.workflows.state import GraphState
from app.workflows.nodes.generate import generate_response
from app.workflows.nodes.tools import execute_basic_tools, execute_xweb_tool
from app.workflows.nodes.rag_search import rag_search
from app.workflows.nodes.fetch_profile import fetch_profile
from app.workflows.nodes.profile_analyzer import profile_analyzer

logger = logging.getLogger("langgraph_builder")

def should_continue(state: GraphState):
    """
    Conditional routing deciding whether to execute basic tools, heavy tools, or perform profile syncing.
    """
    messages = state.get("messages", [])
    if not messages:
        return "profile_analyzer"
        
    last_message = messages[-1]
    
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        # Check if any tool is the high-risk xweb instance
        if any(tc["name"] == "create_xweb_instance" for tc in last_message.tool_calls):
            return "xweb_tool"
        return "basic_tools"
        
    # When no more tools are called, we finish the turn
    return END

workflow = StateGraph(GraphState)

# Nodes
workflow.add_node("fetch_profile", fetch_profile)
workflow.add_node("rag_search", rag_search)
workflow.add_node("agent", generate_response)
workflow.add_node("basic_tools", execute_basic_tools)
workflow.add_node("xweb_tool", execute_xweb_tool)
workflow.add_node("profile_analyzer", profile_analyzer)

# Edges
# Full Lifecycle: Start -> Fetch Profile -> RAG Search -> Agent Generation
workflow.add_edge(START, "fetch_profile")
workflow.add_edge("fetch_profile", "rag_search")
workflow.add_edge("rag_search", "agent")

workflow.add_conditional_edges("agent", should_continue, {
    "basic_tools": "basic_tools", 
    "xweb_tool": "xweb_tool", 
    "profile_analyzer": "profile_analyzer",
    END: END
})

# After doing any tool, we go back to agent for generating final message
workflow.add_edge("basic_tools", "agent")
workflow.add_edge("xweb_tool", "agent")

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
