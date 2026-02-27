from fastapi import FastAPI, Header, Query, UploadFile, File, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlite3
import os
import uuid
from datetime import datetime
from typing import List, Optional
import requests
from vercel_blob import put
from vercel_blob import list, delete, put

# Initialisation de l'application
app = FastAPI()

# Configuration CORS
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add this after your other environment setup
BASE_URL = os.getenv("BASE_URL")
if not BASE_URL:
    VERCEL_URL = os.getenv("VERCEL_URL")
    if VERCEL_URL:
        BASE_URL = f"https://{VERCEL_URL}"
    else:
        BASE_URL = "http://localhost:8000"  # Default for local development


# Types de fichiers autorisés
ALLOWED_TYPES = {
    "image/jpeg": "image",
    "image/png": "image",
    "image/gif": "image",
    "video/mp4": "video",
    "video/quicktime": "video",
    "video/x-msvideo": "video"
}
ARIA_URL = "http://aria.onrender.com"

# Modèles Pydantic
class MediaItem(BaseModel):
    id: str
    product_id: str
    file_name: str
    file_url: str
    file_type: str
    is_thumbnail: bool
    created_at: str

class UploadResponse(BaseModel):
    id: str
    file_url: str
    product_id: str
    file_type: str
    is_thumbnail: bool

# Modèle de réponse de validation
class ValidationResult(BaseModel):
    valid: bool
    userId: str
    email: str
    expiresAt: str

# Connexion à la base de données
def get_db():
    db_path = "/tmp/media.db" if os.environ.get('VERCEL') else "media.db"
    conn = sqlite3.connect(
        db_path,
        check_same_thread=False,
        timeout=10  # Add timeout to prevent locking issues
        )
    conn.execute("PRAGMA journal_mode=WAL")  # Better concurrency
    conn.row_factory = sqlite3.Row
    return conn

# Initialisation de la base de données
def init_db():
    # Ensure /tmp exists in Vercel environment
    if os.environ.get('VERCEL'):
        os.makedirs("/tmp", exist_ok=True)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS medias (
            id TEXT PRIMARY KEY,
            product_id TEXT NOT NULL,
            file_name TEXT NOT NULL,
            file_url TEXT NOT NULL,
            file_type TEXT CHECK(file_type IN ('image', 'video')),
            is_thumbnail INTEGER DEFAULT 0 CHECK(
                (file_type = 'image' AND is_thumbnail IN (0, 1)) OR
                (file_type = 'video' AND is_thumbnail = 0)
            ),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

init_db()

### Endpoints ###

@app.get("/")
async def root():
    return {"message": "scena service"}

@app.post("/upload", response_model=UploadResponse)
async def upload_file(
    product_id: str = Form(..., description="ID du produit associé"),
    file: UploadFile = File(..., description="Fichier média (image ou vidéo)"),
    is_thumbnail: bool = Query(False, alias="is_thumbnail")
):
    # Validation du type de fichier
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(400, detail=f"Type non supporté. Types autorisés: {', '.join(ALLOWED_TYPES.keys())}")

    file_type = ALLOWED_TYPES[file.content_type]

    # Force is_thumbnail=False for videos
    if file_type == 'video' and is_thumbnail:
        raise HTTPException(400, detail="Les vidéos ne peuvent pas être des miniatures")

    # Generate unique filename
    file_ext = os.path.splitext(file.filename)[1]
    new_filename = f"{uuid.uuid4().hex}{file_ext}"

    # Upload to Vercel Blob
    try:
        content = await file.read()
        if len(content) > 100 * 1024 * 1024:  # 100MB max
            raise HTTPException(413, detail="Fichier trop volumineux (>100MB)")

        # Upload to Vercel Blob
        put_result = put(
            path=new_filename,
            data=content,
            options={"access": "public"}
        )
        blob_url = put_result['url']
    except Exception as e:
        raise HTTPException(500, detail=f"Erreur Blob: {str(e)}")

    # Save to database
    media_id = uuid.uuid4().hex
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO medias (id, product_id, file_name, file_url, file_type, is_thumbnail) VALUES (?, ?, ?, ?, ?, ?)",
            (media_id, product_id, new_filename, blob_url, file_type, 1 if (file_type == 'image' and is_thumbnail) else 0))

        conn.commit()
    except sqlite3.Error as e:
        # Attempt to delete blob if DB fails
        try:
            delete(blob_url)
        except:
            pass
        raise HTTPException(500, detail=f"Erreur BDD: {str(e)}")
    finally:
        conn.close()

    return {
        "id": media_id,
        "file_url": blob_url,
        "product_id": product_id,
        "file_type": file_type,
        "is_thumbnail": is_thumbnail if file_type == 'image' else False
    }


