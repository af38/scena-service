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

# Initialisation de l'application
app = FastAPI()

# Configuration CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)

# Configuration du stockage
IS_RENDER = os.getenv("RENDER", False)
UPLOAD_DIR = "/var/data/uploads" if IS_RENDER else "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/media", StaticFiles(directory=UPLOAD_DIR), name="static_media")

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
SERVICE_CREDENTIALS = {
    "email": "scena_service@marketplace.com",  # Identifiants dédiés au service SCENA
    "password": "votre_mot_de_passe_super_secret"  # À stocker dans .env !
}

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
    created_at: str

class UploadResponse(BaseModel):
    id: str
    file_url: str
    product_id: str
    file_type: str

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
            file_type TEXT CHECK(file_type IN ('image', 'video')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

init_db()

### Endpoints ###

@app.post("/upload", response_model=UploadResponse)
async def upload_file(
    product_id: str = Form(..., description="ID du produit associé"),
    file: UploadFile = File(..., description="Fichier média (image ou vidéo)")
):
    """
    Téléverse un fichier média et l'associe à un produit
    """
    # Validation du type de fichier
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(400, detail=f"Type non supporté. Types autorisés: {', '.join(ALLOWED_TYPES.keys())}")

    # Génération d'un nom de fichier unique
    file_ext = os.path.splitext(file.filename)[1]
    new_filename = f"{uuid.uuid4().hex}{file_ext}"
    file_path = os.path.join(UPLOAD_DIR, new_filename)

    # Sauvegarde du fichier
    try:
        with open(file_path, "wb") as buffer:
            content = await file.read()
            if len(content) > 100 * 1024 * 1024:  # 100MB max
                raise HTTPException(413, detail="Fichier trop volumineux (>100MB)")
            buffer.write(content)
    except Exception as e:
        raise HTTPException(500, detail=f"Erreur de sauvegarde: {str(e)}")

    # Enregistrement en base de données
    media_id = uuid.uuid4().hex
    file_type = ALLOWED_TYPES[file.content_type]

    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO medias (id, product_id, file_name, file_type) VALUES (?, ?, ?, ?)",
            (media_id, product_id, new_filename, file_type)
        )
        conn.commit()
    except sqlite3.Error as e:
        os.remove(file_path)  # Nettoyer le fichier en cas d'erreur
        raise HTTPException(500, detail=f"Erreur BDD: {str(e)}")
    finally:
        conn.close()

    return {
        "id": media_id,
        "file_url": f"/media/{new_filename}",
        "product_id": product_id,
        "file_type": file_type
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
            "SELECT id, product_id, file_name, file_type, created_at FROM medias WHERE product_id = ?",
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
                "file_url": f"/media/{media['file_name']}",
                "file_type": media["file_type"],
                "created_at": media["created_at"]
            }
            for media in medias
        ]

    except sqlite3.Error as e:
        raise HTTPException(500, detail=f"Erreur BDD: {str(e)}")
    finally:
        conn.close()

@app.delete("/media")
async def delete_media(id: str = Query(..., alias="id_product", description="ID du produit")):
    """
    Supprime un média et son entrée en base de données
    """
    try:
        conn = get_db()
        cursor = conn.cursor()

        # Récupérer les informations du média
        cursor.execute(
            "SELECT file_name FROM medias WHERE id = ?",
            (id,)
        )
        media = cursor.fetchone()

        if not media:
            raise HTTPException(404, detail="Média non trouvé")

        file_name = media["file_name"]
        file_path = os.path.join(UPLOAD_DIR, file_name)

        # Supprimer le fichier physique
        if os.path.exists(file_path):
            os.remove(file_path)

        # Supprimer l'entrée en base de données
        cursor.execute("DELETE FROM medias WHERE id = ?", (id,))
        conn.commit()

        return {"status": "deleted", "media_id": id}

    except sqlite3.Error as e:
        raise HTTPException(500, detail=f"Erreur BDD: {str(e)}")
    except OSError as e:
        raise HTTPException(500, detail=f"Erreur fichier: {str(e)}")
    finally:
        conn.close()

@app.get("/allmedia", response_model=List[MediaItem])
async def get_all_media():
    """
    Récupère tous les médias (sans pagination)
    Requiert une authentification JWT valide
    authorization: str = Header(...)
    """

    # Vérification du token
    # if not authorization.startswith("Bearer "):
    #     raise HTTPException(401, "Format de token invalide")

    # token = authorization.split(" ")[1]

    # # Validation auprès d'ARIA
    # try:
    #     auth_response = requests.get(
    #         f"{ARIA_URL}/validate-token",
    #         params={"token": token},
    #         timeout=3
    #     )

    #     if auth_response.status_code != 200 or not auth_response.json().get("valid"):
    #         raise HTTPException(401, "Token invalide ou expiré")

    # except requests.exceptions.RequestException:
    #     raise HTTPException(503, "Service d'authentification indisponible")

    # Récupération des médias
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, product_id, file_name, file_type, created_at FROM medias ORDER BY created_at DESC"
        )
        medias = cursor.fetchall()

        return [
            {
                "id": media["id"],
                "product_id": media["product_id"],
                "file_name": media["file_name"],
                "file_url": f"/media/{media['file_name']}",
                "file_type": media["file_type"],
                "created_at": media["created_at"]
            }
            for media in medias
        ]

    except sqlite3.Error as e:
        raise HTTPException(500, detail=f"Erreur BDD: {str(e)}")
    finally:
        conn.close()

# Pour exécuter en local
# if __name__ == "__main__":

#     conn = sqlite3.connect("media.db")
#     print(conn.execute("SELECT * FROM medias").fetchall())  # Affiche toutes les entrées
#     conn.close()

#     import uvicorn
#     uvicorn.run(app, host="0.0.0.0", port=8000)