# chainlit_ui.py

import os
import uuid
import sqlite3
import base64
import threading  # Add threading for g4f API server
from typing import Optional

import chainlit as cl
from chainlit.data.sql_alchemy import SQLAlchemyDataLayer
from chainlit.types import ThreadDict
from chainlit.input_widget import Select
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from chainlit.action import Action
from langgraph.graph.message import RemoveMessage  # Import for removing messages from LangGraph state
from chainlit.message import Message as CLMessage  # For UI message removal

# Import logger utilities including the new functions
from logger_utils import (
    log_info, log_warning, log_error, log_debug, 
    log_chainlit, log_auth, log_data, 
    timing_decorator, session_logger, divider,
    set_logging_context, flush_conversation_log
)

# Start g4f API server
try:
    from g4f.api import run_api
    
    def _start_g4f():
        log_info("Starting G4F API server on http://localhost:15401/v1")
        run_api(bind="0.0.0.0:15401")
    
    # Start g4f API server in a background thread
    threading.Thread(target=_start_g4f, daemon=True, name="G4F-API-Thread").start()
except ImportError:
    log_warning("g4f.api module not found. Install the 'g4f' package to run the local API server.")

# Import LangGraph app and related components from the agent file
from langgraph_agent import app, INITIAL_SYSTEM_PROMPT, ensure_message_has_id

# -----------------------------------------------------------------------------
# 0) Constants and Helpers
# -----------------------------------------------------------------------------
# Organized by provider for better categorization
LLM_MODELS = [
    # OpenAI models
    "gemini-1.5-flash",

    "gemini-1.5-pro",
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-4.1",
    "gpt-4.1-mini",
    "gpt-4.5",
    # Google models
    "gemini-2.0-flash",
    "gemini-2.0-pro",
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "evil",
    # Anthropic models
    "claude-3.5-sonnet",
    "claude-3.7-sonnet",
    # Meta models
    "llama-3.3-70b",
    # DeepSeek models
    "deepseek-r1",
    "deepseek-r1-turbo",
    # xAI models
    "grok-3-r1",
    # Other models
    "o1",
    "o3-mini-high",
    "o4-mini-high",
    "llama-4-maverick-17b",
]

def get_chat_settings_widgets(current_model: Optional[str] = None):
    """Helper function to create chat settings widgets."""
    initial_idx = 0
    if current_model and current_model in LLM_MODELS:
        try:
            initial_idx = LLM_MODELS.index(current_model)
        except ValueError:
            # If current_model is somehow not in LLM_MODELS, default to 0
            log_warning(f"Model '{current_model}' from session not in defined LLM_MODELS. Defaulting to first model.")
            initial_idx = 0
    
    return [
        Select(
            id="llm_model",
            label="Choose LLM",
            values=LLM_MODELS,
            initial_index=initial_idx,
        )
    ]

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
    user_identifier = thread.get("userIdentifier", "UnknownUser")
    log_chainlit(f"Resuming chat thread: {thread_id} for user: {user_identifier}", data={"thread_name": thread.get("name")})
    cl.user_session.set("thread_id", thread_id) # Critical for linking session to LangGraph thread

    # Retrieve the last selected model for this session
    current_model_in_session = cl.user_session.get("llm_model")
    log_chainlit(f"Retrieved model from session for resume: '{current_model_in_session}' for thread_id: {thread_id}")

    # Send chat settings to ensure the UI button is present and reflects the session's model
    chat_settings_widgets = get_chat_settings_widgets(current_model_in_session)
    await cl.ChatSettings(chat_settings_widgets).send()
    log_chainlit(f"Sent chat settings on resume for thread_id: {thread_id}. Initial model for UI: '{LLM_MODELS[chat_settings_widgets[0].initial_index]}'")

    # Ensure a valid model is set in the session, defaulting if necessary
    if current_model_in_session and current_model_in_session in LLM_MODELS:
        # Model from session is valid, ensure it's set (might be redundant if already set, but safe)
        cl.user_session.set("llm_model", current_model_in_session)
    else:
        # If no model in session, or model is invalid, set to the default from settings
        default_model_for_session = LLM_MODELS[chat_settings_widgets[0].initial_index]
        cl.user_session.set("llm_model", default_model_for_session)
        log_chainlit(f"Model in session was '{current_model_in_session}'. Set to '{default_model_for_session}' for thread_id: {thread_id}")

    session_logger(thread_id, f"resumed by user {user_identifier}, model set to '{cl.user_session.get('llm_model')}'")


