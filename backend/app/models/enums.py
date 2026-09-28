from enum import Enum


class LifecycleStatus(str, Enum):
    RECEIVED = "RECEIVED"
    VALIDATED = "VALIDATED"
    PROCESSING = "PROCESSING"
    EXTRACTED = "EXTRACTED"
    NEEDS_CONFIRMATION = "NEEDS_CONFIRMATION"
    STAGED = "STAGED"
    RECONCILING = "RECONCILING"
    RECONCILED = "RECONCILED"
    POSTED = "POSTED"
    FAILED = "FAILED"
    REJECTED = "REJECTED"
    UNMATCHED = "UNMATCHED"
    AMBIGUOUS = "AMBIGUOUS"


class PaymentMethod(str, Enum):
    CASH = "CASH"
    UPI = "UPI"
    BANK_TRANSFER = "BANK_TRANSFER"
    CARD = "CARD"
    CHEQUE = "CHEQUE"
    OTHER = "OTHER"


class SourceType(str, Enum):
    WHATSAPP = "whatsapp"
    SMS_UPI = "sms_upi"
    MANUAL = "manual"


class ReconciliationStatus(str, Enum):
    MATCHED = "MATCHED"
    UNMATCHED = "UNMATCHED"
    AMBIGUOUS = "AMBIGUOUS"
    MANUALLY_RESOLVED = "MANUALLY_RESOLVED"


class MatchBasis(str, Enum):
    REFERENCE = "reference"
    SCORED = "scored"
    MANUAL = "manual"


class AccountType(str, Enum):
    ASSET = "asset"
    EXPENSE = "expense"
    LIABILITY = "liability"


class EntryType(str, Enum):
    DEBIT = "debit"
    CREDIT = "credit"


class ProjectStatus(str, Enum):
    ACTIVE = "active"
    ON_HOLD = "on_hold"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class JobType(str, Enum):
    MEDIA_DOWNLOAD = "media_download"
    OCR = "ocr"
    LLM_EXTRACT = "llm_extract"
    RECONCILE = "reconcile"
    NOTIFY_WHATSAPP = "notify_whatsapp"


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    RETRYING = "retrying"


class NotificationChannel(str, Enum):
    EMAIL = "email"
    SMS = "sms"
    WHATSAPP = "whatsapp"
    PUSH = "push"
    WEBHOOK = "webhook"


class NotificationStatus(str, Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    SCHEDULED = "scheduled"


class WebhookEvent(str, Enum):
    EXPENSE_CREATED = "expense.created"
    EXPENSE_UPDATED = "expense.updated"
    EXPENSE_POSTED = "expense.posted"
    EXPENSE_RECONCILED = "expense.reconciled"
    PAYMENT_RECEIVED = "payment.received"
    NOTIFICATION_SENT = "notification.sent"
    WEBHOOK_DELIVERED = "webhook.delivered"


class GDPRRequestType(str, Enum):
    ACCESS = "access"
    RECTIFICATION = "rectification"
    ERASURE = "erasure"
    PORTABILITY = "portability"
    RESTRICTION = "restriction"
    OBJECTION = "objection"


class GDPRRequestStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    REJECTED = "rejected"
