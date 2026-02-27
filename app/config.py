from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    base_url: str = "http://localhost:8000"
    allowed_types: dict = {
        "image/jpeg": "image",
        "image/png": "image",
        "image/gif": "image",
        "video/mp4": "video",
        "video/quicktime": "video",
        "video/x-msvideo": "video"
    }
    max_file_size: int = 100 * 1024 * 1024  # 100 MB
    aria_url: str = "http://aria.onrender.com"

    class Config:
        env_file = ".env"

settings = Settings()