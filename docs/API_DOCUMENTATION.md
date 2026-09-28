# Construction Expense Management System - API Documentation

## Overview

The Construction Expense Management System provides a RESTful API for managing construction project expenses, budgets, vendors, and reconciliation workflows.

**Base URL**: `http://localhost:8000/api/v1`

**Authentication**: JWT Bearer Token

## Authentication

### Login
```
POST /api/v1/auth/login
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "password123"
}
```

### Refresh Token
```
POST /api/v1/auth/refresh
Authorization: Bearer <refresh_token>
```

## Projects

### Create Project
```
POST /api/v1/projects
Authorization: Bearer <token>
Content-Type: application/json

{
  "name": "Project Name",
  "code": "PROJ-001",
  "description": "Project description",
  "location": "Location",
  "status": "active"
}
```

### List Projects
```
GET /api/v1/projects
Authorization: Bearer <token>
Query Parameters:
- page: Page number (default: 1)
- size: Page size (default: 20)
- status: Filter by status
```

### Get Project
```
GET /api/v1/projects/{project_id}
Authorization: Bearer <token>
```

### Update Project
```
PUT /api/v1/projects/{project_id}
Authorization: Bearer <token>
Content-Type: application/json

{
  "name": "Updated Name",
  "description": "Updated description"
}
```

### Delete Project
```
DELETE /api/v1/projects/{project_id}
Authorization: Bearer <token>
```

### Budget vs Actual
```
GET /api/v1/projects/{project_id}/budget-vs-actual
Authorization: Bearer <token>
```

## Budgets

### Create Budget
```
POST /api/v1/budgets
Authorization: Bearer <token>
Content-Type: application/json

{
  "project_id": "uuid",
  "category": "MATERIALS",
  "amount": 100000,
  "currency": "USD"
}
```

### List Budgets
```
GET /api/v1/budgets?project_id={project_id}
Authorization: Bearer <token>
```

## Expenses

### Create Expense
```
POST /api/v1/expenses
Authorization: Bearer <token>
Content-Type: application/json

{
  "project_id": "uuid",
  "vendor_name": "Vendor Name",
  "vendor_gstin": "29ABCDE1234F1Z5",
  "date": "2024-01-15",
  "total": 5000,
  "currency": "USD",
  "category": "MATERIALS",
  "payment_method": "CASH",
  "reference_number": "INV-001"
}
```

### List Expenses
```
GET /api/v1/expenses
Authorization: Bearer <token>
Query Parameters:
- project_id: Filter by project
- status: Filter by lifecycle status
- page: Page number (default: 1)
- size: Page size (default: 20)
- date_from: Filter by date range start
- date_to: Filter by date range end
```

### Get Expense
```
GET /api/v1/expenses/{expense_id}
Authorization: Bearer <token>
```

### Transition Expense Status
```
POST /api/v1/expenses/{expense_id}/transition
Authorization: Bearer <token>
Content-Type: application/json

{
  "target_status": "VALIDATED"
}
```

Valid transitions:
- RECEIVED → VALIDATED
- VALIDATED → STAGED
- STAGED → EXTRACTED
- EXTRACTED → RECONCILED
- RECONCILED → POSTED

## Payment Events

### Create Payment Event
```
POST /api/v1/payment-events
Authorization: Bearer <token>
Content-Type: application/json

{
  "project_id": "uuid",
  "amount": 10000,
  "currency": "USD",
  "date": "2024-01-16",
  "payment_method": "BANK_TRANSFER",
  "reference_number": "PAY-001"
}
```

### List Payment Events
```
GET /api/v1/payment-events?project_id={project_id}
Authorization: Bearer <token>
```

## Reconciliation

### Manual Reconciliation
```
POST /api/v1/reconciliation
Authorization: Bearer <token>
Content-Type: application/json

{
  "expense_id": "uuid",
  "payment_event_id": "uuid",
  "match_basis": "MANUAL",
  "notes": "Manual reconciliation"
}
```

### Auto Match Batch
```
POST /api/v1/reconciliation/auto-match
Authorization: Bearer <token>
Content-Type: application/json

{
  "project_id": "uuid",
  "dry_run": false,
  "expense_ids": ["uuid1", "uuid2"]
}
```

