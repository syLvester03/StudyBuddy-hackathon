import os
from datetime import timedelta
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()


class Config:
    # Flask
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)

    # MySQL
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = int(os.getenv("DB_PORT", 3306))
    DB_NAME = os.getenv("DB_NAME", "studybuddy")
    DB_USER = os.getenv("DB_USER", "root")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")

    # Groq / LLM
    GROQ_API_KEY = os.getenv("api_key")  # as requested
    GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-70b-versatile")