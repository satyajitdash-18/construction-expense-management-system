import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { User } from '@/types/api';

interface AuthState {
  user: User | null;
  tokens: { access_token: string; refresh_token: string; token_type?: string; expires_in?: number } | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  setAuth: (user: User, tokens: { access_token: string; refresh_token: string; token_type?: string; expires_in?: number }) => void;
  clearAuth: () => void;
  setLoading: (loading: boolean) => void;
  updateUser: (user: Partial<User>) => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      tokens: null,
      isAuthenticated: false,
      isLoading: false,
      
      setAuth: (user: User, tokens: { access_token: string; refresh_token: string; token_type?: string; expires_in?: number }) => {
        localStorage.setItem('access_token', tokens.access_token);
        localStorage.setItem('refresh_token', tokens.refresh_token);
        localStorage.setItem('user', JSON.stringify(user));
        set({ 
          user, 
          tokens: { 
            access_token: tokens.access_token, 
            refresh_token: tokens.refresh_token,
            token_type: tokens.token_type || 'bearer',
            expires_in: tokens.expires_in || 3600
          }, 
          isAuthenticated: true 
        });
      },
      
      clearAuth: () => {
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        localStorage.removeItem('user');
        set({ user: null, tokens: null, isAuthenticated: false });
      },
      
      setLoading: (loading: boolean) => {
        set({ isLoading: loading });
      },
      
      updateUser: (userData: Partial<User>) => {
        set((state) => {
          if (!state.user) return state;
          const updatedUser = { ...state.user, ...userData };
          localStorage.setItem('user', JSON.stringify(updatedUser));
          return { user: updatedUser };
        });
      },
    }),
    {
      name: 'auth-storage',
      partialize: (state) => ({
        user: state.user,
        tokens: state.tokens,
        isAuthenticated: state.isAuthenticated,
      }),
    }
  )
);

export const useAuth = () => {
  const { user, tokens, isAuthenticated, isLoading, setAuth, clearAuth, setLoading, updateUser } = useAuthStore();
  return { user, tokens, isAuthenticated, isLoading, setAuth, clearAuth, setLoading, updateUser };
};