# Operations Runbooks

## Table of Contents
1. [Daily Operations](#daily-operations)
2. [Incident Response](#incident-response)
3. [Backup & Recovery](#backup--recovery)
4. [Capacity Management](#capacity-management)
5. [Security Operations](#security-operations)

---

## Daily Operations

### Morning Health Check (9:00 AM)
```bash
#!/bin/bash
# daily-health-check.sh

echo "=== Daily Health Check ==="
date

# 1. API Health
echo "1. API Health:"
curl -s http://localhost:8000/api/v1/health/detailed | jq '.status'

# 2. Database
echo "2. Database:"
docker exec construction-postgres pg_isready -U postgres

# 3. Redis
echo "3. Redis:"
docker exec construction-redis redis-cli ping

# 4. MinIO
echo "4. MinIO:"
curl -s http://localhost:9002/minio/health/live

# 5. Celery Workers
echo "5. Celery Workers:"
curl -s http://localhost:8000/api/v1/metrics/celery | jq '.total_workers'

# 6. Disk Space
echo "6. Disk Space:"
df -h /var/lib/docker

# 7. Memory Usage
echo "7. Memory Usage:"
docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}"

# 8. Error Rate (last hour)
echo "8. Error Rate:"
curl -s http://localhost:8000/api/v1/metrics/business | jq '.'
```

### Evening Log Review (6:00 PM)
```bash
#!/bin/bash
# evening-log-review.sh

echo "=== Evening Log Review ==="
date

# Check for errors in last 12 hours
docker-compose logs --since=12h backend 2>&1 | grep -i error | head -20
docker-compose logs --since=12h backend 2>&1 | grep -i exception | head -20

# Check audit logs for anomalies
curl -s "http://localhost:8000/api/v1/audit/logs?date_from=$(date -d '12 hours ago' +%Y-%m-%d)" | jq '.total'
```

---

## Incident Response

### SEV-1: API Completely Down

**Symptoms**: All endpoints return 5xx or timeout

**Response Time**: 15 minutes

**Steps**:
1. **Acknowledge** - Page on-call engineer
2. **Diagnose** - Check container status
   ```bash
   docker-compose ps
   docker-compose logs --tail=100 backend
   ```
3. **Quick Fixes**:
   - Restart backend: `docker-compose restart backend`
   - Check database: `docker-compose restart postgres`
   - Check Redis: `docker-compose restart redis`
4. **Escalate** - If not resolved in 15 min, escalate to team lead
5. **Post-Incident** - Create incident report within 24 hours

### SEV-2: High Error Rate (>5%)

**Symptoms**: 5xx errors > 5% for 5 minutes

**Response Time**: 30 minutes

**Steps**:
1. **Check Metrics**: `curl http://localhost:8000/api/v1/metrics`
2. **Identify Endpoint**: Check which endpoints failing
3. **Check Logs**: `docker-compose logs -f backend | grep ERROR`
4. **Common Causes**:
   - Database connection pool exhausted
   - Redis memory full
   - External API timeout (LLM provider)
4. **Mitigation**:
   - Increase connection pool
   - Clear Redis cache: `docker exec construction-redis redis-cli FLUSHDB`
   - Switch LLM provider temporarily

### SEV-3: Slow Performance

**Symptoms**: API latency > 2s for 10 minutes

**Response Time**: 1 hour

**Steps**:
1. **Check System Metrics**: `curl http://localhost:8000/api/v1/metrics/system`
2. **Database**: Check slow queries
   ```sql
   SELECT * FROM pg_stat_statements ORDER BY mean_time DESC LIMIT 10;
   ```
3. **Celery Queue**: Check backlog
   ```bash
   docker exec construction-redis redis-cli LLEN celery
   ```
4. **Scale**: Add workers if queue backed up
   ```bash
   docker-compose up -d --scale worker=6
   ```

---

## Backup & Recovery

### Daily Backup (Automated - 2:00 AM)

```bash
#!/bin/bash
# backup-daily.sh

set -e

BACKUP_DIR="/backups/daily"
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p $BACKUP_DIR

# 1. PostgreSQL Backup
echo "Backing up PostgreSQL..."
docker exec construction-postgres pg_dump -U postgres construction_expense | gzip > $BACKUP_DIR/postgres_$DATE.sql.gz

# 2. MinIO Backup (if configured)
echo "Backing up MinIO..."
docker exec construction-minio mc mirror local/evidence $BACKUP_DIR/minio_$DATE/

# 3. Redis Backup
echo "Backing up Redis..."
docker exec construction-redis redis-cli --rdb /data/dump.rdb
docker cp construction-redis:/data/dump.rdb $BACKUP_DIR/redis_$DATE.rdb

# 4. Upload to S3 (optional)
# aws s3 cp $BACKUP_DIR/ s3://my-backup-bucket/daily/ --recursive

# 5. Cleanup old backups (keep 30 days)
find $BACKUP_DIR -name "*.gz" -mtime +30 -delete
find $BACKUP_DIR -name "*.rdb" -mtime +30 -delete

echo "Backup completed: $DATE"
```

### Point-in-Time Recovery

```bash
#!/bin/bash
# restore-point-in-time.sh

# Usage: ./restore-point-in-time.sh <backup_timestamp>

BACKUP_TIMESTAMP=$1
BACKUP_DIR="/backups/daily"

if [ -z "$BACKUP_TIMESTAMP" ]; then
  echo "Usage: $0 <timestamp>"
  echo "Available backups:"
  ls -la $BACKUP_DIR/
  exit 1
fi

echo "Restoring from $BACKUP_TIMESTAMP..."

# 1. Stop services
docker-compose stop backend worker

# 2. Restore PostgreSQL
gunzip -c $BACKUP_DIR/postgres_$BACKUP_TIMESTAMP.sql.gz | docker exec -i construction-postgres psql -U postgres -d construction_expense

# 3. Restore Redis
docker cp $BACKUP_DIR/redis_$BACKUP_TIMESTAMP.rdb construction-redis:/data/dump.rdb
docker-compose restart redis

# 4. Restore MinIO (if needed)
# docker exec construction-minio mc mirror $BACKUP_DIR/minio_$BACKUP_TIMESTAMP/ local/evidence/

# 5. Start services
docker-compose start backend worker

# 6. Verify
curl http://localhost:8000/api/v1/health/detailed

echo "Restore completed"
```

### Disaster Recovery (Full Environment)

```bash
#!/bin/bash
# disaster-recovery.sh

# 1. Provision new infrastructure
# - New VPC/Network
# - New PostgreSQL instance
# - New Redis instance
# - New MinIO instance

# 2. Restore from latest backup
./restore-point-in-time.sh $(ls -t /backups/daily/postgres_*.sql.gz | head -1 | sed 's/.*postgres_\(.*\)\.sql\.gz/\1/')

# 3. Update DNS/Load Balancer
# Point to new endpoints

# 4. Verify all services
./daily-health-check.sh

# 5. Notify stakeholders
# Send Slack/Email notification
```

---

## Capacity Management

### Weekly Capacity Review (Monday 10:00 AM)

```bash
#!/bin/bash
# weekly-capacity-review.sh

echo "=== Weekly Capacity Review ==="
date

# 1. Database Size
echo "1. Database Size:"
docker exec construction-postgres psql -U postgres -d construction_expense -c "
SELECT pg_size_pretty(pg_database_size('construction_expense')) as db_size;
SELECT schemaname, tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
LIMIT 10;
"

# 2. Redis Memory
echo "2. Redis Memory:"
docker exec construction-redis redis-cli INFO memory | grep used_memory_human

# 3. MinIO Storage
echo "3. MinIO Storage:"
docker exec construction-minio mc du local/evidence

# 4. Container Resources
echo "4. Container Resources (7-day avg):"
docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}"

# 5. Growth Trends
echo "5. Weekly Growth:"
# Compare with last week (requires metrics retention)
```

### Scaling Triggers

| Metric | Warning | Critical | Action |
|--------|---------|----------|--------|
| CPU Usage | > 70% | > 85% | Scale horizontally |
| Memory Usage | > 75% | > 90% | Increase limits / optimize |
| Disk Usage | > 70% | > 85% | Cleanup / expand volume |
| DB Connections | > 80% | > 95% | Increase pool / read replicas |
| Redis Memory | > 70% | > 85% | Increase eviction / scale |
| Celery Queue | > 1000 | > 5000 | Add workers |

### Monthly Capacity Planning

1. **Review Trends**: 30-day growth rates
2. **Project Needs**: 3-month forecast
3. **Budget Approval**: Submit scaling requests
4. **Schedule Changes**: Plan during maintenance window

---

## Security Operations

### Daily Security Checks

```bash
#!/bin/bash
# daily-security-check.sh

echo "=== Daily Security Check ==="
date

# 1. Failed Login Attempts
echo "1. Failed Logins (last 24h):"
docker-compose logs --since=24h backend | grep -i "unauthorized\|forbidden\|invalid token" | wc -l

# 2. Audit Log Anomalies
echo "2. Audit Anomalies:"
curl -s "http://localhost:8000/api/v1/audit/logs?date_from=$(date -d '24 hours ago' +%Y-%m-%d)" | jq '.items[] | select(.action=="DELETE" or .action=="ADMIN")'

# 3. Webhook Failures
echo "3. Webhook Failures:"
docker-compose logs --since=24h backend | grep -i webhook | grep -i fail | wc -l

# 4. Certificate Expiry
echo "4. SSL Certificates:"
# Check with openssl or cert-manager

# 5. Dependency Vulnerabilities
echo "5. Vulnerabilities:"
# Run: pip-audit or safety check
```

### Weekly Security Audit (Friday 2:00 PM)

```bash
#!/bin/bash
# weekly-security-audit.sh

# 1. User Access Review
echo "1. Active Users:"
curl -s http://localhost:8000/api/v1/admin/users | jq '.[] | {id, email, roles: [.roles[].name], last_login, is_active}'

# 2. Admin Actions
echo "2. Admin Actions (last 7 days):"
curl -s "http://localhost:8000/api/v1/audit/logs?action=ADMIN&date_from=$(date -d '7 days ago' +%Y-%m-%d)" | jq '.total'

# 3. API Key Usage
echo "3. Active API Keys:"
curl -s http://localhost:8000/api/v1/admin/api-keys | jq '.[] | {name, created_at, last_used}'

# 4. Permission Changes
echo "4. Role Changes:"
curl -s "http://localhost:8000/api/v1/audit/logs?action=ROLE_CHANGE&date_from=$(date -d '7 days ago' +%Y-%m-%d)"

# 5. Compliance Report
echo "5. Generating Compliance Report..."
curl -X POST http://localhost:8000/api/v1/audit/reports \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"report_type": "COMPLIANCE", "format": "PDF", "filters": {"date_from": "'$(date -d '30 days ago' +%Y-%m-%d)'", "date_to": "'$(date +%Y-%m-%d)'"}}'
```

### Monthly Penetration Testing

```bash
#!/bin/bash
# monthly-pentest.sh

# Run automated security scans
# 1. OWASP ZAP scan
docker run --rm -t owasp/zap2docker-stable zap-baseline.py -t http://localhost:8000

# 2. Dependency check
cd backend && pip-audit

# 3. Container scan
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock aquasec/trivy image construction-backend

# 4. Configuration audit
# Check for hardcoded secrets, debug modes, etc.
```

---

## Escalation Contacts

| Role | Name | Phone | Slack | Email |
|------|------|-------|-------|-------|
| Primary On-Call | | | | |
| Secondary On-Call | | | | |
| Team Lead | | | | |
| Engineering Manager | | | | |
| DBA | | | | |
| Security Team | | | | |

---

## Communication Channels

- **Incidents**: #incidents (Slack)
- **Deployments**: #deployments (Slack)
- **Alerts**: #alerts (Slack)
- **General**: #construction-expense (Slack)

---

## Runbook Maintenance

- Review quarterly
- Update after each incident
- Version control in Git
- Test procedures annually