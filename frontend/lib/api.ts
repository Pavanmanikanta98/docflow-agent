import axios from 'axios';
import { v4 as uuidv4 } from 'uuid';

const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000',
});

// ---------------------------------------------------------------------------
// Session ID — generated once per browser, stored in localStorage
// ---------------------------------------------------------------------------

const SESSION_KEY = 'docflow_session_id';

export function getSessionId(): string {
  if (typeof window === 'undefined') return 'ssr';
  let id = localStorage.getItem(SESSION_KEY);
  if (!id) {
    id = `ses_${uuidv4().replace(/-/g, '').slice(0, 16)}`;
    localStorage.setItem(SESSION_KEY, id);
  }
  return id;
}

// ---------------------------------------------------------------------------
// Request interceptor — attach session ID to every request
// ---------------------------------------------------------------------------

api.interceptors.request.use((config) => {
  if (typeof window !== 'undefined') {
    config.headers['X-Session-Id'] = getSessionId();
  }
  return config;
});

export default api;
