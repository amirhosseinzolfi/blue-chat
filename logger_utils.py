import inspect
import time
import logging
from datetime import datetime
from functools import wraps
from typing import Any, Dict, List, Optional, Union

from langchain_core.messages import HumanMessage # Add this import

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.traceback import install
from rich.pretty import pprint
from rich import print as rprint
from rich.syntax import Syntax
from rich.markup import escape
from rich.logging import RichHandler

# Install rich traceback handler
install(show_locals=True)

# Initialize console
console = Console(color_system="auto")

# Define color schemes
COLORS = {
    "INFO": "green",
    "WARNING": "yellow",
    "ERROR": "red",
    "CRITICAL": "red bold",
    "DEBUG": "blue",
    "CHAINLIT": "cyan",
    "LANGGRAPH": "magenta",
    "AUTH": "bright_yellow",
    "DATA": "bright_blue",
    "STATE": "bright_green",
    "WORKFLOW": "bright_magenta",
    "MESSAGE": "bright_cyan",
    "SESSION": "purple4",
    "CONVERSATION": "orange1",  # New color for detailed conversation logs
}

# --------------------------------------------------------------------------
# Logging Setup (Migrated from logger_config.py)
# --------------------------------------------------------------------------

def setup_logging(level="INFO", logger_name=None):
    """
    Sets up logging with RichHandler for colored and structured output.

    Args:
        level (str, optional): The logging level (e.g., "DEBUG", "INFO"). Defaults to "INFO".
        logger_name (str, optional): If provided, configures this specific logger.
                                     Otherwise, configures the root logger.
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    FORMAT = "%(name)s: %(message)s"  # Keep it clean, RichHandler adds timestamp and level

    rich_handler = RichHandler(
        level=log_level,
        console=console,
        rich_tracebacks=True,
        tracebacks_show_locals=True,
        markup=True,  # Enable Rich markup in log messages
        log_time_format="[%X]",  # e.g., [12:34:56]
        show_path=False  # Show path only for tracebacks, not every log message
    )

    if logger_name:
        logger = logging.getLogger(logger_name)
        # Prevent messages from being duplicated if the root logger also has handlers
        logger.propagate = False
    else:
        logger = logging.getLogger()  # Root logger

    # Remove any existing handlers to avoid duplicate messages
    if logger.hasHandlers():
        logger.handlers.clear()

    logger.setLevel(log_level)
    logger.addHandler(rich_handler)

    if logger_name:
        return logging.getLogger(logger_name)
    return logging.getLogger()  # Return the configured root logger instance

# --------------------------------------------------------------------------
# Core Logging Functions
# --------------------------------------------------------------------------

def get_timestamp():
    """Return formatted timestamp for logs"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

def _log(
    message: str, 
    level: str = "INFO", 
    category: str = None, 
    data: Any = None,
    show_callsite: bool = False
):
    """Base logging function with rich formatting"""
    timestamp = get_timestamp()
    
    # Get caller information if requested
    caller_info = ""
    if show_callsite:
        frame = inspect.currentframe().f_back.f_back
        filename = frame.f_code.co_filename.split("\\")[-1]
        lineno = frame.f_lineno
        function = frame.f_code.co_name
        caller_details = escape(f"{filename}:{lineno} in {function}()")
        caller_info = f"[dim]{caller_details}[/dim] "
    
    # Format the category and level
    category_str = f"[{COLORS.get(category, 'white')}]{category}[/{COLORS.get(category, 'white')}]" if category else ""
    level_str = f"[{COLORS.get(level, 'white')}]{level}[/{COLORS.get(level, 'white')}]"
    
    # Print header
    header = f"[dim]{timestamp}[/dim] {level_str} {category_str} {caller_info}"
    console.print(header, end=" ")
    
    # Print message
    console.print(message)
    
    # Print additional data if provided
    if data is not None:
        if isinstance(data, Table): # Check for Table object first
            console.print(data)
        elif isinstance(data, dict) or isinstance(data, list):
            console.print(Panel.fit(Syntax(str(data), "python", theme="monokai")))
        else:
            pprint(data)
    
    console.print()  # Add a newline for separation

