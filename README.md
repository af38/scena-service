# Scena Media Service

Scena Media Service is a production-ready REST API service built with FastAPI that handles media file management for product catalogs. This service enables developers to upload, store, retrieve, and manage image and video files with built-in thumbnail support, file type validation, and cloud storage integration. Designed for simplicity and scalability, it provides a robust foundation for e-commerce platforms and any application requiring structured media asset management.

## What is Scena Media Service?

Scena Media Service serves as a centralized media management API that abstracts the complexities of file storage, metadata tracking, and access control. The service maintains product-media relationships in a SQLite database while storing actual files in Vercel Blob Storage, providing a clean separation between metadata and binary assets. It supports both images and videos, with special handling for thumbnails that allows products to have designated preview images. The service is designed to run seamlessly in local development environments and on Vercel's serverless platform.

### Media Upload and Management

Upload media files with automatic content type detection and validation. The service supports common image formats (JPEG, PNG, GIF) and video formats (MP4, QuickTime, AVI) with a 100MB file size limit. Each upload is associated with a product ID, enabling organized media collections per product.

### Thumbnail System

Automatic thumbnail management allows products to have designated preview images. When uploading an image, you can mark it as a thumbnail (`is_thumbnail=true`), and the service ensures only one thumbnail exists per product, automatically updating previous thumbnails when a new one is set.

### File Type Validation and Security

Built-in security features include MIME type validation against an allowlist, file size enforcement, and filename sanitization. The service prevents unauthorized file types from being uploaded and enforces business logic rules like preventing videos from being set as thumbnails.

### Cloud Storage Integration

Seamless integration with Vercel Blob Storage handles actual file storage, providing public access URLs and automatic content delivery. The service manages blob upload, deletion, and URL generation transparently.

## Technical Stack

| Component             | Technology                | Purpose                                                                                |
| --------------------- | ------------------------- | -------------------------------------------------------------------------------------- |
| Web Framework         | FastAPI 0.115.12          | High-performance async web framework with automatic API documentation                  |
| Database              | SQLite                    | Lightweight embedded database for media metadata storage with WAL mode for concurrency |
| Cloud Storage         | Vercel Blob Storage 0.4.2 | Serverless object storage for media files with public access URLs                      |
| Data Validation       | Pydantic 2.11.5           | Runtime type checking and settings management                                          |
| ASGI Server           | Uvicorn 0.34.3            | Production-grade ASGI server for running FastAPI applications                          |
| CORS Handling         | FastAPI CORSMiddleware    | Cross-Origin Resource Sharing configuration for frontend integration                   |
| Dependency Management | python-dotenv 1.1.0       | Environment variable loading from .env files                                           |

## Quick API Summary

The service provides a RESTful API with the following core endpoints:

| Endpoint        | Method | Description                                            |
| --------------- | ------ | ------------------------------------------------------ |
| `/`             | GET    | Health check endpoint returning service status         |
| `/media/upload` | POST   | Upload a new media file (image or video) for a product |
| `/media/`       | GET    | Retrieve all media files for a specific product        |
| `/media/update` | PUT    | Update an existing media file                          |
| `/media/`       | DELETE | Delete a specific media file by ID                     |
| `/media/all`    | DELETE | Delete all media files for a specific product          |
| `/thumbnail`    | GET    | Retrieve the thumbnail image for a product             |
| `/thumbnail`    | PUT    | Set a specific media item as the product thumbnail     |

## Configuration Options

| Setting         | Default Value                                                                   | Description                                                  |
| --------------- | ------------------------------------------------------------------------------- | ------------------------------------------------------------ |
| `base_url`      | `http://localhost:8000`                                                         | Base URL for the service, auto-detects in Vercel environment |
| `max_file_size` | 100 MB                                                                          | Maximum allowed file size for uploads                        |
| `allowed_types` | `image/jpeg, image/png, image/gif, video/mp4, video/quicktime, video/x-msvideo` | MIME types permitted for upload                              |
| `aria_url`      | `http://aria.onrender.com`                                                      | External service URL for integration (if applicable)         |
| `VERCEL`        | Environment variable                                                            | Presence indicates Vercel deployment environment             |

## Database Schema

The service uses a single SQLite table with the following schema:

| Column         | Type      | Constraints                          | Description                            |
| -------------- | --------- | ------------------------------------ | -------------------------------------- |
| `id`           | TEXT      | PRIMARY KEY                          | Unique identifier for the media item   |
| `product_id`   | TEXT      | NOT NULL                             | Associated product identifier          |
| `file_name`    | TEXT      | NOT NULL                             | Original filename of the uploaded file |
| `file_url`     | TEXT      | NOT NULL                             | Public URL to the stored file          |
| `file_type`    | TEXT      | CHECK (image/video)                  | Media type classification              |
| `is_thumbnail` | INTEGER   | CHECK (0/1 for images, 0 for videos) | Thumbnail flag (1 = is thumbnail)      |
| `created_at`   | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP            | Upload timestamp                       |
