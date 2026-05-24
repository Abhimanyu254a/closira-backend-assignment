from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./closira.db"
    APP_NAME: str = "Closira Backend"
    DEBUG: bool = True

    class Config:
        env_file = ".env"


settings = Settings()