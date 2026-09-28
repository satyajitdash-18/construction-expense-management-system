# Deployment Guide

## Prerequisites

- Docker 24.0+
- Docker Compose 2.0+
- 4GB+ RAM
- 20GB+ disk space

## Quick Start

### 1. Clone and Configure
```bash
git clone <repository>
cd CONSTRUCTION_EXPENSE_TR

# Copy environment template
cp .env.example .env

# Edit environment variables
nano .env
```

### 2. Required Environment Variables

```env
# Database
POSTGRES_USER=postgres
POSTGRES_PASSWORD=secure_password
POSTGRES_DB=construction_expense

# Redis
REDIS_URL=redis://redis:6379/0

# MinIO
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=secure_minio_password
MINIO_BUCKET=evidence

# JWT
JWT_SECRET_KEY=your-super-secret-key-change-in-production
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=30

# Celery
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0

# LLM Provider (choose one)
LLM_PROVIDER=openai
OPENAI_API_KEY=your-openai-key
# GEMINI_API_KEY=your-gemini-key
# ANTHROPIC_API_KEY=your-anthropic-key

# Optional
SENTRY_DSN=
WHATSAPP_VERIFY_TOKEN=
WHATSAPP_APP_SECRET=
```

### 3. Start Services
```bash
cd infrastructure
docker-compose up -d
```

### 4. Verify Deployment
```bash
# Check service health
curl http://localhost:8000/api/v1/health

# Check all services
docker-compose ps

# View logs
docker-compose logs -f backend
```

## Production Deployment

### 1. Use Production Docker Compose
```bash
# Create production override
cat > docker-compose.prod.yml <<EOF
version: "3.9"
services:
  backend:
    environment:
      - APP_ENV=production
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
      replicas: 2
  postgres:
    deploy:
      resources:
        limits:
          cpus: '1'
          memory: 1G
  redis:
    deploy:
      resources:
        limits:
          cpus: '0.5'
          memory: 512M
EOF

docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

### 2. SSL/TLS Configuration
```bash
# Generate certificates (Let's Encrypt recommended)
# Place in ./certs/

# Update nginx config for HTTPS
```

### 3. Database Backup
```bash
# Automated backup script
cat > backup.sh <<'EOF'
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
docker exec construction-postgres pg_dump -U postgres construction_expense | gzip > backups/construction_expense_$DATE.sql.gz
# Keep last 30 days
find backups -name "*.sql.gz" -mtime +30 -delete
EOF
chmod +x backup.sh

# Add to cron
# 0 2 * * * /path/to/backup.sh
```

### 4. Monitoring Setup

#### Prometheus + Grafana
```yaml
# Add to docker-compose.yml
  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
    networks:
      - app-network

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
    volumes:
      - grafana-data:/var/lib/grafana
    networks:
      - app-network

volumes:
  grafana-data:
```

#### Alert Rules
```yaml
# prometheus.yml alerts
groups:
- name: construction-expense
  rules:
  - alert: HighErrorRate
    expr: rate(http_requests_total{status=~"5.."}[5m]) > 0.05
    for: 2m
    labels:
      severity: critical
    annotations:
      summary: "High error rate detected"
      
  - alert: DatabaseDown
    expr: up{job="postgres"} == 0
    for: 1m
    labels:
      severity: critical
    annotations:
      summary: "PostgreSQL is down"
```

## Scaling

### Horizontal Scaling
```bash
# Scale backend workers
docker-compose up -d --scale backend=3 --scale worker=4

# Use load balancer (nginx/haproxy) in front
```

### Database Connection Pooling
```python
# In config.py
DATABASE_POOL_SIZE = 20
DATABASE_MAX_OVERFLOW = 10
DATABASE_POOL_TIMEOUT = 30
```

### Redis Cluster
```yaml
# For high availability
redis:
  image: redis:7-alpine
  command: redis-server --appendonly yes --cluster-enabled yes
```

## Security Hardening

### 1. Network Policies
```yaml
# Kubernetes NetworkPolicy example
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: backend-policy
spec:
  podSelector:
    matchLabels:
      app: backend
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - podSelector:
        matchLabels:
          app: nginx
    ports:
    - protocol: TCP
      port: 8000
```

### 2. Secrets Management
```bash
# Use Docker secrets or external vault
# docker secret create jwt_secret jwt_secret.txt
# docker secret create db_password db_password.txt
```

### 3. Security Headers
```python
# In main.py - already configured via middleware
# - X-Content-Type-Options: nosniff
# - X-Frame-Options: DENY
# - X-XSS-Protection: 1; mode=block
# - Strict-Transport-Security: max-age=31536000
```

## CI/CD Pipeline

### GitHub Actions Example
```yaml
# .github/workflows/deploy.yml
name: Deploy to Production

on:
  push:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run tests
        run: |
          cd backend
          pip install -e .[dev]
          pytest tests/ -v

  build:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Build images
        run: |
          docker build -t construction-backend ./backend
          docker build -t construction-frontend ./frontend

  deploy:
    needs: build
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    steps:
      - name: Deploy to server
        run: |
          ssh user@server "cd /app && docker-compose pull && docker-compose up -d"
```

## Troubleshooting

### Common Issues

#### Database Connection Failed
```bash
# Check PostgreSQL logs
docker-compose logs postgres

# Verify connection
docker exec construction-postgres pg_isready -U postgres
```

#### Redis Connection Failed
```bash
# Check Redis
docker exec construction-redis redis-cli ping
```

#### MinIO Bucket Not Found
```bash
# Create bucket
docker exec construction-minio mc mb local/evidence
```

#### Celery Workers Not Processing
```bash
# Check worker logs
docker-compose logs worker

# Check queue
docker exec construction-redis redis-cli LLEN celery
```

#### High Memory Usage
```bash
# Check container stats
docker stats

# Adjust limits in docker-compose.yml
```

### Logs Location
```bash
# Application logs
docker-compose logs -f backend

# Database logs
docker-compose logs -f postgres

# All services
docker-compose logs -f --tail=100
```

### Health Checks
```bash
# All services
curl http://localhost:8000/api/v1/health/detailed

# Individual services
curl http://localhost:8000/api/v1/health/ready
curl http://localhost:8000/api/v1/health/live
```

## Maintenance

### Database Migrations
```bash
# Run migrations
docker-compose exec backend alembic upgrade head

# Create new migration
docker-compose exec backend alembic revision --autogenerate -m "description"
```

### Clear Cache
```bash
# Redis
docker exec construction-redis redis-cli FLUSHDB

# Application cache (if implemented)
```

### Update Dependencies
```bash
# Backend
cd backend
pip install --upgrade -r requirements.txt

# Rebuild image
docker-compose build backend
docker-compose up -d backend
```

## Rollback Procedure

```bash
# 1. Tag current release
git tag -a rollback-$(date +%Y%m%d) -m "Rollback point"

# 2. Deploy previous version
git checkout previous-tag
docker-compose build
docker-compose up -d

# 3. Verify health
curl http://localhost:8000/api/v1/health/detailed

# 4. Run smoke tests
./scripts/smoke-tests.sh
```

## Support

For issues:
1. Check logs: `docker-compose logs -f`
2. Review monitoring dashboards
3. Check GitHub Issues
4. Contact: devops@company.com