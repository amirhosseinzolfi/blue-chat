# Blue Chat

Blue Chat is a conversational AI chatbot built with Chainlit, LangChain, LangGraph, and SQLite.  
It provides real‐time chat powered by GPT-4, with automatic summarization, persistence, and user authentication.

## Features
- Interactive AI conversations via Chainlit  
- Automatic conversation summarization with LangGraph  
- Persistent storage & in-place schema migrations (SQLite)  
- Password‐protected sidebar (Chainlit)  
- Structured, context‐aware logging  

## Prerequisites
- Python 3.8 or higher  
- SQLite  
- An OpenAI API key  

## Installation

```bash
git clone https://github.com/your-org/blue_chat.git
cd blue_chat
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configuration

Copy and export your OpenAI key:

```bash
export OPENAI_API_KEY="your_real_key_here"
```

You can override default endpoints or keys by setting:
- `OPENAI_API_KEY`  
- `CHATBOT_DB` (defaults to `./chatbot_messagesstate_v2.sqlite`)  
- `LANGGRAPH_CHECKPOINT_DB_FILE` (defaults to `./langgraph_checkpoints.sqlite`)  

## Usage

Run the Chainlit app:

```bash
chainlit run langgraph_chainlit_app.py
```

Then open `http://localhost:8000` in your browser and log in with:
- **Username:** admin  
- **Password:** admin  

## Project Structure

- `langgraph_chainlit_app.py` – main application  
- `requirements.txt`      – pinned dependencies  
- `README.md`             – this documentation  
- `logger_utils.py`       – custom logging helpers  
- `chatbot_messagesstate_v2.sqlite` – Chainlit state DB  
- `langgraph_checkpoints.sqlite`    – LangGraph checkpoint DB  

## Logging

All operations emit structured logs via `logger_utils`. Check the console or redirect to a file for audit trails.

## License

This project is licensed under the MIT License.  
