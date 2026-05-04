import axios from 'axios';
import { v4 as uuidv4 } from 'uuid';

const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000',
});

// ---------------------------------------------------------------------------
// Session ID — generated once per browser, stored in localStorage
// ---------------------------------------------------------------------------

const SESSION_KEY = 'docflow_session_id';
const LLM_KEY_STORAGE = 'docflow_llm_key';

export function getSessionId(): string {
  if (typeof window === 'undefined') return 'ssr';
  let id = localStorage.getItem(SESSION_KEY);
  if (!id) {
    id = `ses_${uuidv4().replace(/-/g, '').slice(0, 16)}`;
    localStorage.setItem(SESSION_KEY, id);
  }
  return id;
}

export function getUserLlmKey(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem(LLM_KEY_STORAGE);
}

export function setUserLlmKey(key: string): void {
  if (typeof window === 'undefined') return;
  localStorage.setItem(LLM_KEY_STORAGE, key);
}

export function clearUserLlmKey(): void {
  if (typeof window === 'undefined') return;
  localStorage.removeItem(LLM_KEY_STORAGE);
}

// ---------------------------------------------------------------------------
// Request interceptor — attach session ID + optional LLM key to every request
// ---------------------------------------------------------------------------

api.interceptors.request.use((config) => {
  if (typeof window !== 'undefined') {
    config.headers['X-Session-Id'] = getSessionId();

    const llmKey = getUserLlmKey();
    if (llmKey) {
      config.headers['X-LLM-Key'] = llmKey;
    }
  }
  return config;
});

export default api;
