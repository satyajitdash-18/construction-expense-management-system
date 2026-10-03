import axios, { AxiosError, AxiosInstance, InternalAxiosRequestConfig } from 'axios';
import type { 
  User, 
  Project, 
  ProjectBudget, 
  Vendor, 
  ExpenseCategory, 
  Expense, 
  ExpenseListResponse, 
  Evidence, 
  EvidenceUploadResponse,
  DashboardStats,
  LoginRequest,
  RegisterRequest,
  UserResponse,
  PaginatedResponse,
  AuditReportRequest,
  AuditReportResponse,
  ComplianceDashboardResponse,
  DataRetentionPolicyCreate,
  DataRetentionPolicyResponse,
  GDPRRequestCreate,
  GDPRRequestListResponse,
  GDPRRequestResponse,
  OCRJobItem,
  ExtractionJobItem,
  NotificationItem,
  NotificationStats,
  WebhookConfig,
  ReconciliationRecord,
} from '@/types/api';

const API_BASE_URL = (import.meta as ImportMeta & { env: Record<string, string> }).env?.VITE_API_BASE_URL || '/api/v1';

class ApiService {
  private client: AxiosInstance;

  constructor() {
    this.client = axios.create({
      baseURL: API_BASE_URL,
      headers: {
        'Content-Type': 'application/json',
      },
      timeout: 30000,
    });

    this.client.interceptors.request.use(
      (config: InternalAxiosRequestConfig) => {
        const token = localStorage.getItem('access_token');
        if (token && config.headers) {
          config.headers.Authorization = `Bearer ${token}`;
        }
        return config;
      },
      (error) => Promise.reject(error)
    );

    this.client.interceptors.response.use(
      (response) => response,
      async (error: AxiosError) => {
        // Normalize error detail into error.message
        const data = error.response?.data as { detail?: string | Array<{ msg: string }>; message?: string } | undefined;
        const errorDetail = data?.detail || data?.message;
        if (errorDetail) {
          error.message = typeof errorDetail === 'string'
            ? errorDetail
            : Array.isArray(errorDetail)
              ? errorDetail.map((d) => d.msg || JSON.stringify(d)).join(', ')
              : JSON.stringify(errorDetail);
        }

        const originalRequest = error.config as (InternalAxiosRequestConfig & { _retry?: boolean }) | undefined;
        const isAuthRoute = originalRequest?.url?.includes('/auth/login') || originalRequest?.url?.includes('/auth/refresh');

        if (error.response?.status === 401 && originalRequest && !originalRequest._retry && !isAuthRoute) {
          originalRequest._retry = true;
          
          try {
            const refreshToken = localStorage.getItem('refresh_token');
            if (refreshToken) {
              const response = await axios.post(`${API_BASE_URL}/auth/refresh`, {
                refresh_token: refreshToken,
              });
              
              const { access_token, refresh_token } = response.data;
              localStorage.setItem('access_token', access_token);
              localStorage.setItem('refresh_token', refresh_token);
              
              if (originalRequest.headers) {
                originalRequest.headers.Authorization = `Bearer ${access_token}`;
              }
              
              return this.client(originalRequest);
            }
          } catch {
            this.clearAuth();
            if (typeof window !== 'undefined' && window.location.pathname !== '/login') {
              window.location.href = '/login';
            }
          }
        }
        
        return Promise.reject(error);
      }
    );
  }

  clearAuth(): void {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('user');
  }

  getAuth(): User | null {
    const userStr = localStorage.getItem('user');
    if (userStr) {
      try {
        return JSON.parse(userStr) as User;
      } catch {
        return null;
      }
    }
    return null;
  }

  setAuth(user: User, tokens: { access_token: string; refresh_token: string; token_type?: string; expires_in?: number }): void {
    localStorage.setItem('user', JSON.stringify(user));
    localStorage.setItem('access_token', tokens.access_token);
    localStorage.setItem('refresh_token', tokens.refresh_token);
  }