# -----------------------------------------------------------------------------
# 4) Chat Settings Update Handler
# -----------------------------------------------------------------------------
@cl.on_settings_update
async def on_settings_update(settings: dict):
    # Update the stored model whenever the user changes it :contentReference[oaicite:0]{index=0}
    if "llm_model" in settings:
        selected_model = settings["llm_model"]
        cl.user_session.set("llm_model", selected_model)
        thread_id = cl.user_session.get("thread_id", "N/A")
        log_chainlit(f"ChatSettings updated: llm_model set to '{selected_model}' for thread_id: {thread_id}")

# -----------------------------------------------------------------------------
# 5) Chainlit Callbacks using the LangGraph Agent
# -----------------------------------------------------------------------------
@cl.on_chat_start
@timing_decorator
async def start():
    divider("CHAT START")
    # 1) Let user choose an LLM from the chat settings dropdown
    # For a new chat, current_model is None, so get_chat_settings_widgets defaults to initial_index=0
    chat_settings_widgets = get_chat_settings_widgets()
    settings = await cl.ChatSettings(chat_settings_widgets).send()
    
    selected_model = settings["llm_model"] # This will be LLM_MODELS[chat_settings_widgets[0].initial_index]
    cl.user_session.set("llm_model", selected_model)

    # Generate a new thread_id for each new chat session.
    # This thread_id is used to configure the LangGraph agent,
    # ensuring that each chat session has its own isolated state.
    thread_id = str(uuid.uuid4())
    cl.user_session.set("thread_id", thread_id) # Store thread_id in session
    log_chainlit(f"New chat started. Thread ID: {thread_id}. Initial LLM: '{selected_model}'")
    session_logger(thread_id, f"started with LLM: {selected_model}")
    
    config = {"configurable": {"thread_id": thread_id, "model_name": selected_model}}
    log_debug(f"Initializing LangGraph for thread {thread_id} with model: '{selected_model}'", data=config)
    
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
    log_chainlit(f"Initialized state in LangGraph for thread {thread_id} using model '{selected_model}'")
    


