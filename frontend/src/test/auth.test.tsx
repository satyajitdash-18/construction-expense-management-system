import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import LoginPage from '@/pages/LoginPage';
import ProtectedRoute from '@/components/ProtectedRoute';
import { useAuthStore } from '@/store/authStore';
import { api } from '@/services/api';

// Mock the API service
vi.mock('@/services/api', () => ({
  api: {
    login: vi.fn(),
    logout: vi.fn(),
  },
}));

describe('Authentication & Protected Routing Suite', () => {
  beforeEach(() => {
    localStorage.clear();
    useAuthStore.getState().clearAuth();
    vi.clearAllMocks();
  });

  it('renders login form with all essential fields', () => {
    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>
    );

    expect(screen.getByRole('heading', { name: /sign in/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/email address/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument();
  });

  it('handles successful login and saves credentials to auth store', async () => {
    const mockUser = {
      id: '11111111-1111-1111-1111-111111111111',
      email: 'test@example.com',
      is_active: true,
      roles: [{ id: 'role-1', name: 'admin' }],
    };
    const mockTokens = {
      access_token: 'mock-access-token',
      refresh_token: 'mock-refresh-token',
      token_type: 'bearer',
      expires_in: 3600,
    };

    (api.login as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      user: mockUser,
      tokens: mockTokens,
    });

    render(
      <MemoryRouter initialEntries={['/login']}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/dashboard" element={<div>Dashboard Page</div>} />
        </Routes>
      </MemoryRouter>
    );

    fireEvent.change(screen.getByLabelText(/email address/i), {
      target: { value: 'test@example.com' },
    });
    fireEvent.change(screen.getByLabelText(/password/i), {
      target: { value: 'password123' },
    });
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }));

    await waitFor(() => {
      expect(api.login).toHaveBeenCalledWith({
        email: 'test@example.com',
        password: 'password123',
      });
      expect(useAuthStore.getState().isAuthenticated).toBe(true);
      expect(localStorage.getItem('access_token')).toBe('mock-access-token');
      expect(screen.getByText('Dashboard Page')).toBeInTheDocument();
    });
  });

  it('displays error alert on login API failure', async () => {
    (api.login as ReturnType<typeof vi.fn>).mockRejectedValueOnce({
      response: { data: { detail: 'Incorrect email or password' } },
    });

    render(
      <MemoryRouter initialEntries={['/login']}>
        <LoginPage />
      </MemoryRouter>
    );

    fireEvent.change(screen.getByLabelText(/email address/i), {
      target: { value: 'wrong@example.com' },
    });
    fireEvent.change(screen.getByLabelText(/password/i), {
      target: { value: 'wrongpass' },
    });
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }));

    await waitFor(() => {
      expect(screen.getByText('Incorrect email or password')).toBeInTheDocument();
      expect(useAuthStore.getState().isAuthenticated).toBe(false);
    });
  });

  it('redirects unauthenticated user away from protected routes to /login', () => {
    render(
      <MemoryRouter initialEntries={['/expenses']}>
        <Routes>
          <Route
            path="/expenses"
            element={
              <ProtectedRoute>
                <div>Protected Expenses Content</div>
              </ProtectedRoute>
            }
          />
          <Route path="/login" element={<div>Login Page Target</div>} />
        </Routes>
      </MemoryRouter>
    );

    expect(screen.queryByText('Protected Expenses Content')).not.toBeInTheDocument();
    expect(screen.getByText('Login Page Target')).toBeInTheDocument();
  });

  it('allows access to protected route when authenticated in store or localStorage', () => {
    localStorage.setItem('access_token', 'valid-active-token');

    render(
      <MemoryRouter initialEntries={['/expenses']}>
        <Routes>
          <Route
            path="/expenses"
            element={
              <ProtectedRoute>
                <div>Protected Expenses Content</div>
              </ProtectedRoute>
            }
          />
          <Route path="/login" element={<div>Login Page Target</div>} />
        </Routes>
      </MemoryRouter>
    );

    expect(screen.getByText('Protected Expenses Content')).toBeInTheDocument();
    expect(screen.queryByText('Login Page Target')).not.toBeInTheDocument();
  });

  it('clears auth state on logout', () => {
    useAuthStore.getState().setAuth(
      { id: '123', email: 'user@example.com', is_active: true, full_name: '', role: 'site_user', created_at: new Date().toISOString() },
      { access_token: 'token123', refresh_token: 'refresh123' }
    );

    expect(useAuthStore.getState().isAuthenticated).toBe(true);
    expect(localStorage.getItem('access_token')).toBe('token123');

    useAuthStore.getState().clearAuth();

    expect(useAuthStore.getState().isAuthenticated).toBe(false);
    expect(localStorage.getItem('access_token')).toBeNull();
    expect(localStorage.getItem('user')).toBeNull();
  });
});
