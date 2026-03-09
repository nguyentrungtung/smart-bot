from app.workflows.state import GraphState
from langchain_core.messages import AIMessage
import logging

logger = logging.getLogger(__name__)

# Very basic LLM placeholder that will utilize LiteLLM logic soon
class LLMProxyWrapper:
    async def ainvoke(self, state, *args, **kwargs):
        # We simulate a text response here
        return AIMessage(content="Simulated text directly from wrapper")

llm = LLMProxyWrapper()

async def generate_response(state: GraphState) -> dict:
    """
    Core AI generation node.
    Passes state explicitly to the LiteLLM proxy instance, along with tool definitions.
    """
    messages = state.get("messages", [])
    
    # We await the mock invocation which returnsAIMessage 
    response = await llm.ainvoke(messages)
    
    # Return delta update for the LangGraph state
    return {"messages": [response]}
