import logging
from rich.logging import RichHandler
from rich.console import Console

# Define a global console for consistent styling if needed elsewhere
console = Console(color_system="auto")

def setup_logging(level="INFO", logger_name=None):
    """
    Sets up logging with RichHandler for colored and structured output.

    Args:
        level (str, optional): The logging level (e.g., "DEBUG", "INFO"). Defaults to "INFO".
        logger_name (str, optional): If provided, configures this specific logger.
                                     Otherwise, configures the root logger.
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    FORMAT = "%(name)s: %(message)s" # Keep it clean, RichHandler adds timestamp and level

    rich_handler = RichHandler(
        level=log_level,
        console=console,
        rich_tracebacks=True,
        tracebacks_show_locals=True,
        markup=True, # Enable Rich markup in log messages
        log_time_format="[%X]", # e.g., [12:34:56]
        show_path=False # Show path only for tracebacks, not every log message
    )

    if logger_name:
        logger = logging.getLogger(logger_name)
        # Prevent messages from being duplicated if the root logger also has handlers
        logger.propagate = False
    else:
        logger = logging.getLogger() # Root logger

    # Remove any existing handlers to avoid duplicate messages
    if logger.hasHandlers():
        logger.handlers.clear()

    logger.setLevel(log_level)
    logger.addHandler(rich_handler)

    if logger_name:
        return logging.getLogger(logger_name)
    return logging.getLogger() # Return the configured root logger instance

if __name__ == "__main__":
    # Example usage:
    setup_logging("DEBUG") # Setup root logger
    
    log = logging.getLogger("my_app") # Get a specific logger
    # If you want this specific logger to also use the rich handler directly:
    # setup_logging("DEBUG", "my_app")


    log.debug("This is a [bold cyan]debug[/] message with markup.", extra={"markup": True})
    log.info("This is an [green]info[/] message.")
    log.warning("This is a [yellow]warning[/].")
    log.error("This is an [bold red]error[/].")
    log.critical("This is a [bold white on red]critical[/] error!")

    try:
        1 / 0
    except ZeroDivisionError:
        log.exception("A caught exception occurred.")
