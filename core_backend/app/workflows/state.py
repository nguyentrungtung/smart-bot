from typing import TypedDict, Annotated, List, Dict, Any
import operator
from langchain_core.messages import BaseMessage

def merge_metadata(old: Dict[str, Any], new: Dict[str, Any]) -> Dict[str, Any]:
    """Reducer to merge metadata dicts in parallel nodes."""
    return {**old, **new}

class GraphState(TypedDict):
    """
    State schema for the LangGraph agent.
    Maintains message history and injected user session context.
    """
    messages: Annotated[list[BaseMessage], operator.add]
    session_id: str
    user_id: str
    # Holds RAG results
    rag_documents: List[str]
    # Hybrid Memory: Cumulative summary of older messages
    summary: str
    # Holds raw thinking process before final response is generated
    thinking: List[str]
    # Generic metadata for future extensions
    metadata: Annotated[Dict[str, Any], merge_metadata]


