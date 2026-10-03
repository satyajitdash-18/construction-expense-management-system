# MinIO Community Edition Container

This directory provides the Docker packaging for MinIO Community Edition (GNU AGPLv3).

## Background
Upstream releases distributed under commercial channels (`quay.io/minio/aistor/minio`) require commercial licenses and run in offline mode with all S3 operations denied if unlicensed.

To ensure long-term stability, open-source compliance, and reproducible environments, this container builds the official MinIO Community Edition server and client (`mc`) from the official open-source repositories under GNU AGPLv3.

## Reproducible Multi-Stage Build
The image is built reproducibly without requiring any local Go compiler or precompiled binaries on the host:
- **MinIO Server Source**: Pinned to official commit `7aac2a2c5b7c882e68c1ce017d8256be2feea27f` (License: GNU AGPLv3).
- **MinIO Client (`mc`)**: Pinned to official release revision `v0.0.0-20251106162529-77f82e18b540` (License: GNU AGPLv3).
- **Builder Stage**: `golang:1.24-alpine` builds static binaries with `CGO_ENABLED=0` and stripped symbols (`-s -w`).
- **Runtime Stage**: `alpine:3.20` containing only `ca-certificates`, `curl`, `tzdata`, `minio`, `mc`, and `docker-entrypoint.sh`.

## Build
```bash
docker build -t construction-minio:community infrastructure/docker/minio
```
Or via Docker Compose:
```bash
docker compose --env-file .env -f infrastructure/docker-compose.yml build minio
```

## Security & Operations
- Root credentials must be provided via `MINIO_ROOT_USER` (or `MINIO_ACCESS_KEY`) and `MINIO_ROOT_PASSWORD` (or `MINIO_SECRET_KEY`).
- Default credentials (`minioadmin:minioadmin`) must not be used in production.
- Health checks use `mc ready local` or HTTP live probe `curl -f http://localhost:9000/minio/health/live`.
