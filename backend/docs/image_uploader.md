# Image Uploader Module

## Purpose
Provide a pluggable image upload adapter for prompt builder charts.
The prompt builder should not care which hosting service is used; it
only expects URLs back from the uploader.

## Current Implementations
- File system uploader (default): writes PNGs locally and returns file paths
  or URLs if `BACKEND_PROMPT_IMAGE_BASE_URL` is set.
- ImgBB uploader: uploads via the ImgBB API and returns hosted URLs.
- freeimage.host uploader: uploads via freeimage.host and returns hosted URLs.

## Configuration (env)
```
BACKEND_PROMPT_IMAGE_UPLOADER=filesystem  # filesystem, imgbb, freeimage
BACKEND_PROMPT_IMAGE_STORE_PATH=backend/tmp/prompt_images
BACKEND_PROMPT_IMAGE_BASE_URL=
BACKEND_PROMPT_IMAGE_UPLOAD_CONCURRENCY=4
BACKEND_PROMPT_IMAGE_IMGBB_API_KEY=
BACKEND_PROMPT_IMAGE_IMGBB_API_URL=https://api.imgbb.com/1/upload
BACKEND_PROMPT_IMAGE_FREEIMAGE_API_KEY=
BACKEND_PROMPT_IMAGE_FREEIMAGE_API_URL=https://freeimage.host/api/1/upload
```

## Configuration (API)
Use the integrations API to set the active hosting provider and API key. This
stores the config in the DB and overrides env defaults.

Endpoints:
- `GET /api/v1/integrations/image-uploader`
- `PUT /api/v1/integrations/image-uploader`

Rules:
- `provider` must be `filesystem`, `imgbb`, or `freeimage` (accepts `freeimage.host`).
- `api_key` is required for `imgbb` and `freeimage` unless already configured.
- Switching to `filesystem` clears any stored API key.

Example:
```
curl -X PUT http://localhost:8000/api/v1/integrations/image-uploader \
  -H 'Content-Type: application/json' \
  -d '{"provider":"imgbb","api_key":"YOUR_KEY"}'
```

## Extension Points
To add another provider:
1) Implement `upload(image_bytes, name) -> url` in a new class.
2) Register it in `build_image_uploader()` based on env/config.
3) Keep the interface async so prompt builder can upload multiple images
   concurrently.

## DB Configuration
- Table: `image_uploader_config`
- Fields: `provider`, `api_key`
- When set, DB configuration overrides env defaults.

## Concurrency
Prompt builder uploads are run with a semaphore to avoid overwhelming
the remote service. Set concurrency via `BACKEND_PROMPT_IMAGE_UPLOAD_CONCURRENCY`.

## CLI
```
PYTHONPATH=backend/src python -m app.cli image-uploader show
PYTHONPATH=backend/src python -m app.cli image-uploader set --provider imgbb --api-key YOUR_KEY
PYTHONPATH=backend/src python -m app.cli image-uploader set --provider freeimage --api-key YOUR_KEY
PYTHONPATH=backend/src python -m app.cli image-uploader test
```