@cl.on_message
@timing_decorator
async def handle_message(message: cl.Message):
    divider("MESSAGE RECEIVED")
    
    thread_id = cl.user_session.get("thread_id")
    selected_model = cl.user_session.get("llm_model", "gpt-4o") # Default if not set

    if not thread_id:
        # Fallback: This should ideally not happen if on_chat_start or on_chat_resume always sets it.
        thread_id = str(uuid.uuid4())
        cl.user_session.set("thread_id", thread_id)
        log_warning(f"No thread_id found in session, generated new one: {thread_id}. Using LLM: '{selected_model}'.", data={"thread_id": thread_id, "model_name": selected_model})
        session_logger(thread_id, f"created (fallback in on_message) with LLM: {selected_model}")
        # Consider if initial state needs to be set here for such fallback cases.
        # For now, assume on_chat_start handles new threads properly.
    
    log_chainlit(f"Processing message for thread_id: {thread_id} using LLM: '{selected_model}'", 
                 data={"message_preview": message.content[:50] + "..." if len(message.content) > 50 else message.content})

    config = {"configurable": {"thread_id": thread_id, "model_name": selected_model}}
    log_debug(f"Using LangGraph config for message. Thread ID: {thread_id}, Model: '{selected_model}'", data=config)
    
    # Prepare content for HumanMessage, potentially including an image
    human_message_content = [{"type": "text", "text": message.content}]

    if message.elements:
        for element in message.elements:
            if element.mime and "image" in element.mime:
                log_debug(f"Image element found: {element.name}, mime: {element.mime}")
                try:
                    # Accessing element.path which should be populated by Chainlit for file uploads
                    image_path = element.path
                    if image_path:
                        with open(image_path, "rb") as image_file:
                            encoded_image = base64.b64encode(image_file.read()).decode("utf-8")
                        
                        image_part = {
                            "type": "image_url",
                            "image_url": {"url": f"data:{element.mime};base64,{encoded_image}"},
                        }
                        human_message_content.append(image_part)
                        log_debug("Added base64 encoded image to message content")
                        # Process only the first image found
                        break 
                    else:
                        log_warning(f"Image element {element.name} has no path attribute.")
                except Exception as e:
                    log_error(f"Error processing image element {element.name}: {str(e)}")


    user_msg = ensure_message_has_id(HumanMessage(content=human_message_content))
    log_debug(f"Created LangChain HumanMessage. Thread ID: {thread_id}, Model: '{selected_model}'", 
              data={"id": user_msg.id, "content_structure": [part["type"] for part in human_message_content]})

    # Create a loading message - we'll replace it with the complete response later
    spinner = cl.Message(content="", author="بلو") # Empty content for modern spinner
    await spinner.send()

    bot_response_content = ""
    ai_message_id = None
    try:
        log_chainlit(f"Executing LangGraph. Thread ID: {thread_id}, Model: '{selected_model}'")
        # Process the LangGraph response to get the complete answer
        for i, update_chunk in enumerate(app.stream({"messages": [user_msg]}, config=config, stream_mode="values")):
            log_debug(f"LangGraph stream update #{i+1}. Thread ID: {thread_id}, Model: '{selected_model}'")
            # The final AI message is typically in the 'messages' list of the last update
            ai_messages_in_chunk = [m for m in update_chunk.get("messages", []) if isinstance(m, AIMessage)]
            if ai_messages_in_chunk:
                # Extract content from the last AI message
                last_message = ai_messages_in_chunk[-1]
                
                # Process content appropriately based on type
                if isinstance(last_message.content, str):
                    bot_response_content = last_message.content
                elif isinstance(last_message.content, list):
                    # Extract text content from multimodal response
                    text_parts = []
                    for part in last_message.content:
                        if isinstance(part, dict) and part.get("type") == "text":
                            text_parts.append(part.get("text", ""))
                    bot_response_content = "\n".join(text_parts)
                    if not bot_response_content:
                        bot_response_content = "[The AI responded with non-text content]"
                
                # Store the AI message ID for potential retry operations
                ai_message_id = last_message.id if hasattr(last_message, "id") else None
                log_debug(f"Updated AI message ID for potential retry: {ai_message_id}")
        
        # Remove the spinner
        await spinner.remove()
        
        # Show the complete response at once
        if bot_response_content:
            log_chainlit(f"Sending complete bot response. Thread ID: {thread_id}, Model: '{selected_model}'", 
                        {"content_length": len(bot_response_content)})
            
            # Send the complete message
            msg = await cl.Message(content=bot_response_content, author="Bot").send()
            
            # Add retry action button below the AI message
            retry_action = Action(
                name="retry",
                payload={
                    "content": message.content,
                    "original_user_msg_id": user_msg.id,  # Original user message ID
                    "original_ai_msg_id": ai_message_id   # Corresponding AI response ID
                },
                label="",
                tooltip="Retry this message",
                icon="refresh-cw"
            )
            await retry_action.send(for_id=msg.id)
            
            # Add copy action button
            copy_action = Action(
                name="copy",
                payload={"text": bot_response_content},
                label="",
                tooltip="Copy to clipboard",
                icon="copy"
            )
            await copy_action.send(for_id=msg.id)
            
            session_logger(thread_id, f"response sent (model: {selected_model})")
            
            # Now flush the detailed conversation log (this will display it last)
            flush_conversation_log(thread_id)
        else:
            log_warning(f"No AI response content found. Thread ID: {thread_id}, Model: '{selected_model}'")
            await cl.Message(content="Sorry, I couldn't generate a response.", author="Bot").send()
            session_logger(thread_id, f"no response content (model: {selected_model})")
            
    except Exception as e:
        log_error(f"Error processing message with LangGraph. Thread ID: {thread_id}, Model: '{selected_model}'. Error: {str(e)}", 
                  data={"exception": repr(e), "thread_id": thread_id, "model_name": selected_model})
        await spinner.remove()
        await cl.Message(content=f"An error occurred: {str(e)}", author="Bot").send()
        session_logger(thread_id, "error", data={"error": str(e), "model_name": selected_model})
        # Ensure logs are flushed even on error
        flush_conversation_log(thread_id)

