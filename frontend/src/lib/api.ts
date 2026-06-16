export const API_BASE = 'http://localhost:8000';

export function apiUrl(path: string): string {
  if (path.startsWith('http')) return path;
  return `${API_BASE}${path.startsWith('/') ? path : `/${path}`}`;
}

/** Always fetch fresh data — no browser HTTP cache. */
export async function apiFetch(
  path: string,
  init: RequestInit = {}
): Promise<Response> {
  const headers = new Headers(init.headers);
  headers.set('Cache-Control', 'no-cache');
  headers.set('Pragma', 'no-cache');

  return fetch(apiUrl(path), {
    ...init,
    cache: 'no-store',
    headers,
  });
}

export interface ChatMessageResponse {
  answer: string;
  intent: string;
  sources: string[];
  needs_clarification: boolean;
  clarification_options: string[];
  thread_id: string;
  user_id: string;
}

export async function sendChatMessage(
  userId: string,
  message: string,
  threadId: string
): Promise<ChatMessageResponse> {
  const response = await apiFetch('/api/chat/message', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      user_id: userId,
      message,
      thread_id: threadId,
    }),
  });
  if (!response.ok) {
    throw new Error(`Chat API failed (${response.status})`);
  }
  return response.json();
}

const THREAD_STORAGE_KEY = 'finassist_chat_thread_id';

export function getOrCreateChatThreadId(): string {
  const existing = sessionStorage.getItem(THREAD_STORAGE_KEY);
  if (existing) return existing;
  const id = crypto.randomUUID();
  sessionStorage.setItem(THREAD_STORAGE_KEY, id);
  return id;
}
