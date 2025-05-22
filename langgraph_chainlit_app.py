import os
import uuid
import operator
import sqlite3
import contextlib
from typing import Annotated, Optional, Literal

import chainlit as cl
from chainlit.data.sql_alchemy import SQLAlchemyDataLayer
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage, RemoveMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END, MessagesState
from langgraph.checkpoint.sqlite import SqliteSaver

# Import our rich logger utility
from logger_utils import (
    log_info, log_warning, log_error, log_debug, 
    log_chainlit, log_langgraph, log_auth, log_data, 
    log_workflow, log_state, log_messages, 
    timing_decorator, session_logger, divider
)

# -----------------------------------------------------------------------------
# 1) Data Persistence & In-Place Schema Migration
# -----------------------------------------------------------------------------
@cl.data_layer
@timing_decorator
def get_data_layer():
    log_data("Initializing SQLAlchemy data layer")
    db_file = "./chatbot_messagesstate_v2.sqlite" # Database for Chainlit's data
    conn = sqlite3.connect(db_file)
    cur = conn.cursor()

    log_data(f"Connected to database: {db_file}")
    
    # Enable WAL mode and a busy timeout
    cur.execute("PRAGMA journal_mode=WAL;")
    cur.execute("PRAGMA busy_timeout=10000;")
    log_data("Configured SQLite with WAL mode and busy timeout")

    # 1a) Create Chainlit tables if they don't exist
    log_data("Creating or verifying required tables")
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS users (
      id TEXT PRIMARY KEY,
      identifier TEXT NOT NULL UNIQUE ON CONFLICT IGNORE,
      metadata TEXT NOT NULL,
      createdAt TEXT
    );
    CREATE TABLE IF NOT EXISTS threads (
      id TEXT PRIMARY KEY,
      createdAt TEXT,
      name TEXT,
      userId TEXT,
      userIdentifier TEXT,
      tags TEXT,
      metadata TEXT,
      FOREIGN KEY (userId) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS elements (
      id TEXT PRIMARY KEY,
      threadId TEXT,
      type TEXT,
      url TEXT,
      chainlitKey TEXT,
      name TEXT NOT NULL,
      display TEXT,
      objectKey TEXT,
      size TEXT,
      page INTEGER,
      language TEXT,
      forId TEXT,
      mime TEXT,
      props TEXT,
      FOREIGN KEY (threadId) REFERENCES threads(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS feedbacks (
      id TEXT PRIMARY KEY,
      forId TEXT NOT NULL,
      threadId TEXT NOT NULL,
      value INTEGER NOT NULL,
      comment TEXT,
      FOREIGN KEY (threadId) REFERENCES threads(id) ON DELETE CASCADE
    );
    """)
    # Steps table: create if missing
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS steps (
      id TEXT PRIMARY KEY,
      name TEXT NOT NULL,
      type TEXT NOT NULL,
      threadId TEXT NOT NULL,
      parentId TEXT,
      streaming BOOLEAN NOT NULL,
      waitForAnswer BOOLEAN,
      isError BOOLEAN,
      metadata TEXT,
      tags TEXT,
      input TEXT,
      output TEXT,
      createdAt TEXT,
      command TEXT,
      start TEXT,
      end TEXT,
      -- Note: defaultOpen and showInput added below if needed
      metadata2 TEXT
    );
    """)
    # 1b) Check for and add the `defaultOpen` column if missing
    cur.execute("PRAGMA table_info(steps);")
    columns = [row[1] for row in cur.fetchall()]
    if "defaultOpen" not in columns:
        log_data("Adding missing 'defaultOpen' column to steps table")
        cur.execute("ALTER TABLE steps ADD COLUMN defaultOpen BOOLEAN DEFAULT 0;")
    if "showInput" not in columns:
        log_data("Adding missing 'showInput' column to steps table")
        cur.execute("ALTER TABLE steps ADD COLUMN showInput TEXT;")

    conn.commit()
    conn.close()
    log_data("Schema migration completed successfully")

    # Return the async driver–backed data layer
    return SQLAlchemyDataLayer(
        conninfo="sqlite+aiosqlite:///./chatbot_messagesstate_v2.sqlite" # Chainlit's database
    )

# -----------------------------------------------------------------------------
# 2) Password Authentication (required for sidebar)
# -----------------------------------------------------------------------------
@cl.password_auth_callback
def auth_callback(username: str, password: str) -> Optional[cl.User]:
    log_auth(f"Authentication attempt for user: {username}")
    if username == "admin" and password == "admin":
        log_auth(f"User '{username}' authenticated successfully")
        return cl.User(identifier="admin", metadata={"role": "admin"})
    log_auth(f"Authentication failed for user: {username}", data={"reason": "Invalid credentials"})
    return None

# -----------------------------------------------------------------------------
# 3) Resume Handler
# -----------------------------------------------------------------------------
from chainlit.types import ThreadDict

@cl.on_chat_resume
@timing_decorator
async def on_chat_resume(thread: ThreadDict):
    divider("CHAT RESUME")
    thread_id = thread["id"]
    log_chainlit(f"Resuming chat thread: {thread_id}", data={"thread_name": thread.get("name")})
    cl.user_session.set("thread_id", thread_id)
    session_logger(thread_id, "resumed")
    await cl.Message(f"🔄 Resumed chat: **{thread['name']}**").send()

# -----------------------------------------------------------------------------
# 4) LangGraph Summarization Workflow
# -----------------------------------------------------------------------------
os.environ["OPENAI_API_KEY"] = "324"
INITIAL_SYSTEM_PROMPT = "You are a helpful AI. Be concise."
LANGGRAPH_CHECKPOINT_DB_FILE = "./langgraph_checkpoints.sqlite" # New: Separate DB for LangGraph checkpoints
MESSAGES_TO_KEEP_AFTER_SUMMARY = 2
NEW_MESSAGES_THRESHOLD_FOR_SUMMARY = 10

log_info("Initializing application with the following configuration:")
log_info("LangGraph checkpoint database", data=LANGGRAPH_CHECKPOINT_DB_FILE)
log_info("Messages threshold for summarization", data=NEW_MESSAGES_THRESHOLD_FOR_SUMMARY)
log_info("Messages to keep after summarization", data=MESSAGES_TO_KEEP_AFTER_SUMMARY)

llm = ChatOpenAI(
    base_url="http://141.98.210.149:15203/v1",
    model_name="gpt-4o",
    temperature=0.5,
    api_key="324"
)
log_info("LLM initialized", data={"model": "gpt-4o", "base_url": "http://141.98.210.149:15203/v1"})

def ensure_message_has_id(message: BaseMessage) -> BaseMessage:
    if not hasattr(message, "id") or not isinstance(message.id, str):
        message.id = str(uuid.uuid4())
        log_debug(f"Added ID to message: {message.id}")
    return message

class AgentState(MessagesState):
    summary: str
    messages_since_last_summary: Annotated[int, operator.add]

def call_llm_node(state: AgentState) -> dict:
    thread_id = cl.user_session.get("thread_id", "unknown_thread")
    log_workflow("llm_caller", f"Processing for thread {thread_id}")
    
    # Log the current state
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
    
    # Reset messages_since_last_summary
    current_messages_since_summary = state.get("messages_since_last_summary", 0)
    log_debug(f"Resetting messages_since_last_summary counter from {current_messages_since_summary} to 0")
    
    result = {
        "summary": new_summary,
        "messages": to_remove,
        "messages_since_last_summary": -current_messages_since_summary  # This will reset the counter to 0
    }
    
    log_workflow("summarize_conversation", "Completed summarization", data=result)
    return result

log_langgraph("Initializing LangGraph checkpoint manager", data={"db_file": LANGGRAPH_CHECKPOINT_DB_FILE})
checkpointer_cm = SqliteSaver.from_conn_string(LANGGRAPH_CHECKPOINT_DB_FILE)
checkpointer = contextlib.ExitStack().enter_context(checkpointer_cm)

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
app = workflow.compile(checkpointer=checkpointer)
log_langgraph("LangGraph workflow compiled successfully")

@cl.on_chat_start
@timing_decorator
async def start():
    divider("CHAT START")
    thread_id = str(uuid.uuid4())
    log_chainlit(f"Starting new chat with thread_id: {thread_id}")
    cl.user_session.set("thread_id", thread_id)
    session_logger(thread_id, "started")
    
    # Config for LangGraph, ensuring thread_id is correctly namespaced
    config = {"configurable": {"thread_id": thread_id}}
    log_debug("Created LangGraph config", data=config)
    
    init_sys = ensure_message_has_id(SystemMessage(content=INITIAL_SYSTEM_PROMPT))
    log_debug("Created initial system message", data={"id": init_sys.id, "content": init_sys.content})
    
    # Initial values for the LangGraph state
    initial_values = {
        "messages": [init_sys], 
        "summary": "", 
        "messages_since_last_summary": 0
    }
    log_debug("Setting up initial state", data=initial_values)
    
    # Update LangGraph state using the config and initial values
    log_langgraph("Initializing state in LangGraph", data={"thread_id": thread_id})
    app.update_state(config, initial_values)
    
    await cl.Message("How can I help you?").send()
    log_chainlit("Sent initial greeting to user")

@cl.on_message
@timing_decorator
async def handle_message(message: cl.Message):
    divider("MESSAGE RECEIVED")
    log_chainlit(f"Received message: {message.content[:50]}..." if len(message.content) > 50 else message.content)
    
    thread_id = cl.user_session.get("thread_id")
    if not thread_id:
        thread_id = str(uuid.uuid4())
        log_warning("No thread_id found in session, generating new one", data={"thread_id": thread_id})
        cl.user_session.set("thread_id", thread_id)
        session_logger(thread_id, "created (fallback)")

    config = {"configurable": {"thread_id": thread_id}}
    log_debug("LangGraph config", data=config)
    
    user_msg = ensure_message_has_id(HumanMessage(content=message.content))
    log_debug("Created LangChain message object", data={"id": user_msg.id, "type": "HumanMessage"})

    log_chainlit("Sending spinner message")
    spinner = cl.Message(content="", author="Bot", type="run")
    await spinner.send()

    bot_response = ""
    try:
        log_langgraph("Streaming LangGraph execution", data={"thread_id": thread_id})
        for i, update in enumerate(app.stream({"messages": [user_msg]}, config=config, stream_mode="values")):
            log_debug(f"Stream update #{i+1}", data=update)
            ais = [m for m in update.get("messages", []) if isinstance(m, AIMessage)]
            if ais:
                bot_response = ais[-1].content
                log_debug("Found AI response", data={"content_length": len(bot_response)})

        log_chainlit("Removing spinner")
        await spinner.remove()
        
        log_chainlit("Sending bot response", data={"content_length": len(bot_response)})
        await cl.Message(bot_response, author="Bot").send()
        session_logger(thread_id, "response sent")
        
    except Exception as e:
        log_error(f"Error processing message: {str(e)}", data={"exception": repr(e)})
        await spinner.remove()
        await cl.Message(f"Error: {e}", author="Bot").send()
        session_logger(thread_id, "error", data={"error": str(e)})
