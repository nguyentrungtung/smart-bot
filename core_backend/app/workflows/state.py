from typing import TypedDict, Annotated
import operator
from langchain_core.messages import BaseMessage

class GraphState(TypedDict):
    """
    State schema for the LangGraph agent.
    Maintains message history and injected user session context.
    """
    messages: Annotated[list[BaseMessage], operator.add]
    session_id: str
    user_id: str
