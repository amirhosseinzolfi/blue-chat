import os
import threading
import logging
import sys

# --------------------------
# Configuration
# --------------------------
API_HOST = os.getenv("G4F_API_HOST", "http://localhost:1555/v1")
API_KEY = os.getenv("G4F_API_KEY", None)  # If required by your provider
COOKIES_DIR = os.path.join(os.path.dirname(__file__), "har_and_cookies")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# --------------------------
# Logging Setup
# --------------------------
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# --------------------------
# Load Cookies and HAR Files
# --------------------------
try:
    import g4f.debug
    from g4f.cookies import set_cookies_dir, read_cookie_files

    # Enable debug logging for g4f
    g4f.debug.logging = True

    # Configure and load cookies/HARs
    set_cookies_dir(COOKIES_DIR)
    read_cookie_files(COOKIES_DIR)
    logger.info(f"Loaded cookies and HAR files from {COOKIES_DIR}")
except ImportError as e:
    logger.warning(f"g4f cookies integration unavailable: {e}")
except Exception as e:
    logger.error(f"Error loading cookies/HARs: {e}")

# --------------------------
# G4F API Server Bootstrap
# --------------------------
try:
    from g4f.api import run_api
    G4F_API_AVAILABLE = True
except ImportError:
    run_api = None
    G4F_API_AVAILABLE = False

if G4F_API_AVAILABLE:
    def _start_g4f():
        logger.info(f"Starting G4F API server on {API_HOST} …")
        run_api(bind="0.0.0.0:1555")

    threading.Thread(
        target=_start_g4f,
        daemon=True,
        name="G4F-API-Thread"
    ).start()
else:
    logger.warning(
        "g4f.api module not found. Install the 'g4f' package to run the local API server."
    )

# --------------------------
# Terminal Chatbot Script
# --------------------------
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

# ANSI escape codes for colors
class Colors:
    USER  = '\033[92m'  # Green
    BOT   = '\033[94m'  # Blue
    ERROR = '\033[91m'  # Red
    INFO  = '\033[93m'  # Yellow
    ENDC  = '\033[0m'   # Reset

AVAILABLE_MODELS = [
    "gemini-1.5-flash",
    "gemini-2.0-flash",
    "gemini-2.0-flash-thinking",
    "gemini-1.5-pro",
    "gemini-2.0-pro",
    "gpt-4o",
    "gpt-4o-mini",
    "o1",
    "o3-mini",
    "llama-3.3-70b",
    "deepseek-r1",
    "claude-3.5-sonnet",
    "claude-3.7-sonnet",
]

def select_model() -> str:
    """
    Display a numbered list of AVAILABLE_MODELS and prompt user to select one.
    Returns the selected model name.
    """
    print(f"{Colors.INFO}Available models:{Colors.ENDC}")
    for idx, name in enumerate(AVAILABLE_MODELS, 1):
        print(f"{Colors.INFO}{idx}. {name}{Colors.ENDC}")

    while True:
        choice = input(f"{Colors.USER}Enter model number (1-{len(AVAILABLE_MODELS)}): {Colors.ENDC}").strip()
        if choice.lower() in {"q", "quit", "exit"}:
            return ""
        if not choice.isdigit():
            print(f"{Colors.ERROR}Invalid input. Please enter a number.{Colors.ENDC}")
            continue
        idx = int(choice)
        if 1 <= idx <= len(AVAILABLE_MODELS):
            return AVAILABLE_MODELS[idx - 1]
        print(f"{Colors.ERROR}Choice out of range. Try again.{Colors.ENDC}")


def main_chat_loop():
    model = select_model()
    if not model:
        logger.info("No model selected. Exiting.")
        return

    logger.info(f"Initializing LLM with model: {model}")
    try:
        llm = ChatOpenAI(
            base_url="http://localhost:1555/v1",
            model_name=model,
            temperature=0.5,
            api_key="11"  # replace with a valid key if needed
        )
        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a helpful assistant."),
            ("human", "{user_input}")
        ])
        parser = StrOutputParser()
        chain = prompt | llm | parser

        print(f"{Colors.INFO}ChatBot ready. Type 'quit' or 'exit' to leave.{Colors.ENDC}")
        print(f"{Colors.INFO}{'-'*40}{Colors.ENDC}")

    except Exception as e:
        logger.error(f"Failed to initialize LLM: {e}")
        return

    while True:
        try:
            user_input = input(f"{Colors.USER}You: {Colors.ENDC}").strip()
            if user_input.lower() in {"quit", "exit"}:
                logger.info("Session ended by user.")
                break
            if not user_input:
                continue

            response = chain.invoke({"user_input": user_input})
            print(f"{Colors.BOT}Bot: {response}{Colors.ENDC}")

        except KeyboardInterrupt:
            logger.info("Interrupted by user. Exiting.")
            break
        except ConnectionError as ce:
            logger.error(f"Connection error: {ce}")
        except Exception as e:
            logger.error(f"Unexpected error: {e}")


if __name__ == "__main__":
    main_chat_loop()
