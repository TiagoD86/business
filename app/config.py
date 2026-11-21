from decimal import Decimal
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    app_api_key: str = Field(min_length=24)
    database_url: str = 'sqlite:///./business_ai_os.db'
    initial_capital_brl: Decimal = Decimal('2000')
    monthly_ai_budget_brl: Decimal = Decimal('50')
    gemini_max_workflow_brl: Decimal = Decimal('1.00')
    gemini_api_key: str = ''
    gemini_model: str = 'gemini-2.5-flash'
    session_cookie_name: str = 'baios_session'
    session_ttl_hours: int = Field(default=24, ge=1, le=720)
    session_cookie_secure: bool = False