  // Auth
  async login(credentials: LoginRequest): Promise<UserResponse> {
    const response = await this.client.post<UserResponse & { access_token?: string; refresh_token?: string; token_type?: string; expires_in?: number }>('/auth/login', credentials);
    let user: User;
    let tokens: { access_token: string; refresh_token: string; token_type: string; expires_in: number };

    if (response.data.tokens && response.data.user) {
      tokens = response.data.tokens;
      user = response.data.user;
    } else {
      tokens = {
        access_token: response.data.access_token ?? '',
        refresh_token: response.data.refresh_token ?? '',
        token_type: response.data.token_type || 'bearer',
        expires_in: response.data.expires_in || 3600,
      };
      localStorage.setItem('access_token', tokens.access_token);
      localStorage.setItem('refresh_token', tokens.refresh_token);

      const meResponse = await this.client.get<User & { roles?: Array<string | { name: string }> }>('/auth/me', {
        headers: { Authorization: `Bearer ${tokens.access_token}` },
      });
      const me = meResponse.data;
      const rawRole = Array.isArray(me.roles) && me.roles.length > 0
        ? (typeof me.roles[0] === 'string' ? me.roles[0] : me.roles[0].name)
        : (me.role || 'site_user');
      const validRoles = ['admin', 'project_manager', 'site_user', 'finance_user'] as const;
      const role: (typeof validRoles)[number] = validRoles.includes(rawRole as (typeof validRoles)[number])
        ? (rawRole as (typeof validRoles)[number])
        : 'site_user';
      user = {
        id: me.id,
        email: me.email,
        full_name: me.full_name || '',
        role,
        is_active: me.is_active ?? true,
        created_at: me.created_at || new Date().toISOString(),
      };
    }

    this.setAuth(user, tokens);
    return { user, tokens };
  }

  async register(data: RegisterRequest): Promise<UserResponse> {
    const response = await this.client.post<UserResponse>('/auth/register', data);
    this.setAuth(response.data.user, { 
      access_token: response.data.tokens.access_token, 
      refresh_token: response.data.tokens.refresh_token 
    });
    return response.data;
  }

  async logout(): Promise<void> {
    try {
      const refreshToken = localStorage.getItem('refresh_token');
      await this.client.post('/auth/logout', { refresh_token: refreshToken || null });
    } catch {
      // Ignore network errors on logout, proceed with local cleanup
    } finally {
      this.clearAuth();
    }
  }

  async refreshToken(): Promise<{ access_token: string; refresh_token: string }> {
    const refreshToken = localStorage.getItem('refresh_token');
    const response = await this.client.post('/auth/refresh', { refresh_token: refreshToken });
    localStorage.setItem('access_token', response.data.access_token);
    localStorage.setItem('refresh_token', response.data.refresh_token);
    return response.data;
  }

  async getCurrentUser(): Promise<User> {
    const response = await this.client.get<User>('/auth/me');
    const token = localStorage.getItem('access_token');
    const refreshToken = localStorage.getItem('refresh_token');
    if (token && refreshToken) {
      this.setAuth(response.data, { 
        access_token: token, 
        refresh_token: refreshToken 
      });
    }
    return response.data;
  }

  async updateProfile(data: { full_name?: string; email?: string; phone?: string; avatar_url?: string }): Promise<User> {
    const response = await this.client.patch<User>('/auth/me', data);
    const token = localStorage.getItem('access_token');
    const refreshToken = localStorage.getItem('refresh_token');
    if (token && refreshToken) {
      this.setAuth(response.data, { access_token: token, refresh_token: refreshToken });
    }
    return response.data;
  }

  async changePassword(currentPassword: string, newPassword: string): Promise<void> {
    await this.client.post('/auth/change-password', { current_password: currentPassword, new_password: newPassword });
  }

  async updateNotificationPreferences(data: Record<string, boolean>): Promise<Record<string, boolean>> {
    const response = await this.client.patch('/auth/notification-preferences', data);
    return response.data;
  }

