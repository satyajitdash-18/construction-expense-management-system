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
} from '@/types/api';

const API_BASE_URL = (import.meta as any).env?.VITE_API_BASE_URL || '/api/v1';

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
        const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean };

        if (error.response?.status === 401 && !originalRequest._retry) {
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
            window.location.href = '/login';
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

  setAuth(user: User, tokens: { access_token: string; refresh_token: string }): void {
    localStorage.setItem('user', JSON.stringify(user));
    localStorage.setItem('access_token', tokens.access_token);
    localStorage.setItem('refresh_token', tokens.refresh_token);
  }

  // Auth
  async login(credentials: LoginRequest): Promise<UserResponse> {
    const response = await this.client.post<UserResponse>('/auth/login', credentials);
    this.setAuth(response.data.user, { 
      access_token: response.data.tokens.access_token, 
      refresh_token: response.data.tokens.refresh_token 
    });
    return response.data;
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
    await this.client.post('/auth/logout');
    this.clearAuth();
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

  async updateNotificationPreferences(data: Record<string, boolean>): Promise<any> {
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

  async createExpense(data: any): Promise<Expense> {
    const response = await this.client.post<Expense>('/expenses', data);
    return response.data;
  }

  async updateExpense(id: string, data: any): Promise<Expense> {
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

  async listEvidence(expenseId: string, page?: number, pageSize?: number): Promise<any> {
    const response = await this.client.get(`/evidence/expense/${expenseId}`, { params: { page, page_size: pageSize } });
    return response.data;
  }

  async deleteEvidence(evidenceId: string): Promise<void> {
    await this.client.delete(`/evidence/${evidenceId}`);
  }

  async getEvidenceList(params?: { page?: number; page_size?: number }): Promise<any> {
    const response = await this.client.get('/evidence', { params });
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
  }): Promise<any> {
    const response = await this.client.get('/reconciliation/records', { params });
    return response.data;
  }

  async getReconciliation(id: string): Promise<any> {
    const response = await this.client.get(`/reconciliation/records/${id}`);
    return response.data;
  }

  async reconcileExpense(expenseId: string, paymentEventId?: string, autoMatch: boolean = true): Promise<any> {
    const response = await this.client.post('/reconciliation/match', { expense_id: expenseId, payment_event_id: paymentEventId, auto_match: autoMatch });
    return response.data;
  }

  async confirmReconciliation(recordId: string, notes?: string): Promise<any> {
    const response = await this.client.post(`/reconciliation/records/${recordId}/action`, { action: 'confirm', notes });
    return response.data;
  }

  async rejectReconciliation(recordId: string, notes: string): Promise<any> {
    const response = await this.client.post(`/reconciliation/records/${recordId}/action`, { action: 'reject', notes });
    return response.data;
  }

  async unmatchReconciliation(recordId: string, notes: string): Promise<any> {
    const response = await this.client.post(`/reconciliation/records/${recordId}/action`, { action: 'unmatch', notes });
    return response.data;
  }

  async getReconciliationStats(projectId?: string): Promise<any> {
    const response = await this.client.get('/reconciliation/stats', { params: { project_id: projectId } });
    return response.data;
  }

  async autoMatchBatch(params: { project_id?: string; confidence_threshold?: number; dry_run?: boolean }): Promise<any> {
    const response = await this.client.post('/reconciliation/auto-match', params);
    return response.data;
  }

  // OCR
  async startOCR(evidenceId: string): Promise<any> {
    const response = await this.client.post('/ocr/process', { evidence_id: evidenceId });
    return response.data;
  }

  async getOCRJob(jobId: string): Promise<any> {
    const response = await this.client.get(`/ocr/jobs/${jobId}`);
    return response.data;
  }

  async getOCRJobs(params?: { page?: number; page_size?: number; status?: string }): Promise<any> {
    const response = await this.client.get('/ocr/jobs', { params });
    return response.data;
  }

  // Extraction
  async startExtraction(evidenceId: string): Promise<any> {
    const response = await this.client.post('/extraction/process', { evidence_id: evidenceId });
    return response.data;
  }

  async getExtractionJob(jobId: string): Promise<any> {
    const response = await this.client.get(`/extraction/jobs/${jobId}`);
    return response.data;
  }

  async getExtractionJobs(params?: { page?: number; page_size?: number; status?: string }): Promise<any> {
    const response = await this.client.get('/extraction/jobs', { params });
    return response.data;
  }

  async extractSync(evidenceId: string): Promise<any> {
    const response = await this.client.post('/extraction/process-sync', { evidence_id: evidenceId });
    return response.data;
  }

  // Dashboard
  async getDashboardStats(): Promise<DashboardStats> {
    const response = await this.client.get<DashboardStats>('/dashboard/stats');
    return response.data;
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

  async runRetentionPolicy(policyId: string): Promise<any> {
    const response = await this.client.post(`/audit-compliance/retention-policies/${policyId}/run`);
    return response.data;
  }

  async runAllRetentionPolicies(): Promise<any> {
    const response = await this.client.post('/audit-compliance/retention-policies/run-all');
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

  async approveGdprRequest(id: string, responseData?: any): Promise<GDPRRequestResponse> {
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

  async getAuditReports(params?: { page?: number; page_size?: number; status?: string; report_type?: string }): Promise<any> {
    const response = await this.client.get('/audit-compliance/reports', { params });
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

  async getAuditTrail(entityType: string, entityId: string, page?: number, pageSize?: number): Promise<any> {
    const response = await this.client.get(`/audit-compliance/trail/${entityType}/${entityId}`, { params: { page, page_size: pageSize } });
    return response.data;
  }

  async getComplianceDashboard(): Promise<ComplianceDashboardResponse> {
    const response = await this.client.get('/audit-compliance/dashboard');
    return response.data;
  }

  // Notifications
  async sendNotification(data: { channel: string; subject?: string; body: string; user_id?: string; priority?: string; metadata?: Record<string, any>; scheduled_at?: string }): Promise<any> {
    const response = await this.client.post('/notifications', data);
    return response.data;
  }

  async sendBulkNotification(userIds: string[], channel: string, body: string, subject?: string, priority: string = 'normal', metadata?: Record<string, any>): Promise<any> {
    const response = await this.client.post('/notifications/bulk', { user_ids: userIds, channel, subject, body, priority, metadata });
    return response.data;
  }

  async getNotifications(params?: { page?: number; page_size?: number; status?: string }): Promise<any> {
    const response = await this.client.get('/notifications', { params });
    return response.data;
  }

  async markNotificationAsRead(id: string): Promise<any> {
    const response = await this.client.patch(`/notifications/${id}/read`);
    return response.data;
  }

  async markAllNotificationsAsRead(): Promise<any> {
    const response = await this.client.post('/notifications/mark-all-read');
    return response.data;
  }

  async getNotificationStats(): Promise<any> {
    const response = await this.client.get('/notifications/stats');
    return response.data;
  }

  async processScheduledNotifications(): Promise<{ sent_count: number }> {
    const response = await this.client.post('/notifications/process-scheduled');
    return response.data;
  }

  // Webhooks
  async createWebhook(data: { url: string; events: string[]; secret?: string; headers?: Record<string, string>; retry_policy?: any; is_active?: boolean }): Promise<any> {
    const response = await this.client.post('/notifications/webhooks', data);
    return response.data;
  }

  async getWebhooks(page = 1, pageSize = 20): Promise<any> {
    const response = await this.client.get('/notifications/webhooks', { params: { page, page_size: pageSize } });
    return response.data;
  }

  async getWebhook(id: string): Promise<any> {
    const response = await this.client.get(`/notifications/webhooks/${id}`);
    return response.data;
  }

  async deleteWebhook(id: string): Promise<void> {
    await this.client.delete(`/notifications/webhooks/${id}`);
  }

  async getWebhookDeliveries(webhookId: string, page = 1, pageSize = 20): Promise<any> {
    const response = await this.client.get(`/notifications/webhooks/${webhookId}/deliveries`, { params: { page, page_size: pageSize } });
    return response.data;
  }

  // Audit Events
  async getAuditEvents(params?: { page?: number; page_size?: number; event_type?: string; entity_type?: string; entity_id?: string; actor_id?: string; date_from?: string; date_to?: string }): Promise<any> {
    const response = await this.client.get('/audit/events', { params });
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