# Multi-stage Dockerfile for MinIO Community Edition (GNU AGPLv3)
# Builds reproducibly from official open-source repository at pinned revision.
FROM golang:1.24-alpine AS builder

ARG MINIO_COMMIT=7aac2a2c5b7c882e68c1ce017d8256be2feea27f
ARG MC_VERSION=v0.0.0-20251106162529-77f82e18b540

RUN apk add --no-cache git ca-certificates

WORKDIR /src
RUN git init && \
    git remote add origin https://github.com/minio/minio.git && \
    git fetch --depth 1 origin ${MINIO_COMMIT} && \
    git checkout FETCH_HEAD && \
    CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /out/minio .

RUN CGO_ENABLED=0 GOBIN=/out go install github.com/minio/mc@${MC_VERSION}

# Minimal runtime stage
FROM alpine:3.20

LABEL maintainer="Construction Expense Team" \
      description="MinIO Community Edition built from official source (GNU AGPLv3)"

RUN apk add --no-cache ca-certificates curl tzdata

COPY --from=builder /out/minio /usr/bin/minio
COPY --from=builder /out/mc /usr/bin/mc
COPY docker-entrypoint.sh /usr/bin/docker-entrypoint.sh

RUN chmod +x /usr/bin/minio /usr/bin/mc /usr/bin/docker-entrypoint.sh && \
    mkdir -p /data

EXPOSE 9000 9001
VOLUME ["/data"]

ENTRYPOINT ["/usr/bin/docker-entrypoint.sh"]
CMD ["minio", "server", "/data"]
