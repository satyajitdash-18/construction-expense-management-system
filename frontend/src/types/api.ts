export interface User {
  id: string;
  email: string;
  full_name: string;
  role: 'admin' | 'project_manager' | 'site_user' | 'finance_user';
  is_active: boolean;
  created_at: string;
  phone?: string;
  avatar_url?: string;
}

export interface Project {
  id: string;
  name: string;
  code: string;
  status: 'active' | 'on_hold' | 'completed' | 'archived';
  created_by: string;
  created_at: string;
  updated_at: string | null;
  creator?: User;
  budgets?: ProjectBudget[];
  expenses?: Expense[];
}

export interface ProjectBudget {
  id: string;
  project_id: string;
  category_id: string;
  amount: number;
  currency: string;
  effective_from: string;
  effective_to: string | null;
}

export interface Vendor {
  id: string;
  name: string;
  gstin: string | null;
  phone: string | null;
  notes: string | null;
  email?: string | null;
  address?: string | null;
  city?: string | null;
  state?: string | null;
  pincode?: string | null;
  contact_person?: string | null;
  created_at: string;
  updated_at: string | null;
}

export interface ExpenseCategory {
  id: string;
  name: string;
  parent_category_id: string | null;
  created_at: string;
  updated_at: string | null;
}

export interface Expense {
  id: string;
  project_id: string;
  source_event_id: string | null;
  vendor_id: string | null;
  category_id: string | null;
  transaction_date: string;
  subtotal: number;
  tax_amount: number;
  total: number;
  currency: string;
  payment_method: 'CASH' | 'UPI' | 'BANK_TRANSFER' | 'CARD' | 'CHEQUE' | 'OTHER';
  gstin_supplier: string | null;
  hsn_sac_code: string | null;
  cgst_amount: number | null;
  sgst_amount: number | null;
  igst_amount: number | null;
  irn: string | null;
  confidence_score: number | null;
  extraction_payload: Record<string, unknown>;
  lifecycle_status: 'RECEIVED' | 'VALIDATED' | 'PROCESSING' | 'EXTRACTED' | 'NEEDS_CONFIRMATION' | 'STAGED' | 'RECONCILING' | 'RECONCILED' | 'POSTED' | 'FAILED' | 'REJECTED' | 'UNMATCHED' | 'AMBIGUOUS';
  receipt_id: string | null;
  source_audit_event_id: string | null;
  created_at: string;
  updated_at: string | null;
  vendor?: Vendor;
  vendor_name?: string | null;
  category?: ExpenseCategory;
  project?: Project;
  line_items?: ExpenseLineItem[];
  evidence_files?: Evidence[];
}

export interface ExpenseLineItem {
  id: string;
  expense_id: string;
  description: string;
  quantity: number | null;
  unit_price: number | null;
  amount: number;
  tax_amount: number | null;
}

export interface ExpenseCreate {
  project_id: string;
  transaction_date: string;
  subtotal: number;
  tax_amount: number;
  total: number;
  currency?: string;
  payment_method: 'CASH' | 'UPI' | 'BANK_TRANSFER' | 'CARD' | 'CHEQUE' | 'OTHER';
  vendor_id?: string;
  category_id?: string;
  line_items?: Omit<ExpenseLineItem, 'id' | 'expense_id'>[];
  vendor_name?: string;
  gstin_supplier?: string;
  hsn_sac_code?: string;
  cgst_amount?: number;
  sgst_amount?: number;
  igst_amount?: number;
  irn?: string;
}

export interface ExpenseUpdate {
  transaction_date?: string;
  subtotal?: number;
  tax_amount?: number;
  total?: number;
  currency?: string;
  payment_method?: 'CASH' | 'UPI' | 'BANK_TRANSFER' | 'CARD' | 'CHEQUE' | 'OTHER';
  vendor_id?: string;
  category_id?: string;
  vendor_name?: string;
  gstin_supplier?: string;
  hsn_sac_code?: string;
  cgst_amount?: number;
  sgst_amount?: number;
  igst_amount?: number;
  irn?: string;
  lifecycle_status?: string;
}