@app.get("/thumbnail", response_model=MediaItem)
async def get_product_thumbnail(id_product: str = Query(..., alias="id_product", description="ID du produit")):
    """
    Récupère la miniature (thumbnail) associée à un produit
    - Retourne la première image marquée comme miniature (is_thumbnail=1)
    - Si aucune miniature spécifique, retourne la première image du produit
    - Retourne une erreur 404 si aucun média image n'existe pour ce produit
    """
    try:
        conn = get_db()
        cursor = conn.cursor()

        # Try to find an explicitly marked thumbnail first
        cursor.execute(
            """SELECT id, product_id, file_name, file_url, file_type, is_thumbnail, created_at
            FROM medias
            WHERE product_id = ? AND file_type = 'image' AND is_thumbnail = 1
            LIMIT 1""",
            (id_product,)
        )
        thumbnail = cursor.fetchone()

        # # If no explicit thumbnail, get the first image
        # if not thumbnail:
        #     cursor.execute(
        #         """SELECT id, product_id, file_name, file_url, file_type, is_thumbnail, created_at
        #         FROM medias
        #         WHERE product_id = ? AND file_type = 'image'
        #         LIMIT 1""",
        #         (id_product,)
        #     )
        #     thumbnail = cursor.fetchone()

        if not thumbnail:
            raise HTTPException(404, detail="Aucun média image comme thumbnail trouvé pour ce produit")

        return {
            "id": thumbnail["id"],
            "product_id": thumbnail["product_id"],
            "file_name": thumbnail["file_name"],
            "file_url": thumbnail["file_url"],
            "file_type": thumbnail["file_type"],
            "is_thumbnail": bool(thumbnail["is_thumbnail"]),
            "created_at": thumbnail["created_at"]
        }

    except sqlite3.Error as e:
        raise HTTPException(500, detail=f"Erreur BDD: {str(e)}")
    finally:
        conn.close()



@app.put("/thumbnail", response_model=MediaItem)
async def update_product_thumbnail(
    id_media: str = Query(..., alias="id_media", description="ID du média à définir comme miniature")
):
    """
    Met à jour la miniature d'un produit:
    1. Vérifie que le média existe et est une image
    2. Si le média est déjà une miniature, renvoie une erreur
    3. Sinon, met à jour:
       - Désactive l'ancienne miniature (is_thumbnail=0)
       - Définit le nouveau média comme miniature (is_thumbnail=1)
    """
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()

        # 1. Vérifier que le média existe et est une image
        cursor.execute(
            """SELECT id, product_id, file_type, is_thumbnail
            FROM medias
            WHERE id = ?""",
            (id_media,)
        )
        media = cursor.fetchone()

        if not media:
            raise HTTPException(404, detail="Média non trouvé")

        if media["file_type"] != "image":
            raise HTTPException(400, detail="Seules les images peuvent être des miniatures")

        if media["is_thumbnail"] == 1:
            raise HTTPException(400, detail="Ce média est déjà la miniature actuelle")

        # 2. Désactiver l'ancienne miniature
        cursor.execute(
            """UPDATE medias
            SET is_thumbnail = 0
            WHERE product_id = ? AND is_thumbnail = 1""",
            (media["product_id"],)
        )

        # 3. Définir le nouveau média comme miniature
        cursor.execute(
            """UPDATE medias
            SET is_thumbnail = 1
            WHERE id = ?""",
            (id_media,)
        )

        # 4. Récupérer les données mises à jour
        cursor.execute(
            """SELECT id, product_id, file_name, file_url, file_type, is_thumbnail, created_at
            FROM medias
            WHERE id = ?""",
            (id_media,)
        )
        updated_media = cursor.fetchone()

        conn.commit()

        return {
            "id": updated_media["id"],
            "product_id": updated_media["product_id"],
            "file_name": updated_media["file_name"],
            "file_url": updated_media["file_url"],
            "file_type": updated_media["file_type"],
            "is_thumbnail": bool(updated_media["is_thumbnail"]),
            "created_at": updated_media["created_at"]
        }

    except sqlite3.Error as e:
        if conn:
            conn.rollback()
        raise HTTPException(500, detail=f"Erreur BDD: {str(e)}")
    finally:
        if conn:
            conn.close()


# Pour exécuter en local
# if __name__ == "__main__":

#     conn = sqlite3.connect("media.db")
#     print(conn.execute("SELECT * FROM medias").fetchall())  # Affiche toutes les entrées
#     conn.close()

#     import uvicorn
#     uvicorn.run(app, host="0.0.0.0", port=8000)