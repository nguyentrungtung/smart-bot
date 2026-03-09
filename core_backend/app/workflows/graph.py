from langgraph.graph import StateGraph, START, END
from app.workflows.state import GraphState
from app.workflows.nodes.generate import generate_response
from app.workflows.nodes.tools import execute_tools

def should_continue(state: GraphState):
    """
    Conditional routing deciding whether to execute tools or end generation
    """
    messages = state.get("messages", [])
    if not messages:
        return END
        
    last_message = messages[-1]
    
    # If there are tool calls to run natively
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
        
    return END

workflow = StateGraph(GraphState)

workflow.add_node("agent", generate_response)
workflow.add_node("tools", execute_tools)

workflow.add_edge(START, "agent")
workflow.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})

# After doing tools, we go back to agent for generating final message
workflow.add_edge("tools", "agent")

agent_graph = workflow.compile()
