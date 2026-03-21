/* eslint-disable react-refresh/only-export-components */
/* eslint-disable react-hooks/exhaustive-deps */
import React, { createContext, useContext, useState, useEffect } from 'react';
import { jwtDecode } from 'jwt-decode';

const AuthContext = createContext();

export const useAuth = () => useContext(AuthContext);

export const AuthProvider = ({ children }) => {
  const [token, setToken] = useState(localStorage.getItem('token'));
  const [user, setUser] = useState(null);
  const [sessionId] = useState(() => {
    let sid = localStorage.getItem('rem-leases_session_id');
    if (!sid) {
      sid = crypto.randomUUID();
      localStorage.setItem('rem-leases_session_id', sid);
    }
    return sid;
  });

  const logout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    setToken(null);
    setUser(null);
  };

  useEffect(() => {
    if (token) {
      try {
        const decoded = jwtDecode(token);
        if (decoded.exp * 1000 < Date.now()) {
          logout();
        } else {
          // You ideally store user data in LocalStorage during login too, or fetch it based on the token.
          const storedUser = localStorage.getItem('user');
          if (storedUser) {
            setUser(JSON.parse(storedUser));
          } else {
            setUser({ id: decoded.sub }); // Basic fallback
          }
        }
      } catch {
        logout();
      }
    }
  }, [token]);

  const login = (newToken, userData) => {
    localStorage.setItem('token', newToken);
    localStorage.setItem('user', JSON.stringify(userData));
    setToken(newToken);
    setUser(userData);
  };

  return (
    <AuthContext.Provider value={{ token, user, sessionId, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
};
