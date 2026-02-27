from pydantic import BaseModel
from datetime import datetime

class MediaItem(BaseModel):
    id: str
    product_id: str
    file_name: str
    file_url: str
    file_type: str
    is_thumbnail: bool
    created_at: datetime

class UploadResponse(BaseModel):
    id: str
    file_url: str
    product_id: str
    file_type: str
    is_thumbnail: bool

# Optional for validation endpoint
class ValidationResult(BaseModel):
    valid: bool
    userId: str
    email: str
    expiresAt: str