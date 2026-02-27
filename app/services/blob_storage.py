from vercel_blob import put, delete, list
from fastapi import HTTPException
import uuid
import os

async def upload_blob(content: bytes, filename: str, file_ext: str) -> str:
    new_filename = f"{uuid.uuid4().hex}{file_ext}"
    try:
        result = put(path=new_filename, data=content, options={"access": "public"})
        return result['url']
    except Exception as e:
        raise HTTPException(500, f"Blob upload failed: {str(e)}")

def delete_blob(url: str):
    try:
        delete(url)
    except Exception as e:
        # Log error but don't fail the whole request
        print(f"Blob deletion error: {e}")