def log_info(message: str, data: Any = None):
    """Log info level message"""
    _log(message, level="INFO", data=data, show_callsite=True)

def log_warning(message: str, data: Any = None):
    """Log warning level message"""
    _log(message, level="WARNING", data=data, show_callsite=True)

def log_error(message: str, data: Any = None):
    """Log error level message"""
    _log(message, level="ERROR", data=data, show_callsite=True)

def log_debug(message: str, data: Any = None):
    """Log debug level message"""
    _log(message, level="DEBUG", data=data, show_callsite=True)

def log_chainlit(message: str, data: Any = None):
    """Log Chainlit specific events"""
    _log(message, category="CHAINLIT", data=data, show_callsite=True)

def log_langgraph(message: str, data: Any = None):
    """Log LangGraph specific events"""
    _log(message, category="LANGGRAPH", data=data, show_callsite=True)

def log_auth(message: str, data: Any = None):
    """Log authentication events"""
    _log(message, category="AUTH", data=data, show_callsite=True)

def log_data(message: str, data: Any = None):
    """Log data layer operations"""
    _log(message, category="DATA", data=data, show_callsite=True)

def log_workflow(node: str, message: str, data: Any = None):
    """Log workflow node execution"""
    _log(f"Node: [bold]{node}[/bold] - {message}", category="WORKFLOW", data=data, show_callsite=True)

def log_state(state: Dict[str, Any]):
    """Pretty print LangGraph state"""
    summary_table = Table(show_header=True, header_style="bold")
    summary_table.add_column("Key")
    summary_table.add_column("Value")
    
    for key, value in state.items():
        if key == "messages":
            message_count = len(value) if isinstance(value, list) else "N/A"
            summary_table.add_row(key, f"{message_count} messages")
        elif isinstance(value, (int, float, str, bool)) or value is None:
            summary_table.add_row(key, str(value))
        else:
            summary_table.add_row(key, f"<{type(value).__name__}>")
    
    _log("Current state:", category="STATE", data=summary_table)

def log_messages(messages: List[Any]):
    """Pretty print message objects"""
    if not messages:
        _log("No messages", category="MESSAGE")
        return
    
    message_table = Table(show_header=True, header_style="bold")
    message_table.add_column("Type")
    message_table.add_column("ID")
    message_table.add_column("Content")
    
    for msg in messages:
        msg_type = type(msg).__name__
        msg_id = getattr(msg, "id", "N/A")
        content = getattr(msg, "content", str(msg))
        # Truncate content if too long
        if isinstance(content, str):
            if len(content) > 100:
                content = content[:97] + "..."
        elif isinstance(content, list):
            content = f"[Multimodal content with {len(content)} parts]"
        message_table.add_row(msg_type, msg_id, str(content))
    
    _log(f"{len(messages)} messages:", category="MESSAGE", data=message_table)

# --------------------------------------------------------------------------
# Enhanced Detailed Conversation Logging
# --------------------------------------------------------------------------

# Add buffer to store conversation logs until they need to be displayed
_conversation_buffer = {}

