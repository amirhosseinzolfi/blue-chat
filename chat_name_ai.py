import os
import sqlite3
import asyncio
import chainlit as cl
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from sqlalchemy import create_engine, MetaData, Table, update

# -----------------------------------------------------------------------------
# Configuration for Title-Generation LLM
# -----------------------------------------------------------------------------
# Use a separate LLM instance (e.g. GPT-3.5-turbo) for generating chat titles
TITLE_LLM = ChatOpenAI(
    base_url="http://localhost:15401/v1",
    model_name="deepseek-r1",
    temperature=0.5,
    api_key="324"
)
# -----------------------------------------------------------------------------
# Database setup for renaming threads
# -----------------------------------------------------------------------------
# Use the same SQLite file as Chainlit's data layer
SQLITE_DB_PATH = os.getenv(
    "CHAINLIT_SQLITE_DB", "./chatbot_messagesstate_v2.sqlite"
)

_engine = create_engine(
    f"sqlite:///{SQLITE_DB_PATH}",
    connect_args={"check_same_thread": False}
)

_meta = MetaData(bind=_engine)
_threads_table = Table("threads", _meta, autoload_with=_engine)

# -----------------------------------------------------------------------------
# Core Title-Generation Logic
# -----------------------------------------------------------------------------
async def generate_chat_title(thread_id: str) -> str:
    """
    Fetches the chat history for a given thread and generates a concise title using the LLM.
    """
    # 1) Retrieve all messages for this thread via Chainlit data layer
    history = await cl.data_layer.get_messages(thread_id)
    # 2) Concatenate text content
    contents = []
    for msg in history:
        content = getattr(msg, "content", None)
        if isinstance(content, str):
            contents.append(content)
    text = "\n".join(contents)

    # Protect against empty history
    if not text:
        return "New Conversation"

    # 3) Build LLM prompt
    prompt_text = (
        "You are a helpful assistant that generates short, descriptive chat titles. "
        "Please provide a concise title (4 words max) for the following conversation:\n\n" + text
    )

    # 4) Invoke the LLM asynchronously
    resp = await TITLE_LLM.apredict([
        SystemMessage(content="You are a title-generator."),
        HumanMessage(content=prompt_text)
    ])
    title = resp.strip().title()
    return title


def _update_thread_name_db(thread_id: str, new_name: str):
    """
    Synchronously updates the thread name in the SQLite database.
    """
    with _engine.begin() as conn:
        stmt = (
            update(_threads_table)
            .where(_threads_table.c.id == thread_id)
            .values(name=new_name)
        )
        conn.execute(stmt)

# -----------------------------------------------------------------------------
# Chainlit Callback to Rename Thread on Chat End
# -----------------------------------------------------------------------------
@cl.on_chat_end
async def name_chat(thread: dict):
    """
    Callback triggered when a chat ends. Generates and updates the thread name.
    """
    thread_id = thread.get("id")
    try:
        # Generate a new title
        new_title = await generate_chat_title(thread_id)
        # Persist the title in DB
        await asyncio.get_event_loop().run_in_executor(
            None, _update_thread_name_db, thread_id, new_title
        )
        cl.log_info(f"Updated thread '{thread_id}' with new title: '{new_title}'")
    except Exception as e:
        cl.log_error(f"Failed to generate or update chat title: {e}")
