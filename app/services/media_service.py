from ..database import get_db as _get_db
from ..models import MediaItem
from fastapi import HTTPException
import uuid
from datetime import datetime

async def create_media(product_id: str, file_type: str, is_thumbnail: bool, blob_url: str, filename: str):
    media_id = uuid.uuid4().hex
    with _get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO medias (id, product_id, file_name, file_url, file_type, is_thumbnail) VALUES (?, ?, ?, ?, ?, ?)",
            (media_id, product_id, filename, blob_url, file_type, 1 if is_thumbnail and file_type == 'image' else 0)
        )
        conn.commit()
    return media_id

def get_media_by_product(product_id: str):
    with _get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, product_id, file_name, file_url, file_type, is_thumbnail, created_at FROM medias WHERE product_id = ?",
            (product_id,)
        )
        rows = cursor.fetchall()
        if not rows:
            raise HTTPException(404, "No media found for this product")
        return [MediaItem(**dict(row)) for row in rows]

# Similarly move other functions: delete_media, update_media, etc.