def log_conversation(
    thread_id: str,
    model_name: str,
    system_instruction: str,
    history_summary: str = None,
    messages: List[Any] = None,
    final_prompt: str = None, # Argument kept for signature compatibility, not directly used for the "User Prompt to AI" row
    ai_response: str = None
):
    """
    Log detailed information about a conversation in a structured table format.
    
    Args:
        thread_id: The conversation thread ID
        model_name: The AI model used for this conversation
        system_instruction: The system instruction/prompt
        history_summary: Summary of conversation history (if available)
        messages: List of message objects in the conversation (this is what's sent to the LLM)
        final_prompt: The full constructed prompt string (optional, not used for "User Prompt to AI" row).
        ai_response: The AI's response
    """
    # Create main table
    convo_table = Table(
        title=f"[bold]{model_name}[/bold] Conversation Details (Thread: {thread_id})",
        expand=True,
        highlight=True,
        border_style="orange1",
        caption="Full Conversation Details"
    )
    
    # Add columns for the main info
    convo_table.add_column("Parameter", style="cyan")
    convo_table.add_column("Value", style="white")
    
    # Add model name and session ID
    convo_table.add_row("Model", f"[bold green]{model_name}[/bold green]")
    convo_table.add_row("Session ID", f"[bold yellow]{thread_id}[/bold yellow]")
    
    # Add system instruction (truncate if very long)
    sys_instr_display = system_instruction
    if len(system_instruction) > 300:
        sys_instr_display = system_instruction[:297] + "..."
    convo_table.add_row("System Instruction", sys_instr_display)
    
    # Add history summary if available
    if history_summary:
        summary_display = history_summary
        if len(history_summary) > 300:
            summary_display = history_summary[:297] + "..."
        convo_table.add_row("History Summary", summary_display)
    else:
        convo_table.add_row("History Summary", "[dim]None[/dim]")
    
    # Add message count
    msg_count = len(messages) if messages else 0
    convo_table.add_row("Message Count", f"[bold]{msg_count}[/bold] messages")
    
    # Create nested table for messages if available
    if messages and len(messages) > 0:
        msg_table = Table(show_header=True)
        msg_table.add_column("#", style="dim")
        msg_table.add_column("Role", style="magenta")
        msg_table.add_column("Content", style="white")
        
        for i, msg in enumerate(messages):
            role = "System"
            if hasattr(msg, "__class__") and hasattr(msg.__class__, "__name__"):
                if "Human" in msg.__class__.__name__:
                    role = "Human"
                elif "AI" in msg.__class__.__name__:
                    role = "AI"
            
            content = getattr(msg, "content", "")
            if isinstance(content, list):
                # Handle multimodal content
                content_parts = []
                for part in content:
                    if isinstance(part, dict):
                        if part.get("type") == "text":
                            content_parts.append(part.get("text", ""))
                        elif part.get("type") == "image_url":
                            content_parts.append("[Image content]")
                content = "\n".join(content_parts)
                if len(content) > 100:
                    content = content[:97] + "..."
            elif isinstance(content, str) and len(content) > 100:
                content = content[:97] + "..."
                
            msg_table.add_row(str(i+1), role, content)
        
        convo_table.add_row("Message History", msg_table)
    
    # Display the content of the last HumanMessage as "User Prompt to AI"
    user_prompt_content_display = "[No user prompt found in messages]"
    if messages:
        last_human_message_obj = None
        # Iterate in reverse to find the last HumanMessage
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage):
                last_human_message_obj = msg
                break
        
        if last_human_message_obj:
            content = getattr(last_human_message_obj, "content", "")
            if isinstance(content, list):
                # Handle multimodal content for display
                parts_display = []
                for part in content:
                    if isinstance(part, dict):
                        if part.get("type") == "text":
                            parts_display.append(part.get("text", ""))
                        elif part.get("type") == "image_url":
                            parts_display.append("[Image Content]") # Consistent with Message History display
                        else:
                            parts_display.append(f"[{part.get('type', 'unknown part')}]")
                    else: 
                        parts_display.append(str(part)) # Handle case where content part is not a dict
                user_prompt_content_display = "\n".join(parts_display)
            elif isinstance(content, str):
                user_prompt_content_display = content
            else:
                user_prompt_content_display = str(content) # Fallback for unexpected content types

            # Truncate if very long
            if len(user_prompt_content_display) > 300:
                user_prompt_content_display = user_prompt_content_display[:297] + "..."
        
    convo_table.add_row("User Prompt to AI", Panel(user_prompt_content_display, expand=False, title="User Input to AI"))
    
    # Add AI response if available
    if ai_response:
        response_display = ai_response
        if len(ai_response) > 300:
            response_display = ai_response[:297] + "..."
        convo_table.add_row("AI Response", Panel(response_display, expand=False))
    
    # Instead of logging directly, store in buffer for later display
    _conversation_buffer[thread_id] = {
        "table": convo_table,
        "message": f"Conversation details for thread {thread_id}",
        "timestamp": get_timestamp()
    }