  async deleteAccount(): Promise<void> {
    await this.client.delete('/auth/me');
    this.clearAuth();
  }

  // Projects
  async getProjects(params?: { page?: number; page_size?: number; status?: string }): Promise<PaginatedResponse<Project>> {
    const response = await this.client.get<PaginatedResponse<Project>>('/projects', { params });
    return response.data;
  }

  async getProject(id: string): Promise<Project> {
    const response = await this.client.get<Project>(`/projects/${id}`);
    return response.data;
  }

  async createProject(data: { name: string; code: string }): Promise<Project> {
    const response = await this.client.post<Project>('/projects', data);
    return response.data;
  }

  async updateProject(id: string, data: { name?: string; code?: string; status?: string }): Promise<Project> {
    const response = await this.client.patch<Project>(`/projects/${id}`, data);
    return response.data;
  }

  async deleteProject(id: string): Promise<void> {
    await this.client.delete(`/projects/${id}`);
  }

  async getProjectBudgets(projectId: string): Promise<ProjectBudget[]> {
    const response = await this.client.get<ProjectBudget[]>(`/projects/${projectId}/budgets`);
    return response.data;
  }

  async createProjectBudget(projectId: string, data: Omit<ProjectBudget, 'id' | 'project_id' | 'created_at' | 'updated_at'>): Promise<ProjectBudget> {
    const response = await this.client.post<ProjectBudget>(`/projects/${projectId}/budgets`, data);
    return response.data;
  }

  async updateProjectBudget(projectId: string, budgetId: string, data: Partial<ProjectBudget>): Promise<ProjectBudget> {
    const response = await this.client.patch<ProjectBudget>(`/projects/${projectId}/budgets/${budgetId}`, data);
    return response.data;
  }

  async deleteProjectBudget(projectId: string, budgetId: string): Promise<void> {
    await this.client.delete(`/projects/${projectId}/budgets/${budgetId}`);
  }

  // Expenses
  async getExpenses(params?: { 
    project_id?: string; 
    vendor_id?: string; 
    category_id?: string; 
    status?: string; 
    date_from?: string; 
    date_to?: string; 
    limit?: number; 
    offset?: number;
    page?: number;
    page_size?: number;
    search?: string;
  }): Promise<ExpenseListResponse> {
    const response = await this.client.get<ExpenseListResponse>('/expenses', { params });
    return response.data;
  }

  async getExpense(id: string): Promise<Expense> {
    const response = await this.client.get<Expense>(`/expenses/${id}`);
    return response.data;
  }

  async createExpense(data: Record<string, unknown>): Promise<Expense> {
    const response = await this.client.post<Expense>('/expenses', data);
    return response.data;
  }

  async updateExpense(id: string, data: Record<string, unknown>): Promise<Expense> {
    const response = await this.client.patch<Expense>(`/expenses/${id}`, data);
    return response.data;
  }

  async deleteExpense(id: string): Promise<void> {
    await this.client.delete(`/expenses/${id}`);
  }

  async transitionExpense(id: string, newStatus: string, actorId?: string): Promise<Expense> {
    const response = await this.client.post<Expense>(`/expenses/${id}/transition`, { new_status: newStatus, actor_id: actorId });
    return response.data;
  }