### List Reconciliations
```
GET /api/v1/reconciliation?project_id={project_id}
Authorization: Bearer <token>
```

### Get Reconciliation Stats
```
GET /api/v1/reconciliation/stats?project_id={project_id}
Authorization: Bearer <token>
```

## Vendors

### Create Vendor
```
POST /api/v1/vendors
Authorization: Bearer <token>
Content-Type: application/json

{
  "name": "Vendor Name",
  "gstin": "29ABCDE1234F1Z5",
  "email": "vendor@example.com",
  "phone": "+1234567890",
  "address": "123 Vendor St",
  "city": "City",
  "state": "State",
  "postal_code": "12345",
  "country": "USA"
}
```

### List Vendors
```
GET /api/v1/vendors
Authorization: Bearer <token>
```

## Categories

### List Categories
```
GET /api/v1/categories
Authorization: Bearer <token>
```

## Audit & Compliance

### Get Audit Logs
```
GET /api/v1/audit/logs
Authorization: Bearer <token>
Query Parameters:
- entity_type: Filter by entity type
- entity_id: Filter by entity ID
- action: Filter by action
- date_from: Filter by date range start
- date_to: Filter by date range end
- page: Page number
- size: Page size
```

### Generate Audit Report
```
POST /api/v1/audit/reports
Authorization: Bearer <token>
Content-Type: application/json

{
  "report_type": "EXPENSE_SUMMARY",
  "format": "JSON",
  "filters": {
    "date_from": "2024-01-01",
    "date_to": "2024-12-31"
  }
}
```

### Get Audit Reports
```
GET /api/v1/audit/reports
Authorization: Bearer <token>
```

### Download Report
```
GET /api/v1/audit/reports/{report_id}/download
Authorization: Bearer <token>
```

## Notifications

### Get Preferences
```
GET /api/v1/notifications/preferences
Authorization: Bearer <token>
```

### Update Preferences
```
PATCH /api/v1/notifications/preferences
Authorization: Bearer <token>
Content-Type: application/json

{
  "email_enabled": true,
  "sms_enabled": false,
  "push_enabled": true,
  "webhook_enabled": false,
  "event_types": ["EXPENSE_CREATED", "RECONCILIATION_MATCHED"]
}
```

### List Notifications
```
GET /api/v1/notifications
Authorization: Bearer <token>
Query Parameters:
- page: Page number
- size: Page size
- unread_only: Show only unread
```

## Webhooks

### Register Webhook
```
POST /api/v1/webhooks
Authorization: Bearer <token>
Content-Type: application/json

{
  "url": "https://example.com/webhook",
  "events": ["EXPENSE_CREATED", "RECONCILIATION_MATCHED"],
  "secret": "webhook-secret"
}
```

### List Webhooks
```
GET /api/v1/webhooks
Authorization: Bearer <token>
```

## Monitoring

### Health Check
```
GET /api/v1/health
```

### Detailed Health Check
```
GET /api/v1/health/detailed
```

### Readiness Probe
```
GET /api/v1/health/ready
```

### Liveness Probe
```
GET /api/v1/health/live
```

### Prometheus Metrics
```
GET /api/v1/metrics
```

### System Metrics
```
GET /api/v1/metrics/system
```

### Celery Metrics
```
GET /api/v1/metrics/celery
```

### Business Metrics
```
GET /api/v1/metrics/business
```

## Error Responses

All error responses follow this format:
```json
{
  "detail": "Error message",
  "error_code": "ERROR_CODE"
}
```

Common HTTP status codes:
- 200: Success
- 201: Created
- 400: Bad Request
- 401: Unauthorized
- 403: Forbidden
- 404: Not Found
- 422: Validation Error
- 500: Internal Server Error

## Rate Limiting

API endpoints are rate limited. Default limits:
- 100 requests per minute per IP
- 1000 requests per hour per user

Exceeding limits returns 429 Too Many Requests.

## Pagination

List endpoints support pagination:
- `page`: Page number (1-based, default: 1)
- `size`: Page size (default: 20, max: 100)

Response format:
```json
{
  "items": [...],
  "total": 100,
  "page": 1,
  "size": 20,
  "pages": 5
}
```