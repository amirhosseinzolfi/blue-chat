import inspect
import time
from datetime import datetime
from functools import wraps
from typing import Any, Dict, List, Optional, Union

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.traceback import install
from rich.pretty import pprint
from rich import print as rprint
from rich.syntax import Syntax

# Install rich traceback handler
install(show_locals=True)

# Initialize console
console = Console()

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
}

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
        caller_info = f"[dim][{filename}:{lineno} in {function}()][/dim] "
    
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
        if isinstance(data, dict) or isinstance(data, list):
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
        if len(content) > 100:
            content = content[:97] + "..."
        message_table.add_row(msg_type, msg_id, content)
    
    _log(f"{len(messages)} messages:", category="MESSAGE", data=message_table)

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
