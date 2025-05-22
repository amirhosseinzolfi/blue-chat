import os
import uuid
import operator
import contextlib # Ensure contextlib is imported
from typing import Annotated, Literal

import chainlit as cl # Used for cl.user_session.get in call_llm_node for logging thread_id
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage, RemoveMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END, MessagesState
from langgraph.checkpoint.sqlite import SqliteSaver

# Import logger utilities
from logger_utils import (
    log_info, log_debug, log_workflow, log_state, log_messages, log_langgraph
)

# Agent Configuration
os.environ["OPENAI_API_KEY"] = "324" # This should ideally be managed via environment variables
INITIAL_SYSTEM_PROMPT = "You are a helpful AI. Be concise."
LANGGRAPH_CHECKPOINT_DB_FILE = "./langgraph_checkpoints.sqlite"
MESSAGES_TO_KEEP_AFTER_SUMMARY = 2
NEW_MESSAGES_THRESHOLD_FOR_SUMMARY = 10

log_info("Initializing LangGraph agent with the following configuration:")
log_info("LangGraph checkpoint database", data=LANGGRAPH_CHECKPOINT_DB_FILE)
log_info("Messages threshold for summarization", data=NEW_MESSAGES_THRESHOLD_FOR_SUMMARY)
log_info("Messages to keep after summarization", data=MESSAGES_TO_KEEP_AFTER_SUMMARY)

# LLM Initialization
llm = ChatOpenAI(
    base_url="http://141.98.210.149:15203/v1",
    model_name="gpt-4o",
    temperature=0.5,
    api_key="324" # This should ideally be managed via environment variables
)
log_info("LLM initialized for agent", data={"model": "gpt-4o", "base_url": "http://141.98.210.149:15203/v1"})

def ensure_message_has_id(message: BaseMessage) -> BaseMessage:
    if not hasattr(message, "id") or not isinstance(message.id, str):
        message.id = str(uuid.uuid4())
        log_debug(f"Added ID to message: {message.id}")
    return message

# Agent State
class AgentState(MessagesState):
    summary: str
    messages_since_last_summary: Annotated[int, operator.add]

# Agent Nodes
def call_llm_node(state: AgentState) -> dict:
    # Minor dependency: cl.user_session.get is used for logging here.
    # For stricter separation, this could be removed or thread_id passed differently.
    thread_id = cl.user_session.get("thread_id", "unknown_thread_in_agent_node")
    log_workflow("llm_caller", f"Processing for thread {thread_id}")
    log_state(state)
    
    msgs = []
    summary = state.get("summary", "")
    if summary:
        log_debug("Using conversation summary in prompt", data={"summary": summary})
        msgs.append(ensure_message_has_id(SystemMessage(
            content=f"This is a summary of the conversation so far: {summary}"
        )))
    
    for m in state["messages"]:
        if not isinstance(m, RemoveMessage):
            msgs.append(m)
    
    if not msgs:
        log_debug("No messages found, using default greeting")
        msgs.append(ensure_message_has_id(HumanMessage(content="Hello.")))
    
    log_messages(msgs)
    
    log_debug("Calling LLM")
    resp = llm.invoke(msgs)
    log_debug("LLM response received", data={"content": resp.content})
    
    return {"messages": [ensure_message_has_id(resp)], "messages_since_last_summary": 1}

def should_summarize_node(state: AgentState) -> Literal["summarize_conversation_node", "__end__"]:
    current_count = state.get("messages_since_last_summary", 0)
    should_summarize = current_count >= NEW_MESSAGES_THRESHOLD_FOR_SUMMARY
    
    decision = "summarize_conversation_node" if should_summarize else "__end__"
    log_workflow("should_summarize", 
                f"Decision: {decision}", 
                data={"messages_since_last_summary": current_count, 
                      "threshold": NEW_MESSAGES_THRESHOLD_FOR_SUMMARY})
    return decision

