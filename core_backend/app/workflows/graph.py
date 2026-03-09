from langgraph.graph import StateGraph, START, END
from app.workflows.state import GraphState
from app.workflows.nodes.generate import generate_response
from app.workflows.nodes.tools import execute_basic_tools, execute_xweb_tool

def should_continue(state: GraphState):
    """
    Conditional routing deciding whether to execute basic tools, heavy tools, or end generation
    """
    messages = state.get("messages", [])
    if not messages:
        return END
        
    last_message = messages[-1]
    
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        # Check if any tool is the high-risk xweb instance
        if any(tc["name"] == "create_xweb_instance" for tc in last_message.tool_calls):
            return "xweb_tool"
        return "basic_tools"
        
    return END

workflow = StateGraph(GraphState)

workflow.add_node("agent", generate_response)
workflow.add_node("basic_tools", execute_basic_tools)
workflow.add_node("xweb_tool", execute_xweb_tool)

workflow.add_edge(START, "agent")
workflow.add_conditional_edges("agent", should_continue, {
    "basic_tools": "basic_tools", 
    "xweb_tool": "xweb_tool", 
    END: END
})

# After doing any tool, we go back to agent for generating final message
workflow.add_edge("basic_tools", "agent")
workflow.add_edge("xweb_tool", "agent")

# COMPILE INSTRUCTIONS: we specifically interrupt execution right before hitting the xweb_tool node
agent_graph = workflow.compile(interrupt_before=["xweb_tool"])
