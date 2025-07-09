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

# def verify_token(authorization: str = Header(...)):
#     if not authorization.startswith("Bearer "):
#         raise HTTPException(401, "Format de token invalide")

#     token = authorization.split(" ")[1]

#     # Validation auprès d'ARIA
#     try:
#         response = requests.get(
#             f"{ARIA_URL}/validate-token",
#             params={"token": token},
#             timeout=3
#         )
#         if response.status_code != 200:
#             raise HTTPException(401, "Token rejeté par ARIA")

#         claims = response.json()
#         if not claims["valid"]:
#             raise HTTPException(401, "Token invalide")

#         return claims
#     except requests.exceptions.RequestException:
#         raise HTTPException(503, "Service d'authentification indisponible")

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
    conn = sqlite3.connect("media.db")
    conn.row_factory = sqlite3.Row
    return conn

# Initialisation de la base de données
def init_db():
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
    return {"message": "Hello World"}

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
        raise HTTPException(400, detail="Les vidéos ne peuvent pas être des thumbnails")

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

@app.get("/media", response_model=List[MediaItem])
async def get_media_by_product( id_product: str = Query(..., alias="id_product", description="ID du produit")):
    """
    Récupère tous les médias associés à un produit
    """
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, product_id, file_name,file_url, file_type, is_thumbnail, created_at FROM medias WHERE product_id = ?",
            (id_product,)
        )
        medias = cursor.fetchall()

        if not medias:
            raise HTTPException(404, detail="Aucun média trouvé pour ce produit")

        return [
            {
                "id": media["id"],
                "product_id": media["product_id"],
                "file_name": media["file_name"],
                "file_url": media["file_url"],
                "file_type": media["file_type"],
                "is_thumbnail": bool(media["is_thumbnail"]),
                "created_at": media["created_at"]
            }
            for media in medias
        ]

    except sqlite3.Error as e:
        raise HTTPException(500, detail=f"Erreur BDD: {str(e)}")
    finally:
        conn.close()