def flush_conversation_log(thread_id: str = None):
    """
    Display the buffered conversation log and clear the buffer.
    
    Args:
        thread_id: Optional thread ID to flush specific conversation. If None, flushes all.
    """
    global _conversation_buffer
    
    if thread_id:
        if thread_id in _conversation_buffer:
            buffered = _conversation_buffer.pop(thread_id)
            _log(buffered["message"], category="CONVERSATION", data=buffered["table"])
    else:
        # Flush all buffered conversations
        for thread_id, buffered in _conversation_buffer.items():
            _log(buffered["message"], category="CONVERSATION", data=buffered["table"])
        _conversation_buffer = {}

# --------------------------------------------------------------------------
# Context Management for Logging
# --------------------------------------------------------------------------

_logging_context = {}

def set_logging_context(context_type: str = None, **kwargs):
    """
    Set context information to be included in subsequent log entries.
    
    Args:
        context_type: Optional type of context (e.g., 'request', 'session', 'user')
        **kwargs: Key-value pairs to store in the logging context
    """
    global _logging_context
    
    if context_type:
        # If context_type is provided, store the values within that namespace
        if context_type not in _logging_context:
            _logging_context[context_type] = {}
        
        for key, value in kwargs.items():
            _logging_context[context_type][key] = value
    else:
        # Otherwise, store directly in the root context
        for key, value in kwargs.items():
            _logging_context[key] = value
    
    log_debug(f"Logging context updated", data={"context_type": context_type, "values": kwargs})

def get_logging_context(context_type: str = None, key: str = None):
    """
    Retrieve context information from the logging context.
    
    Args:
        context_type: Optional type of context to retrieve from
        key: Optional specific key to retrieve
        
    Returns:
        The requested context data or None if not found
    """
    if context_type:
        if context_type not in _logging_context:
            return None
        if key:
            return _logging_context[context_type].get(key)
        return _logging_context[context_type]
    
    if key:
        return _logging_context.get(key)
    
    return _logging_context

def clear_logging_context(context_type: str = None):
    """
    Clear the logging context.
    
    Args:
        context_type: Optional type of context to clear. If None, clears all context.
    """
    global _logging_context
    
    if context_type:
        if context_type in _logging_context:
            _logging_context.pop(context_type)
            log_debug(f"Cleared logging context for {context_type}")
    else:
        _logging_context = {}
        log_debug("Cleared all logging context")

# --------------------------------------------------------------------------
# Utility Functions
# --------------------------------------------------------------------------

def timing_decorator(func):
    """Decorator to time function execution"""
    @wraps(func)
    async def async_wrapper(*args, **kwargs):
        start_time = time.time()
        try:
            result = await func(*args, **kwargs)
            elapsed = time.time() - start_time
            _log(f"Executed [bold]{func.__name__}[/bold] in [bold]{elapsed:.4f}s[/bold]", category="TIMING")
            return result
        except Exception as e:
            elapsed = time.time() - start_time
            _log(f"Error in [bold]{func.__name__}[/bold] after [bold]{elapsed:.4f}s[/bold]: {str(e)}", level="ERROR", category="TIMING")
            raise
    
    @wraps(func)
    def sync_wrapper(*args, **kwargs):
        start_time = time.time()
        try:
            result = func(*args, **kwargs)
            elapsed = time.time() - start_time
            _log(f"Executed [bold]{func.__name__}[/bold] in [bold]{elapsed:.4f}s[/bold]", category="TIMING")
            return result
        except Exception as e:
            elapsed = time.time() - start_time
            _log(f"Error in [bold]{func.__name__}[/bold] after [bold]{elapsed:.4f}s[/bold]: {str(e)}", level="ERROR", category="TIMING")
            raise
    
    if inspect.iscoroutinefunction(func):
        return async_wrapper
    return sync_wrapper

def session_logger(session_id: str, action: str, data: Any = None):
    """Log session-specific actions"""
    _log(f"Session [bold]{session_id}[/bold]: {action}", category="SESSION", data=data, show_callsite=True)

def divider(label: str = None):
    """Print a divider with optional label"""
    if label:
        console.rule(f"[bold]{label}[/bold]")
    else:
        console.rule()

# Initialize logging on module import
setup_logging(level="INFO")
