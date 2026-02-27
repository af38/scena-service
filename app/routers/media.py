import sqlite3
from typing import List
import uuid

from fastapi import APIRouter, Depends, UploadFile, File, Form, Query, HTTPException
from .. import models, services
from ..config import settings
from ..dependencies import get_db
from ..services import blob_storage, media_service
import os

from vercel_blob import put
from vercel_blob import list, delete, put

router = APIRouter(prefix="/media", tags=["media"])
allowed_types = settings.allowed_types

@router.post("/upload", response_model=models.UploadResponse)
async def upload_file(
    product_id: str = Form(...),
    file: UploadFile = File(...),
    is_thumbnail: bool = Query(False)
):
    # Validate file type
    if file.content_type not in allowed_types:
        raise HTTPException(400, detail=f"Unsupported type. Allowed: {list(allowed_types.keys())}")

    file_type = allowed_types[file.content_type]

    if file_type == 'video' and is_thumbnail:
        raise HTTPException(400, detail="Videos cannot be thumbnails")

    # Read content
    content = await file.read()
    if len(content) > settings.max_file_size:
        raise HTTPException(413, detail="File too large (>100MB)")

    # Upload to blob
    file_ext = os.path.splitext(file.filename)[1]
    blob_url = await blob_storage.upload_blob(content, file.filename, file_ext)

    # Save to DB
    media_id = await media_service.create_media(
        product_id=product_id,
        file_type=file_type,
        is_thumbnail=is_thumbnail,
        blob_url=blob_url,
        filename=file.filename
    )

    return models.UploadResponse(
        id=media_id,
        file_url=blob_url,
        product_id=product_id,
        file_type=file_type,
        is_thumbnail=is_thumbnail and file_type == 'image'
    )

@router.put("/update", response_model=models.UploadResponse)
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
    if file.content_type not in allowed_types:
        raise HTTPException(400, detail=f"Type non supporté. Types autorisés: {', '.join(allowed_types.keys())}")

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

        new_file_type = allowed_types[file.content_type]
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


@router.delete("/all")
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


@router.delete("/")
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

@router.get("/", response_model=List[models.MediaItem])
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