def summarize_conversation_node(state: AgentState) -> dict:
    log_workflow("summarize_conversation", "Starting conversation summarization")
    
    excerpt = [m for m in state["messages"] if isinstance(m, (HumanMessage, AIMessage, SystemMessage))]
    log_debug(f"Found {len(excerpt)} messages to consider for summarization")
    
    existing = state.get("summary", "")
    if existing:
        log_debug("Found existing summary", data={"existing_summary": existing})
    
    header = (
        "Please extend this summary with the new conversation excerpts below.\n"
        if existing else
        "Please create a concise summary of the following conversation:\n"
    )
    
    lines = []
    for m in excerpt:
        role = "Human" if isinstance(m, HumanMessage) else "AI" if isinstance(m, AIMessage) else "System"
        lines.append(f"{role}: {m.content}")
    
    prompt = header
    if existing:
        prompt += f"\nPrevious Summary:\n{existing}\n\nNew Excerpts:\n"
    prompt += "\n".join(lines)
    
    log_debug("Generated summarization prompt", data={"prompt": prompt[:200] + "..." if len(prompt) > 200 else prompt})
    
    resp = llm.invoke([ensure_message_has_id(HumanMessage(content=prompt))])
    new_summary = resp.content.strip()
    log_debug("Generated new summary", data={"new_summary": new_summary})
    
    num_to_remove = max(0, len(excerpt) - MESSAGES_TO_KEEP_AFTER_SUMMARY)
    to_remove = [RemoveMessage(id=m.id) for m in excerpt[:num_to_remove]]
    log_debug(f"Will remove {len(to_remove)} messages from history")
    
    current_messages_since_summary = state.get("messages_since_last_summary", 0)
    log_debug(f"Resetting messages_since_last_summary counter from {current_messages_since_summary} to 0")
    
    result = {
        "summary": new_summary,
        "messages": to_remove,
        "messages_since_last_summary": -current_messages_since_summary
    }
    
    log_workflow("summarize_conversation", "Completed summarization", data=result)
    return result

# Graph Compilation
log_langgraph("Initializing LangGraph checkpoint manager", data={"db_file": LANGGRAPH_CHECKPOINT_DB_FILE})
# SqliteSaver.from_conn_string() returns a context manager.
# We need to enter this context to get the actual checkpointer instance.
_checkpointer_context_manager = SqliteSaver.from_conn_string(LANGGRAPH_CHECKPOINT_DB_FILE)

# Use an ExitStack to manage the checkpointer's lifecycle at the module level.
# The ExitStack will ensure that the checkpointer's __exit__ method (closing the DB connection)
# is called when the Python interpreter shuts down or if the stack is explicitly closed.
_module_exit_stack = contextlib.ExitStack()
checkpointer_instance = _module_exit_stack.enter_context(_checkpointer_context_manager)
# Now, checkpointer_instance is an actual SqliteSaver instance, not a context manager.

log_langgraph("Building LangGraph workflow")
workflow = StateGraph(AgentState)
workflow.add_node("llm_caller", call_llm_node)
workflow.add_node("summarize_conversation_node", summarize_conversation_node)
workflow.set_entry_point("llm_caller")
workflow.add_conditional_edges(
    "llm_caller",
    should_summarize_node,
    {"summarize_conversation_node": "summarize_conversation_node", "__end__": END},
)
workflow.add_edge("summarize_conversation_node", END)

# Compiled LangGraph App
# Pass the actual checkpointer_instance to workflow.compile()
app = workflow.compile(checkpointer=checkpointer_instance)
log_langgraph("LangGraph workflow compiled successfully and ready to be imported.")

# Note: The _module_exit_stack and its managed resources (like the checkpointer_instance's DB connection)
# will persist for the lifetime of the Python process where this module is loaded.
# If this module were part of a system with more complex lifecycle management (e.g., dynamic
# loading/unloading, or specific shutdown sequences), explicit closing of _module_exit_stack
# via `_module_exit_stack.close()` might be required at an appropriate point (e.g., using `atexit` module).
# For typical Chainlit/LangGraph server applications, this module-level setup is generally acceptable.

# Example of how to manage checkpointer context if needed separately (not used for app compilation directly here):
# memory_cm = SqliteSaver.from_conn_string(":memory:")
# graph = StateGraph(AgentState)
# ... define graph ...
# runnable = graph.compile(checkpointer=memory)
# With contextlib.ExitStack() as stack:
#   stack.enter_context(memory) # Manages the __enter__ and __exit__
#   # use runnable