# Action callback for retrying AI messages
@cl.action_callback("retry")
async def retry_action(action: Action):
    thread_id = cl.user_session.get("thread_id")
    # Get both message IDs from payload
    user_msg_id = action.payload.get("original_user_msg_id")
    ai_msg_id = action.payload.get("original_ai_msg_id")
    old_bot_msg_id = action.forId # ID of the Chainlit UI message this action is attached to

    log_chainlit(f"Retry action triggered. Thread ID: {thread_id}", 
                 {"user_msg_id": user_msg_id, "ai_msg_id": ai_msg_id, "ui_msg_id": old_bot_msg_id})

    # 1. Get the old message and prepare to replace it
    old_msg = cl.Message(id=old_bot_msg_id, content="")
    
    # 2. Remove the old bot message from UI
    await old_msg.remove()

    # 3. Prepare config for LangGraph state update
    selected_model = cl.user_session.get("llm_model", "gpt-4o")
    config = {"configurable": {"thread_id": thread_id, "model_name": selected_model}}

    # 4. Remove BOTH the original user message AND its AI response from LangGraph state
    # This ensures the history is clean for the retry
    remove_msgs = []
    
    if user_msg_id:
        remove_msgs.append(RemoveMessage(id=user_msg_id))
        log_debug(f"Will remove original user message (ID: {user_msg_id}) from LangGraph state")
    
    if ai_msg_id:
        remove_msgs.append(RemoveMessage(id=ai_msg_id))
        log_debug(f"Will remove original AI response (ID: {ai_msg_id}) from LangGraph state")
    
    if remove_msgs:
        # Update LangGraph state by removing both messages and adjusting summary counter
        # Decrement by 2 if we're removing both messages, or by 1 if only removing user message
        summary_adjustment = -2 if ai_msg_id else -1
        app.update_state(config, {"messages": remove_msgs, "messages_since_last_summary": summary_adjustment})
        log_debug(f"Removed {len(remove_msgs)} messages from LangGraph state", 
                  {"user_msg_id": user_msg_id, "ai_msg_id": ai_msg_id})
    else:
        log_warning("No message IDs found in payload to remove from LangGraph state")

    # 5. Re-send the user message content to LangGraph via handle_message
    original_user_content = action.payload.get("content", "")

    # Simulate cl.Message for handle_message
    class FakeChainlitMessage:
        def __init__(self, content_text):
            self.content = content_text
            self.elements = [] # Assuming retry doesn't involve image uploads

    fake_cl_message = FakeChainlitMessage(original_user_content)
    await handle_message(fake_cl_message) # This will create a new HumanMessage and process it

# Entry point for Chainlit (if running this file directly)
if __name__ == "__main__":
    log_info("Chainlit UI application ready.")
    log_info("Run with: chainlit run chainlit_ui.py -w --host 141.98.210.149 --port 15308")
    log_info("App available at: http://141.98.210.149:15308")
