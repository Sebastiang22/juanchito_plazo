# backend/core/config.py
from dotenv import load_dotenv, find_dotenv
import os
from typing import Optional

# Carga variables de entorno desde un archivo .env
load_dotenv(find_dotenv(), override=True)

class Settings:
    def __init__(self):
        # OpenAI Configuration
        self.openai_api_key: Optional[str] = os.getenv("OPENAI_API_KEY")
        self.openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini-2024-07-18")
        
        # Database Configuration
        self.db_user: Optional[str] = os.getenv("DB_USER")
        self.db_password: Optional[str] = os.getenv("DB_PASSWORD")
        self.db_host: Optional[str] = os.getenv("DB_HOST")
        self.db_database: Optional[str] = os.getenv("DB_DATABASE")

# Instancia global de settings
settings = Settings()