export interface ExpenseListResponse {
  items: Expense[];
  total: number;
  limit: number;
  offset: number;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface Evidence {
  id: string;
  expense_id: string;
  object_name: string;
  file_name: string;
  content_type: string;
  size: number;
  checksum: string;
  created_at: string;
}

export interface EvidenceUploadResponse {
  object_name: string;
  checksum: string;
  size: number;
  content_type: string;
  presigned_url: string;
  expires_at: string;
}

export interface SourceEvent {
  id: string;
  source: 'WHATSAPP' | 'SMS_UPI' | 'MANUAL';
  external_id: string | null;
  idempotency_key: string;
  raw_payload: Record<string, unknown>;
  received_at: string;
}

export interface PaymentEvent {
  id: string;
  source_event_id: string;
  amount: number;
  occurred_at: string;
  payee_raw_text: string;
  upi_reference: string | null;
  bank_reference: string | null;
  payment_method: 'CASH' | 'UPI' | 'BANK_TRANSFER' | 'CARD' | 'CHEQUE' | 'OTHER';
  device_id: string | null;
  raw_text: string;
  idempotency_key: string;
}

export interface ReconciliationRecord {
  id: string;
  expense_id: string;
  payment_event_id: string | null;
  status: 'MATCHED' | 'UNMATCHED' | 'AMBIGUOUS' | 'MANUALLY_RESOLVED';
  match_basis: 'REFERENCE' | 'SCORED' | 'MANUAL' | null;
  match_score: number | null;
  resolved_by: string | null;
  resolution_reason: string | null;
  created_at: string;
  updated_at: string | null;
  expense?: Expense;
  payment_event?: PaymentEvent;
}

export interface AuditEvent {
  id: string;
  event_type: string;
  entity_type: string;
  entity_id: string;
  actor_id: string | null;
  correlation_id: string;
  causation_id: string | null;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface ProcessingJob {
  id: string;
  job_type: 'MEDIA_DOWNLOAD' | 'OCR' | 'LLM_EXTRACT' | 'RECONCILE' | 'NOTIFY_WHATSAPP';
  source_event_id: string | null;
  status: 'PENDING' | 'RUNNING' | 'SUCCEEDED' | 'FAILED' | 'RETRYING';
  created_at: string;
  updated_at: string | null;
}

export interface OCRJobItem {
  id: string;
  job_type?: string;
  source_event_id: string | null;
  status: 'PENDING' | 'RUNNING' | 'SUCCEEDED' | 'FAILED' | 'RETRYING';
  result?: { text?: string; full_text?: string; avg_confidence?: number; word_count?: number } | null;
  error_message?: string | null;
  created_at: string;
  completed_at?: string | null;
  evidence?: { file_name?: string };
  confidence_score?: number | null;
}

export interface ExtractionJobItem {
  id: string;
  job_type?: string;
  source_event_id: string | null;
  status: 'PENDING' | 'RUNNING' | 'SUCCEEDED' | 'FAILED' | 'RETRYING';
  result?: Record<string, unknown> | null;
  error_message?: string | null;
  created_at: string;
  completed_at?: string | null;
  evidence?: { file_name?: string };
  model?: string;
  confidence_score?: number | null;
}

export interface NotificationItem {
  id: string;
  user_id?: string | null;
  channel: string;
  subject?: string | null;
  body: string;
  status: string;
  priority?: string;
  title?: string;
  read?: boolean;
  is_read?: boolean;
  error_message?: string | null;
  sent_at?: string | null;
  created_at: string;
  metadata?: Record<string, unknown> | null;
}

export interface NotificationStats {
  total_sent: number;
  total_failed: number;
  by_channel: Record<string, number>;
  by_status: Record<string, number>;
  by_priority: Record<string, number>;
  success_rate: number;
  total?: number;
  sent?: number;
  pending?: number;
  failed?: number;
  unread?: number;
  read?: number;
}

export interface WebhookConfig {
  id: string;
  url: string;
  events: string[];
  secret: string | null;
  headers: Record<string, string> | null;
  retry_policy: Record<string, unknown> | null;
  is_active: boolean;
  last_triggered_at: string | null;
  success_count: number;
  failure_count: number;
  created_at: string;
  updated_at: string | null;
}

export interface WebhookDelivery {
  id: string;
  webhook_config_id: string;
  event_type: string;
  payload: Record<string, unknown>;
  response_status: number | null;
  response_body: string | null;
  attempt_number: number;
  success: boolean;
  error_message: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface AuthTokens {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface RegisterRequest {
  email: string;
  password: string;
  full_name: string;
}

export interface UserResponse {
  user: User;
  tokens: AuthTokens;
}

export interface ApiError {
  detail: string;
}

export interface DashboardStats {
  total_projects: number;
  active_projects: number;
  total_expenses: number;
  pending_expenses: number;
  reconciled_expenses: number;
  posted_expenses: number;
  total_budget: number;
  spent_budget: number;
  pending_reconciliation: number;
}

export interface WebhookConfigCreate {
  url: string;
  events: string[];
  secret?: string;
  headers?: Record<string, string>;
  retry_policy?: Record<string, unknown>;
  is_active?: boolean;
}

export type GDPRRequestType = 'EXPORT' | 'DELETE' | 'CORRECT';
export type GDPRRequestStatus = 'PENDING' | 'PROCESSING' | 'COMPLETED' | 'REJECTED';

export interface GDPRRequestCreate {
  user_id?: string;
  email: string;
  request_type: GDPRRequestType;
  details?: Record<string, unknown>;
}

export interface GDPRRequestResponse {
  id: string;
  user_id: string | null;
  email: string;
  request_type: GDPRRequestType;
  status: GDPRRequestStatus;
  rejection_reason?: string | null;
  created_at: string;
  updated_at?: string | null;
}

export interface GDPRRequestListResponse {
  items: GDPRRequestResponse[];
  total: number;
  page: number;
  page_size: number;
}

export interface DataRetentionPolicyCreate {
  name: string;
  description?: string;
  retention_days: number;
  archive_after_days?: number;
  delete_after_days?: number;
  is_active?: boolean;
}

export interface DataRetentionPolicyResponse {
  id: string;
  name: string;
  description: string | null;
  retention_days: number;
  archive_after_days: number | null;
  delete_after_days: number | null;
  is_active: boolean;
  created_at: string;
  updated_at: string | null;
}

export interface DataRetentionPolicyListResponse {
  items: DataRetentionPolicyResponse[];
  total: number;
  page: number;
  page_size: number;
}

export interface AuditReportRequest {
  report_type: string;
  date_from: string;
  date_to: string;
  format?: 'pdf' | 'csv' | 'json';
  parameters?: Record<string, unknown>;
}

export interface AuditReportResponse {
  id: string;
  report_type: string;
  date_from: string;
  date_to: string;
  status: 'pending' | 'completed' | 'failed';
  download_url?: string;
  created_at: string;
  completed_at?: string | null;
}

export interface ComplianceDashboardResponse {
  audit_events_today: number;
  audit_events_this_month: number;
  pending_gdpr_requests: number;
  completed_gdpr_requests_this_month: number;
  active_retention_policies: number;
}