# langgraph_agent.py 

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

# Import logger utilities with the new functions
from logger_utils import (
    log_info, log_debug, log_workflow, log_state, log_messages, log_langgraph,
    log_conversation, flush_conversation_log
)

# Agent Configuration
os.environ["OPENAI_API_KEY"] = "324" # This should ideally be managed via environment variables
INITIAL_SYSTEM_PROMPT = """name : blue (بلو)
* **Role:** The AI is a personal, intelligent Persian assistant that supports users in achieving their goals.
* **Guard-rails:** Cite only best practices; avoid hallucinations and irrelevant content; follow all user requirements strictly.
* **Persistent Context:**

  * Prompt-stack hierarchy
  * Retrieval-Augmented Generation (RAG)
  * Token-efficiency strategies
* **Style/Format Rules:**

  * Tone: friendly, cool, smart, engaging
  * Always answer in Persian
  * use proper and structured markdown format in a conversational like text structure 
  * Use relevant emojis(just if needed) to enhance engagement
  * Max 120 words per system instruction"""
LANGGRAPH_CHECKPOINT_DB_FILE = "./langgraph_checkpoints.sqlite"
MESSAGES_TO_KEEP_AFTER_SUMMARY = 2
NEW_MESSAGES_THRESHOLD_FOR_SUMMARY = 10

log_info("Initializing LangGraph agent with the following configuration:")
log_info("LangGraph checkpoint database", data=LANGGRAPH_CHECKPOINT_DB_FILE)
log_info("Messages threshold for summarization", data=NEW_MESSAGES_THRESHOLD_FOR_SUMMARY)
log_info("Messages to keep after summarization", data=MESSAGES_TO_KEEP_AFTER_SUMMARY)

# LLM Initialization (fallback default)
llm = ChatOpenAI(
    base_url="http://localhost:15401/v1",  # Updated to use g4f API on port 15401
    model_name="gpt-4o",
    temperature=0.5,
    streaming=True,
    api_key="324" # This should ideally be managed via environment variables
)
log_info("LLM initialized for agent", data={"model": "gpt-4o", "base_url": "http://localhost:15401/v1"})

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
    thread_id = cl.user_session.get("thread_id", "unknown_thread_in_agent_node")
    log_workflow("llm_caller", f"Processing for thread {thread_id}")
    log_state(state)
    
    # 1️⃣ Read the user-selected model from session
    model_name = cl.user_session.get("llm_model", "gpt-4o")
    
    msgs = []
    summary = state.get("summary", "")
    system_instruction = INITIAL_SYSTEM_PROMPT
    
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
    
    # Log messages in a safe way
    log_debug(f"Processing {len(msgs)} messages")
    for i, msg in enumerate(msgs):
        content_preview = ""
        if isinstance(msg.content, str):
            content_preview = msg.content[:50] + "..." if len(msg.content) > 50 else msg.content
        elif isinstance(msg.content, list):
            # For multimodal content, show content type structure
            content_preview = f"Multimodal content with {len(msg.content)} parts: " + ", ".join([part.get('type', 'unknown') for part in msg.content])
        log_debug(f"Message {i+1}: {type(msg).__name__} - {content_preview}")
    
    log_debug("Calling LLM")
    # 2️⃣ Instantiate ChatOpenAI dynamically with the selected model
    dynamic_llm = ChatOpenAI(
        base_url="http://localhost:15401/v1",  # Updated to use g4f API on port 15401
        model_name=model_name,
        temperature=0.5,
        api_key=os.environ["OPENAI_API_KEY"]
    )
    
    # Construct a representation of the final prompt for logging
    final_prompt = f"System: {system_instruction}\n"
    if summary:
        final_prompt += f"Summary: {summary}\n"
    final_prompt += "\nMessages:\n"
    for msg in msgs:
        if hasattr(msg, "__class__") and hasattr(msg.__class__, "__name__"):
            role = msg.__class__.__name__.replace("Message", "")
            content = msg.content
            if isinstance(content, list):
                # Handle multimodal content for display
                content_parts = []
                for part in content:
                    if isinstance(part, dict):
                        if part.get("type") == "text":
                            content_parts.append(part.get("text", ""))
                        elif part.get("type") == "image_url":
                            content_parts.append("[Image content]")
                content = "\n".join(content_parts)
            final_prompt += f"{role}: {content}\n"
    
    # Call the LLM
    resp = dynamic_llm.invoke(msgs)
    
    # Log response safely
    resp_content_preview = ""
    if isinstance(resp.content, str):
        resp_content_preview = resp.content[:50] + "..." if len(resp.content) > 50 else resp.content
    elif isinstance(resp.content, list):
        resp_content_preview = f"Multimodal response with {len(resp.content)} parts"
    log_debug("LLM response received", data={"content_preview": resp_content_preview})
    
    # Store the conversation log but don't display it yet
    ai_response = resp.content
    if isinstance(ai_response, list):
        # Extract text from multimodal response
        text_parts = []
        for part in ai_response:
            if isinstance(part, dict) and part.get("type") == "text":
                text_parts.append(part.get("text", ""))
        ai_response = "\n".join(text_parts)
    
    log_conversation(
        thread_id=thread_id,
        model_name=model_name,
        system_instruction=system_instruction,
        history_summary=summary,
        messages=msgs,
        final_prompt=final_prompt,
        ai_response=ai_response
    )
    
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
        
        # Extract text content properly from potentially multimodal messages
        content_text = ""
        if isinstance(m.content, str):
            content_text = m.content
        elif isinstance(m.content, list):
            # Extract text parts from multimodal messages
            for part in m.content:
                if isinstance(part, dict) and part.get("type") == "text":
                    content_text += part.get("text", "")
            if not content_text:
                content_text = "[Contains image or non-text content]"
        
        lines.append(f"{role}: {content_text}")
    
    prompt = header
    if existing:
        prompt += f"\nPrevious Summary:\n{existing}\n\nNew Excerpts:\n"
    prompt += "\n".join(lines)
    
    log_debug("Generated summarization prompt", data={"prompt": prompt[:200] + "..." if len(prompt) > 200 else prompt})
    
    # Use dynamic LLM for summarization as well
    model_name = cl.user_session.get("llm_model", "gpt-4o")
    dynamic_llm = ChatOpenAI(
        base_url="http://localhost:15401/v1",  # Updated to use g4f API on port 15401
        model_name=model_name,
        temperature=0.5,
        api_key=os.environ["OPENAI_API_KEY"]
    )
    resp = dynamic_llm.invoke([ensure_message_has_id(HumanMessage(content=prompt))])
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
_checkpointer_context_manager = SqliteSaver.from_conn_string(LANGGRAPH_CHECKPOINT_DB_FILE)
_module_exit_stack = contextlib.ExitStack()
checkpointer_instance = _module_exit_stack.enter_context(_checkpointer_context_manager)

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
app = workflow.compile(checkpointer=checkpointer_instance)
log_langgraph("LangGraph workflow compiled successfully and ready to be imported.")
