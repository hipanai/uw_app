import { useState, useCallback, useEffect } from 'react';
import { login as apiLogin, verifyToken } from '@/api/jobs';
import { setAuthToken, clearAuthToken, getAuthToken } from '@/api/client';

interface AuthState {
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;
}

export function useAuth() {
  const [state, setState] = useState<AuthState>({
    isAuthenticated: !!getAuthToken(),
    isLoading: true,
    error: null,
  });

  // Verify token on mount
  useEffect(() => {
    const checkAuth = async () => {
      const token = getAuthToken();
      if (!token) {
        setState({ isAuthenticated: false, isLoading: false, error: null });
        return;
      }

      try {
        const result = await verifyToken();
        setState({
          isAuthenticated: result.valid,
          isLoading: false,
          error: null,
        });
        if (!result.valid) {
          clearAuthToken();
        }
      } catch {
        setState({ isAuthenticated: false, isLoading: false, error: null });
        clearAuthToken();
      }
    };

    checkAuth();
  }, []);

  const login = useCallback(async (password: string): Promise<boolean> => {
    setState((prev) => ({ ...prev, isLoading: true, error: null }));

    try {
      const response = await apiLogin(password);
      setAuthToken(response.token);
      setState({ isAuthenticated: true, isLoading: false, error: null });
      return true;
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Invalid password';
      setState({ isAuthenticated: false, isLoading: false, error: message });
      return false;
    }
  }, []);

  const logout = useCallback(() => {
    clearAuthToken();
    setState({ isAuthenticated: false, isLoading: false, error: null });
  }, []);

  return {
    isAuthenticated: state.isAuthenticated,
    isLoading: state.isLoading,
    error: state.error,
    login,
    logout,
  };
}
