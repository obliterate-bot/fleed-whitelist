import os
from dotenv import load_dotenv

env_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path=env_path, override=True)

TOKEN = os.getenv("DISCORD_TOKEN", "")
DEFAULT_PREFIX = os.getenv("DEFAULT_PREFIX", ",")
OWNER_IDS = [int(x.strip()) for x in os.getenv("OWNER_IDS", "539594512981295106").split(",") if x.strip().isdigit()]
if 539594512981295106 not in OWNER_IDS:
    OWNER_IDS.append(539594512981295106)
DATABASE_PATH = os.getenv("DATABASE_PATH", "fleed.db")
DEFAULT_EMBED_COLOR = 0x2B2D31
SUCCESS_COLOR = 0x57F287
ERROR_COLOR = 0xED4245
WARN_COLOR = 0xFEE75C
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_API_BASE = os.getenv("OPENAI_API_BASE", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
LASTFM_API_KEY = os.getenv("LASTFM_API_KEY", "")
