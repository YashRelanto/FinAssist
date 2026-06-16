export type StoredChatMessage = {
  id: number;
  role: 'user' | 'ai';
  time: string;
  text: string;
  type: 'text';
  intent?: string;
  sources?: string[];
  clarificationOptions?: string[];
};

const SESSION_KEY = 'finassist_chat_session';
const THREAD_STORAGE_KEY = 'finassist_chat_thread_id';

interface ChatSessionPayload {
  userId: string;
  threadId: string;
  messages: StoredChatMessage[];
}

function isValidMessage(value: unknown): value is StoredChatMessage {
  if (!value || typeof value !== 'object') return false;
  const m = value as Record<string, unknown>;
  return (
    typeof m.id === 'number' &&
    (m.role === 'user' || m.role === 'ai') &&
    typeof m.time === 'string' &&
    typeof m.text === 'string' &&
    m.type === 'text'
  );
}

export function loadChatSession(userId: string, threadId: string): StoredChatMessage[] | null {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY);
    if (!raw) return null;

    const parsed = JSON.parse(raw) as ChatSessionPayload;
    if (parsed.userId !== userId || parsed.threadId !== threadId) return null;
    if (!Array.isArray(parsed.messages) || parsed.messages.length === 0) return null;
    if (!parsed.messages.every(isValidMessage)) return null;

    return parsed.messages;
  } catch {
    return null;
  }
}

export function saveChatSession(
  userId: string,
  threadId: string,
  messages: StoredChatMessage[]
): void {
  try {
    const payload: ChatSessionPayload = { userId, threadId, messages };
    sessionStorage.setItem(SESSION_KEY, JSON.stringify(payload));
  } catch {
    /* ignore quota / private mode errors */
  }
}

/** Clears in-tab chat UI state and thread id (e.g. on sign-out). */
export function clearChatSession(): void {
  try {
    sessionStorage.removeItem(SESSION_KEY);
    sessionStorage.removeItem(THREAD_STORAGE_KEY);
  } catch {
    /* ignore */
  }
}