@app.get("/thumbnail", response_model=MediaItem)
async def get_product_thumbnail(id_product: str = Query(..., alias="id_product", description="ID du produit")):
    """
    Récupère la vignette (thumbnail) associée à un produit
    - Retourne la première image marquée comme vignette (is_thumbnail=1)
    - Si aucune vignette spécifique, retourne la première image du produit
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

@app.delete("/media")
async def delete_media(id: str = Query(..., alias="id_media", description="ID du media")):
    """
    Supprime un média et son entrée en base de données
    """
    try:
        conn = get_db()
        cursor = conn.cursor()

        # Récupérer les informations du média
        cursor.execute(
            "SELECT file_url FROM medias WHERE id = ?",
            (id,)
        )
        media = cursor.fetchone()

        if not media:
            raise HTTPException(404, detail="Média non trouvé")

        blob_url = media["file_url"]

        # Delete from blob storage
        try:
            delete(blob_url)
        except Exception as e:
            print(f"Warning: Failed to delete blob {blob_url}: {str(e)}")


        # Supprimer l'entrée en base de données
        cursor.execute("DELETE FROM medias WHERE id = ?", (id,))
        conn.commit()

        return {"status": "deleted", "media_id": id}

    except sqlite3.Error as e:
        raise HTTPException(500, detail=f"Erreur BDD: {str(e)}")
    finally:
        conn.close()

@app.delete("/allmedia")
async def delete_all_media_for_product(
    id_product: str = Query(..., alias="id_product", description="ID du produit"),
    # authorization: str = Header(...)  # Uncomment when JWT is ready
):
    """
    Supprime TOUS les médias associés à un produit spécifique.

    Process:
    1. Récupère tous les médias liés au product_id
    2. Supprime chaque fichier du stockage Blob
    3. Supprime toutes les entrées en base de données

    Attention : Opération irréversible !
    """
    # 1. Vérification du token (à décommentez)
    # claims = verify_token(authorization)
    # if "admin" not in claims.get("roles", []):
    #    raise HTTPException(403, "Permissions insuffisantes")

    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()

        # Récupérer tous les médias du produit
        cursor.execute(
            "SELECT id, file_url FROM medias WHERE product_id = ?",
            (id_product,)
        )
        medias = cursor.fetchall()

        if not medias:
            raise HTTPException(404, f"Aucun média trouvé pour le produit {id_product}")

        deleted_files = 0
        errors = []

        # Collect all blob URLs to delete
        blob_urls = [media["file_url"] for media in medias]

        # Supprimer les fichiers du stockage Blob
        if blob_urls:
            try:
                # Delete all blobs in a single batch
                for url in blob_urls:
                    delete(url)
            except Exception as e:
                # Handle partial failures
                errors.append(f"Erreur suppression Blob: {str(e)}")

        # Supprimer les entrées en base
        cursor.execute("DELETE FROM medias WHERE product_id = ?", (id_product,))
        conn.commit()

        return {
            "status": "completed",
            "product_id": id_product,
            "deleted_blobs": deleted_files,
            "deleted_db_entries": len(medias),
            "errors": errors
        }

    except sqlite3.Error as e:
        if conn:
            conn.rollback()
        raise HTTPException(500, f"Erreur BDD: {str(e)}")
    finally:
        if conn:
            conn.close()

@app.put("/media", response_model=UploadResponse)
async def update_media(
    media_id: str = Query(..., alias="id_media", description="ID du media"),
    file: UploadFile = File(..., description="Nouveau fichier média"),
    # authorization: str = Header(...)  # Décommentez quand JWT sera actif
):
    """
    Met à jour un média existant en remplaçant son fichier tout en conservant:
    - Le même ID de média
    - Le même product_id associé

    Processus:
    1. Récupère le product_id du média existant
    2. Supprime l'ancien fichier physique
    3. Téléverse le nouveau fichier
    4. Met à jour les métadonnées en base de données

    Attention: Le type du nouveau fichier doit être le même que l'original!
    """
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(400, detail=f"Type non supporté. Types autorisés: {', '.join(ALLOWED_TYPES.keys())}")

    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT product_id, file_url, file_type, is_thumbnail FROM medias WHERE id = ?",
            (media_id,)
        )
        existing = cursor.fetchone()

        if not existing:
            raise HTTPException(404, detail="Média non trouvé")

        new_file_type = ALLOWED_TYPES[file.content_type]
        if new_file_type != existing["file_type"]:
            raise HTTPException(400,
                detail=f"Le type du fichier doit rester '{existing['file_type']}'. Type reçu: '{new_file_type}'")

        # Generate new filename
        file_ext = os.path.splitext(file.filename)[1]
        new_filename = f"{uuid.uuid4().hex}{file_ext}"

        # Upload new file to Blob
        content = await file.read()
        if len(content) > 100 * 1024 * 1024:
            raise HTTPException(413, detail="Fichier trop volumineux (>100MB)")

        put_result = put(
            path=new_filename,
            data=content,
            options={
                "access": 'public'
            }
        )
        new_blob_url = put_result['url']

        # Delete old blob
        try:
            delete(existing["file_url"])
        except Exception as e:
            print(f"Warning: Failed to delete old blob {existing['file_url']}: {str(e)}")

        # Update database
        cursor.execute(
            "UPDATE medias SET file_name = ?, file_url = ?, created_at = CURRENT_TIMESTAMP WHERE id = ?",
            (new_filename, new_blob_url, media_id)
        )
        conn.commit()

        return {
            "id": media_id,
            "file_url": new_blob_url,
            "product_id": existing["product_id"],
            "file_type": new_file_type,
            "is_thumbnail": bool(existing["is_thumbnail"])
        }

    except sqlite3.Error as e:
        if conn:
            conn.rollback()
        raise HTTPException(500, detail=f"Erreur BDD: {str(e)}")
    finally:
        if conn:
            conn.close()

@app.put("/thumbnail", response_model=MediaItem)
async def update_product_thumbnail(
    id_media: str = Query(..., alias="id_media", description="ID du média à définir comme vignette")
):
    """
    Met à jour la vignette d'un produit:
    1. Vérifie que le média existe et est une image
    2. Si le média est déjà une vignette, renvoie une erreur
    3. Sinon, met à jour:
       - Désactive l'ancienne vignette (is_thumbnail=0)
       - Définit le nouveau média comme vignette (is_thumbnail=1)
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
            raise HTTPException(400, detail="Seules les images peuvent être des vignettes")

        if media["is_thumbnail"] == 1:
            raise HTTPException(400, detail="Ce média est déjà la vignette actuelle")

        # 2. Désactiver l'ancienne vignette
        cursor.execute(
            """UPDATE medias
            SET is_thumbnail = 0
            WHERE product_id = ? AND is_thumbnail = 1""",
            (media["product_id"],)
        )

        # 3. Définir le nouveau média comme vignette
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