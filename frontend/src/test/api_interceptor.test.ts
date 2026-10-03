import { describe, it, expect, beforeEach, vi } from 'vitest';
import { api } from '@/services/api';

vi.mock('axios', async () => {
  const actual = await vi.importActual<typeof import('axios')>('axios');
  const mockAxiosInstance = {
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() },
    },
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  };
  return {
    ...actual,
    default: {
      ...actual,
      create: vi.fn(() => mockAxiosInstance),
      post: vi.fn(),
    },
  };
});

describe('API Client & Authorization Interceptor Suite', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });

  it('stores and retrieves access and refresh tokens correctly', () => {
    api.setAuth(
      {
        id: 'u-1',
        email: 'test@example.com',
        full_name: 'Test User',
        role: 'admin',
        is_active: true,
        created_at: new Date().toISOString(),
      },
      {
        access_token: 'acc-token-123',
        refresh_token: 'ref-token-456',
      }
    );

    expect(api.getAccessToken()).toBe('acc-token-123');
    expect(api.getRefreshToken()).toBe('ref-token-456');
    expect(api.isAuthenticated()).toBe(true);

    const storedUser = api.getStoredUser();
    expect(storedUser?.email).toBe('test@example.com');
    expect(storedUser?.role).toBe('admin');
  });

  it('clearAuth wipes all stored session credentials', () => {
    localStorage.setItem('access_token', 'temp-acc');
    localStorage.setItem('refresh_token', 'temp-ref');
    localStorage.setItem('user', JSON.stringify({ email: 'user@example.com' }));

    api.clearAuth();

    expect(localStorage.getItem('access_token')).toBeNull();
    expect(localStorage.getItem('refresh_token')).toBeNull();
    expect(localStorage.getItem('user')).toBeNull();
    expect(api.isAuthenticated()).toBe(false);
  });

  it('logout passes refresh_token to backend and clears session', async () => {
    localStorage.setItem('access_token', 'token-to-revoke');
    localStorage.setItem('refresh_token', 'refresh-to-revoke');

    const clientPostSpy = vi.spyOn((api as unknown as { client: { post: unknown } }).client as { post: (...args: unknown[]) => Promise<unknown> }, 'post').mockResolvedValueOnce({ data: null });

    await api.logout();

    expect(clientPostSpy).toHaveBeenCalledWith('/auth/logout', {
      refresh_token: 'refresh-to-revoke',
    });
    expect(api.getAccessToken()).toBeNull();
    expect(api.getRefreshToken()).toBeNull();
  });

  it('gracefully aggregates dashboard stats when /dashboard/stats returns 404', async () => {
    // Mock /dashboard/stats failing with 404
    vi.spyOn((api as unknown as { client: { get: unknown } }).client as { get: (...args: unknown[]) => Promise<unknown> }, 'get').mockImplementation(async (...args: unknown[]) => {
      const url = args[0] as string;
      if (url === '/dashboard/stats') {
        const err = new Error('Not Found');
        (err as Error & { response: object }).response = { status: 404, data: { detail: 'Not Found' } };
        throw err;
      }
      if (url === '/projects') {
        return {
          data: {
            items: [
              { id: 'p1', name: 'Project 1', status: 'active' },
              { id: 'p2', name: 'Project 2', status: 'completed' },
            ],
            total: 2,
          },
        };
      }
      if (url === '/expenses') {
        return {
          data: {
            items: [
              { id: 'e1', total: 500, lifecycle_status: 'RECEIVED' },
              { id: 'e2', total: 1500, lifecycle_status: 'POSTED' },
            ],
            total: 2,
          },
        };
      }
      if (url === '/reconciliation/stats') {
        return {
          data: { total: 10, matched: 8, pending: 2 },
        };
      }
      return { data: {} };
    });

    const stats = await api.getDashboardStats();

    expect(stats.total_projects).toBe(2);
    expect(stats.active_projects).toBe(1);
    expect(stats.total_expenses).toBe(2);
    expect(stats.posted_expenses).toBe(1);
    expect(stats.pending_expenses).toBe(1);
    expect(stats.spent_budget).toBe(2000);
  });
});
