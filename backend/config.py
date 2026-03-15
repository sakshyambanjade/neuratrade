"""
Central configuration. Load from environment with safe defaults for paper trading.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# Core
APP_NAME = "prajnyavan-btc-bot"
ENV = os.getenv("ENV", "dev")

# Ports
API_PORT = int(os.getenv("API_PORT", 8000))
WS_PATH = "/ws"

# Data / DB
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_env_db = os.getenv("DB_PATH", "")
if _env_db:
    DB_PATH = _env_db if os.path.isabs(_env_db) else os.path.join(BASE_DIR, _env_db)
else:
    DB_PATH = os.path.join(BASE_DIR, "trading.db")
DB_URL = f"sqlite:///{DB_PATH}"
SQLITE_BUSY_TIMEOUT_MS = int(os.getenv("SQLITE_BUSY_TIMEOUT_MS", 5000))

# Market
SYMBOL = os.getenv("SYMBOL", "BTCUSDT")
TICK_INTERVAL_SECONDS = int(os.getenv("TICK_INTERVAL_SECONDS", 300))  # 5 min
BINANCE_BASE = "https://api.binance.com"
COINGECKO_BASE = "https://api.coingecko.com/api/v3"

# Risk
MAX_POSITION_PCT = float(os.getenv("MAX_POSITION_PCT", 0.25))
MAX_OPEN_TRADES = int(os.getenv("MAX_OPEN_TRADES", 1))
MAX_DAILY_TRADES = int(os.getenv("MAX_DAILY_TRADES", 12))
MAX_DRAWDOWN_PCT = float(os.getenv("MAX_DRAWDOWN_PCT", 0.08))
MIN_CONFIDENCE = float(os.getenv("MIN_CONFIDENCE", 0.35))

# LLM / Brain
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
LLM_MODEL = os.getenv("LLM_MODEL", "tinyllama")
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", 20))
BRAIN_URL = os.getenv("BRAIN_URL", "http://127.0.0.1:8742")
BRAIN_SECRET = os.getenv("BRAIN_SECRET", "dev-secret")
USER_ID = os.getenv("USER_ID", "btc_trader")

# Prajnyavan (optional SDK)
PRAJ_BASE_URL = os.getenv("PRAJ_BASE_URL", "http://127.0.0.1:9999")
PRAJ_TOKEN = os.getenv("PRAJ_TOKEN", "")
PRAJ_EMBED_PROVIDER = os.getenv("PRAJ_EMBED_PROVIDER", "openai")  # openai | cohere | local
PRAJ_EMBED_MODEL = os.getenv("PRAJ_EMBED_MODEL", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
COHERE_API_KEY = os.getenv("COHERE_API_KEY", "")

# Auth
API_KEY = os.getenv("API_KEY", "dev-key")  # replace in prod
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",")

# Misc
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
HEARTBEAT_SECONDS = int(os.getenv("HEARTBEAT_SECONDS", 420))  # alert threshold for ticks

# Event bus
REDIS_URL = os.getenv("REDIS_URL", "")
