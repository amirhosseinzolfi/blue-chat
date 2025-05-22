import os
import uuid
import sqlite3
from typing import Optional

import chainlit as cl
from chainlit.data.sql_alchemy import SQLAlchemyDataLayer
from chainlit.types import ThreadDict
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

# Import logger utilities
from logger_utils import (
    log_info, log_warning, log_error, log_debug, 
    log_chainlit, log_auth, log_data, 
    timing_decorator, session_logger, divider
)

# Import LangGraph app and related components from the agent file
from langgraph_agent import app, INITIAL_SYSTEM_PROMPT, ensure_message_has_id

# -----------------------------------------------------------------------------
# 1) Data Persistence & In-Place Schema Migration (Chainlit's Data)
# -----------------------------------------------------------------------------
@cl.data_layer
@timing_decorator
def get_data_layer():
    log_data("Initializing SQLAlchemy data layer for Chainlit")
    db_file = "./chatbot_messagesstate_v2.sqlite" # Database for Chainlit's data
    conn = sqlite3.connect(db_file)
    cur = conn.cursor()

    log_data(f"Connected to Chainlit database: {db_file}")
    
    cur.execute("PRAGMA journal_mode=WAL;")
    cur.execute("PRAGMA busy_timeout=10000;")
    log_data("Configured Chainlit SQLite with WAL mode and busy timeout")

    log_data("Creating or verifying required Chainlit tables")
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
      language TEXT, -- Added language column
      generation TEXT, -- Added generation column
      metadata2 TEXT -- Existing column from original script
      -- defaultOpen and showInput are handled by ALTER TABLE below if missing
    );
    """)
    
    cur.execute("PRAGMA table_info(steps);")
    columns = [row[1] for row in cur.fetchall()]
    if "defaultOpen" not in columns:
        log_data("Adding missing 'defaultOpen' column to steps table")
        cur.execute("ALTER TABLE steps ADD COLUMN defaultOpen BOOLEAN DEFAULT 0;")
    if "showInput" not in columns:
        log_data("Adding missing 'showInput' column to steps table")
        cur.execute("ALTER TABLE steps ADD COLUMN showInput TEXT;")
    if "language" not in columns: # Add check and ALTER for language
        log_data("Adding missing 'language' column to steps table")
        cur.execute("ALTER TABLE steps ADD COLUMN language TEXT;")
    if "generation" not in columns: # Add check and ALTER for generation
        log_data("Adding missing 'generation' column to steps table")
        cur.execute("ALTER TABLE steps ADD COLUMN generation TEXT;")

    conn.commit()
    conn.close()
    log_data("Chainlit schema migration completed successfully")

    return SQLAlchemyDataLayer(
        conninfo="sqlite+aiosqlite:///./chatbot_messagesstate_v2.sqlite"
    )

# -----------------------------------------------------------------------------
# 2) Password Authentication
# -----------------------------------------------------------------------------
@cl.password_auth_callback
def auth_callback(username: str, password: str) -> Optional[cl.User]:
    log_auth(f"Authentication attempt for user: {username}")
    if username == "admin" and password == "admin": # Use environment variables for credentials in production
        log_auth(f"User '{username}' authenticated successfully")
        return cl.User(identifier="admin", metadata={"role": "admin"})
    log_auth(f"Authentication failed for user: {username}", data={"reason": "Invalid credentials"})
    return None

# -----------------------------------------------------------------------------
# 3) Resume Handler
# -----------------------------------------------------------------------------
@cl.on_chat_resume
@timing_decorator
async def on_chat_resume(thread: ThreadDict):
    divider("CHAT RESUME")
    thread_id = thread["id"]
    log_chainlit(f"Resuming chat thread: {thread_id}", data={"thread_name": thread.get("name")})
    cl.user_session.set("thread_id", thread_id) # Critical for linking session to LangGraph thread
    session_logger(thread_id, "resumed")
    await cl.Message(f"🔄 Resumed chat: **{thread['name']}**").send()

# -----------------------------------------------------------------------------
# 4) Chainlit Callbacks using the LangGraph Agent
# -----------------------------------------------------------------------------
@cl.on_chat_start
@timing_decorator
async def start():
    divider("CHAT START")
    # Generate a new thread_id for each new chat session.
    # This thread_id is used to configure the LangGraph agent,
    # ensuring that each chat session has its own isolated state.
    thread_id = str(uuid.uuid4())
    cl.user_session.set("thread_id", thread_id) # Store thread_id in session
    log_chainlit(f"Starting new chat with thread_id: {thread_id}")
    session_logger(thread_id, "started")
    
    config = {"configurable": {"thread_id": thread_id}}
    log_debug("Created LangGraph config for new chat", data=config)
    
    init_sys_msg = ensure_message_has_id(SystemMessage(content=INITIAL_SYSTEM_PROMPT))
    log_debug("Created initial system message", data={"id": init_sys_msg.id, "content": init_sys_msg.content})
    
    initial_agent_state = {
        "messages": [init_sys_msg], 
        "summary": "", 
        "messages_since_last_summary": 0
    }
    log_debug("Setting up initial state for LangGraph agent", data=initial_agent_state)
    
    # Initialize or update the state for the new thread in LangGraph
    app.update_state(config, initial_agent_state)
    log_chainlit("Initialized state in LangGraph for new thread", data={"thread_id": thread_id})
    
    await cl.Message("How can I help you?").send()
    log_chainlit("Sent initial greeting to user")

@cl.on_message
@timing_decorator
async def handle_message(message: cl.Message):
    divider("MESSAGE RECEIVED")
    log_chainlit(f"Received message: {message.content[:50]}..." if len(message.content) > 50 else message.content)
    
    thread_id = cl.user_session.get("thread_id")
    if not thread_id:
        # Fallback: This should ideally not happen if on_chat_start or on_chat_resume always sets it.
        thread_id = str(uuid.uuid4())
        cl.user_session.set("thread_id", thread_id)
        log_warning("No thread_id found in session, generated new one for safety.", data={"thread_id": thread_id})
        session_logger(thread_id, "created (fallback in on_message)")
        # Consider if initial state needs to be set here for such fallback cases.
        # For now, assume on_chat_start handles new threads properly.

    config = {"configurable": {"thread_id": thread_id}}
    log_debug("Using LangGraph config for message", data=config)
    
    user_msg = ensure_message_has_id(HumanMessage(content=message.content))
    log_debug("Created LangChain HumanMessage object", data={"id": user_msg.id})

    spinner = cl.Message(content="", author="Bot", type="run")
    await spinner.send()

    bot_response_content = ""
    try:
        log_chainlit("Streaming LangGraph execution", data={"thread_id": thread_id})
        # Stream updates from the LangGraph agent
        for i, update_chunk in enumerate(app.stream({"messages": [user_msg]}, config=config, stream_mode="values")):
            log_debug(f"LangGraph stream update #{i+1}", data=update_chunk)
            # The final AI message is typically in the 'messages' list of the last update
            ai_messages_in_chunk = [m for m in update_chunk.get("messages", []) if isinstance(m, AIMessage)]
            if ai_messages_in_chunk:
                # Assuming the last AIMessage in the stream is the one to display
                bot_response_content = ai_messages_in_chunk[-1].content 
                log_debug("Extracted AI response from stream", {"content_preview": bot_response_content[:50]})
        
        await spinner.remove()
        
        if bot_response_content:
            log_chainlit("Sending bot response to UI", {"content_length": len(bot_response_content)})
            await cl.Message(bot_response_content, author="Bot").send()
            session_logger(thread_id, "response sent")
        else:
            log_warning("No AI response content found after streaming.", data={"thread_id": thread_id})
            await cl.Message("Sorry, I couldn't generate a response.", author="Bot").send()
            session_logger(thread_id, "no response content")
            
    except Exception as e:
        log_error(f"Error processing message with LangGraph: {str(e)}", data={"exception": repr(e), "thread_id": thread_id})
        await spinner.remove()
        await cl.Message(f"An error occurred: {str(e)}", author="Bot").send()
        session_logger(thread_id, "error", data={"error": str(e)})

# Entry point for Chainlit (if running this file directly)
if __name__ == "__main__":
    # This block is typically not needed if Chainlit CLI runs the app,
    # but can be useful for understanding or direct execution.
    # Example: chainlit run chainlit_ui.py -w
    log_info("Chainlit UI application ready. Run with 'chainlit run chainlit_ui.py -w'")