  // Evidence
  async uploadEvidence(expenseId: string, file: File): Promise<EvidenceUploadResponse> {
    const formData = new FormData();
    formData.append('file', file);
    const response = await this.client.post<EvidenceUploadResponse>(`/evidence/upload`, formData, {
      params: { expense_id: expenseId },
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  }

  async getEvidence(evidenceId: string): Promise<Evidence> {
    const response = await this.client.get<Evidence>(`/evidence/${evidenceId}`);
    return response.data;
  }

  async listEvidence(expenseId: string, page?: number, pageSize?: number): Promise<PaginatedResponse<Evidence>> {
    const response = await this.client.get<PaginatedResponse<Evidence>>(`/evidence/expense/${expenseId}`, { params: { page, page_size: pageSize } });
    return response.data;
  }

  async deleteEvidence(evidenceId: string): Promise<void> {
    await this.client.delete(`/evidence/${evidenceId}`);
  }

  async getEvidenceList(params?: { page?: number; page_size?: number }): Promise<PaginatedResponse<Evidence>> {
    const response = await this.client.get<PaginatedResponse<Evidence>>('/evidence', { params });
    return response.data;
  }

  // Vendors
  async getVendors(params?: { page?: number; page_size?: number; search?: string }): Promise<PaginatedResponse<Vendor>> {
    const response = await this.client.get<PaginatedResponse<Vendor>>('/vendors', { params });
    return response.data;
  }

  async getVendor(id: string): Promise<Vendor> {
    const response = await this.client.get<Vendor>(`/vendors/${id}`);
    return response.data;
  }

  async createVendor(data: { name: string; gstin?: string; phone?: string; notes?: string }): Promise<Vendor> {
    const response = await this.client.post<Vendor>('/vendors', data);
    return response.data;
  }

  async updateVendor(id: string, data: Partial<Vendor>): Promise<Vendor> {
    const response = await this.client.patch<Vendor>(`/vendors/${id}`, data);
    return response.data;
  }

  async deleteVendor(id: string): Promise<void> {
    await this.client.delete(`/vendors/${id}`);
  }

  // Categories
  async getCategories(): Promise<ExpenseCategory[]> {
    const response = await this.client.get('/categories');
    return response.data;
  }

  async createCategory(data: { name: string; parent_category_id?: string }): Promise<ExpenseCategory> {
    const response = await this.client.post('/categories', data);
    return response.data;
  }

  async updateCategory(id: string, data: { name?: string; parent_category_id?: string }): Promise<ExpenseCategory> {
    const response = await this.client.patch(`/categories/${id}`, data);
    return response.data;
  }

  async deleteCategory(id: string): Promise<void> {
    await this.client.delete(`/categories/${id}`);
  }

  // Reconciliation
  async getReconciliations(params?: { 
    page?: number; 
    page_size?: number; 
    status?: string; 
    project_id?: string 
  }): Promise<PaginatedResponse<ReconciliationRecord>> {
    const response = await this.client.get<PaginatedResponse<ReconciliationRecord>>('/reconciliation/records', { params });
    return response.data;
  }

  async getReconciliation(id: string): Promise<ReconciliationRecord> {
    const response = await this.client.get<ReconciliationRecord>(`/reconciliation/records/${id}`);
    return response.data;
  }

  async reconcileExpense(expenseId: string, paymentEventId?: string, autoMatch: boolean = true): Promise<Record<string, unknown>> {
    const response = await this.client.post<Record<string, unknown>>('/reconciliation/match', { expense_id: expenseId, payment_event_id: paymentEventId, auto_match: autoMatch });
    return response.data;
  }

  async confirmReconciliation(recordId: string, notes?: string): Promise<Record<string, unknown>> {
    const response = await this.client.post<Record<string, unknown>>(`/reconciliation/records/${recordId}/action`, { action: 'confirm', notes });
    return response.data;
  }

  async rejectReconciliation(recordId: string, notes: string): Promise<Record<string, unknown>> {
    const response = await this.client.post<Record<string, unknown>>(`/reconciliation/records/${recordId}/action`, { action: 'reject', notes });
    return response.data;
  }

  async unmatchReconciliation(recordId: string, notes: string): Promise<Record<string, unknown>> {
    const response = await this.client.post<Record<string, unknown>>(`/reconciliation/records/${recordId}/action`, { action: 'unmatch', notes });
    return response.data;
  }

  async getReconciliationStats(projectId?: string): Promise<Record<string, number>> {
    const response = await this.client.get<Record<string, number>>('/reconciliation/stats', { params: { project_id: projectId } });
    return response.data;
  }

  async autoMatchBatch(params: { project_id?: string; confidence_threshold?: number; dry_run?: boolean }): Promise<Record<string, unknown>> {
    const response = await this.client.post<Record<string, unknown>>('/reconciliation/auto-match', params);
    return response.data;
  }

  // OCR
  async startOCR(evidenceId: string): Promise<Record<string, unknown>> {
    const response = await this.client.post<Record<string, unknown>>('/ocr/process', { evidence_id: evidenceId });
    return response.data;
  }

  async getOCRJob(jobId: string): Promise<OCRJobItem> {
    const response = await this.client.get<OCRJobItem>(`/ocr/jobs/${jobId}`);
    return response.data;
  }

  async getOCRJobs(params?: { page?: number; page_size?: number; status?: string }): Promise<PaginatedResponse<OCRJobItem>> {
    const response = await this.client.get<PaginatedResponse<OCRJobItem>>('/ocr/jobs', { params });
    return response.data;
  }

  // Extraction
  async startExtraction(evidenceId: string): Promise<Record<string, unknown>> {
    const response = await this.client.post<Record<string, unknown>>('/extraction/process', { evidence_id: evidenceId });
    return response.data;
  }

  async getExtractionJob(jobId: string): Promise<ExtractionJobItem> {
    const response = await this.client.get<ExtractionJobItem>(`/extraction/jobs/${jobId}`);
    return response.data;
  }

  async getExtractionJobs(params?: { page?: number; page_size?: number; status?: string }): Promise<PaginatedResponse<ExtractionJobItem>> {
    const response = await this.client.get<PaginatedResponse<ExtractionJobItem>>('/extraction/jobs', { params });
    return response.data;
  }

  async extractSync(evidenceId: string): Promise<Record<string, unknown>> {
    const response = await this.client.post<Record<string, unknown>>('/extraction/process-sync', { evidence_id: evidenceId });
    return response.data;
  }

  // Dashboard
  async getDashboardStats(): Promise<DashboardStats> {
    try {
      const response = await this.client.get<DashboardStats>('/dashboard/stats');
      return response.data;
    } catch {
      // Gracefully aggregate from domain endpoints accessible to current user
      const [projectsRes, expensesRes, recStats] = await Promise.all([
        this.getProjects({ page_size: 100 }).catch(() => ({ items: [], total: 0 })),
        this.getExpenses({ limit: 100 }).catch(() => ({ items: [], total: 0 })),
        this.getReconciliationStats().catch(() => ({ total: 0, matched: 0, pending: 0 })),
      ]);

      const projects = projectsRes.items || [];
      const expenses = expensesRes.items || [];
      const activeProjects = projects.filter((p) => p.status === 'active').length;
      const pendingExpenses = expenses.filter((e) =>
        ['RECEIVED', 'VALIDATED', 'PROCESSING', 'EXTRACTED', 'NEEDS_CONFIRMATION', 'STAGED', 'RECONCILING'].includes(e.lifecycle_status ?? '')
      ).length;
      const reconciledExpenses = expenses.filter((e) => e.lifecycle_status === 'RECONCILED').length;
      const postedExpenses = expenses.filter((e) => e.lifecycle_status === 'POSTED').length;
      const spentBudget = expenses.reduce((sum: number, e) => sum + (Number(e.total) || 0), 0);

      return {
        total_projects: projectsRes.total || projects.length,
        active_projects: activeProjects,
        total_expenses: expensesRes.total || expenses.length,
        pending_expenses: pendingExpenses,
        reconciled_expenses: reconciledExpenses,
        posted_expenses: postedExpenses,
        total_budget: Math.round(spentBudget * 1.2),
        spent_budget: Math.round(spentBudget),
        pending_reconciliation: recStats?.pending || 0,
      };
    }
  }

  // Audit Compliance
  async getRetentionPolicies(): Promise<DataRetentionPolicyResponse[]> {
    const response = await this.client.get('/audit-compliance/retention-policies');
    return response.data;
  }

  async createRetentionPolicy(data: DataRetentionPolicyCreate): Promise<DataRetentionPolicyResponse> {
    const response = await this.client.post('/audit-compliance/retention-policies', data);
    return response.data;
  }

  async updateRetentionPolicy(id: string, data: Partial<DataRetentionPolicyCreate>): Promise<DataRetentionPolicyResponse> {
    const response = await this.client.patch(`/audit-compliance/retention-policies/${id}`, data);
    return response.data;
  }

  async deleteRetentionPolicy(id: string): Promise<void> {
    await this.client.delete(`/audit-compliance/retention-policies/${id}`);
  }

  async runRetentionPolicy(policyId: string): Promise<Record<string, unknown>> {
    const response = await this.client.post<Record<string, unknown>>(`/audit-compliance/retention-policies/${policyId}/run`);
    return response.data;
  }

  async runAllRetentionPolicies(): Promise<Record<string, unknown>> {
    const response = await this.client.post<Record<string, unknown>>('/audit-compliance/retention-policies/run-all');
    return response.data;
  }

  async getGdprRequests(params?: { page?: number; page_size?: number; status?: string; request_type?: string }): Promise<GDPRRequestListResponse> {
    const response = await this.client.get('/audit-compliance/gdpr-requests', { params });
    return response.data;
  }

  async createGdprRequest(data: GDPRRequestCreate): Promise<GDPRRequestResponse> {
    const response = await this.client.post('/audit-compliance/gdpr-requests', data);
    return response.data;
  }

  async getGdprRequest(id: string): Promise<GDPRRequestResponse> {
    const response = await this.client.get(`/audit-compliance/gdpr-requests/${id}`);
    return response.data;
  }

  async approveGdprRequest(id: string, responseData?: Record<string, unknown>): Promise<GDPRRequestResponse> {
    const response = await this.client.post(`/audit-compliance/gdpr-requests/${id}/approve`, { response_data: responseData });
    return response.data;
  }

  async rejectGdprRequest(id: string, reason: string): Promise<GDPRRequestResponse> {
    const response = await this.client.post(`/audit-compliance/gdpr-requests/${id}/reject`, { rejection_reason: reason });
    return response.data;
  }

  async processGdprRequest(id: string): Promise<GDPRRequestResponse> {
    const response = await this.client.post(`/audit-compliance/gdpr-requests/${id}/process`);
    return response.data;
  }

  async getAuditReports(params?: { page?: number; page_size?: number; status?: string; report_type?: string }): Promise<PaginatedResponse<AuditReportResponse>> {
    const response = await this.client.get<PaginatedResponse<AuditReportResponse>>('/audit-compliance/reports', { params });
    return response.data;
  }

  async generateAuditReport(data: AuditReportRequest): Promise<AuditReportResponse> {
    const response = await this.client.post('/audit-compliance/reports', data);
    return response.data;
  }

  async getAuditReport(id: string): Promise<AuditReportResponse> {
    const response = await this.client.get(`/audit-compliance/reports/${id}`);
    return response.data;
  }

  async deleteAuditReport(id: string): Promise<void> {
    await this.client.delete(`/audit-compliance/reports/${id}`);
  }

  async downloadAuditReport(id: string): Promise<Blob> {
    const response = await this.client.get(`/audit-compliance/reports/${id}/download`, { responseType: 'blob' });
    return response.data;
  }

  async getAuditTrail(entityType: string, entityId: string, page?: number, pageSize?: number): Promise<PaginatedResponse<Record<string, unknown>>> {
    const response = await this.client.get<PaginatedResponse<Record<string, unknown>>>(`/audit-compliance/trail/${entityType}/${entityId}`, { params: { page, page_size: pageSize } });
    return response.data;
  }

  async getComplianceDashboard(): Promise<ComplianceDashboardResponse> {
    const response = await this.client.get('/audit-compliance/dashboard');
    return response.data;
  }

  // Notifications
  async sendNotification(data: { channel: string; subject?: string; body: string; user_id?: string; priority?: string; metadata?: Record<string, unknown>; scheduled_at?: string }): Promise<Record<string, unknown>> {
    const response = await this.client.post<Record<string, unknown>>('/notifications', data);
    return response.data;
  }

  async sendBulkNotification(userIds: string[], channel: string, body: string, subject?: string, priority: string = 'normal', metadata?: Record<string, unknown>): Promise<Record<string, unknown>> {
    const response = await this.client.post<Record<string, unknown>>('/notifications/bulk', { user_ids: userIds, channel, subject, body, priority, metadata });
    return response.data;
  }

  async getNotifications(params?: { page?: number; page_size?: number; status?: string }): Promise<PaginatedResponse<NotificationItem>> {
    const response = await this.client.get<PaginatedResponse<NotificationItem>>('/notifications', { params });
    return response.data;
  }

  async markNotificationAsRead(id: string): Promise<Record<string, unknown>> {
    const response = await this.client.patch<Record<string, unknown>>(`/notifications/${id}/read`);
    return response.data;
  }

  async markAllNotificationsAsRead(): Promise<Record<string, unknown>> {
    const response = await this.client.post<Record<string, unknown>>('/notifications/mark-all-read');
    return response.data;
  }

  async getNotificationStats(): Promise<NotificationStats> {
    const response = await this.client.get<NotificationStats>('/notifications/stats');
    return response.data;
  }

  async processScheduledNotifications(): Promise<{ sent_count: number }> {
    const response = await this.client.post('/notifications/process-scheduled');
    return response.data;
  }

  // Webhooks
  async createWebhook(data: { url: string; events: string[]; secret?: string; headers?: Record<string, string>; retry_policy?: Record<string, unknown>; is_active?: boolean }): Promise<Record<string, unknown>> {
    const response = await this.client.post<Record<string, unknown>>('/notifications/webhooks', data);
    return response.data;
  }

  async getWebhooks(page = 1, pageSize = 20): Promise<PaginatedResponse<WebhookConfig>> {
    const response = await this.client.get<PaginatedResponse<WebhookConfig>>('/notifications/webhooks', { params: { page, page_size: pageSize } });
    return response.data;
  }

  async getWebhook(id: string): Promise<Record<string, unknown>> {
    const response = await this.client.get<Record<string, unknown>>(`/notifications/webhooks/${id}`);
    return response.data;
  }

  async deleteWebhook(id: string): Promise<void> {
    await this.client.delete(`/notifications/webhooks/${id}`);
  }

  async getWebhookDeliveries(webhookId: string, page = 1, pageSize = 20): Promise<PaginatedResponse<Record<string, unknown>>> {
    const response = await this.client.get<PaginatedResponse<Record<string, unknown>>>(`/notifications/webhooks/${webhookId}/deliveries`, { params: { page, page_size: pageSize } });
    return response.data;
  }

  // Audit Events
  async getAuditEvents(params?: { page?: number; page_size?: number; event_type?: string; entity_type?: string; entity_id?: string; actor_id?: string; date_from?: string; date_to?: string }): Promise<PaginatedResponse<Record<string, unknown>>> {
    const response = await this.client.get<PaginatedResponse<Record<string, unknown>>>('/audit/events', { params });
    return response.data;
  }

  // Auth helpers
  isAuthenticated(): boolean {
    return !!localStorage.getItem('access_token');
  }

  getStoredUser(): User | null {
    const userStr = localStorage.getItem('user');
    if (userStr) {
      try {
        return JSON.parse(userStr);
      } catch {
        return null;
      }
    }
    return null;
  }

  getAccessToken(): string | null {
    return localStorage.getItem('access_token');
  }

  getRefreshToken(): string | null {
    return localStorage.getItem('refresh_token');
  }
}

export const api = new ApiService();
export default api;