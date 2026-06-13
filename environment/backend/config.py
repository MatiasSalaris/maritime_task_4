from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    provider: str = "sim"   # "sim" | "hardware"
    tick_rate: int = 10      # Hz — world state broadcast frequency
    host: str = "0.0.0.0"
    port: int = 8000

    class Config:
        env_file = ".env"


settings = Settings()
