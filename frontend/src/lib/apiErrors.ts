/** Normalize FastAPI / fetch error payloads for display. */
export function parseApiError(data: unknown, fallback = 'Request failed'): string {
  if (!data || typeof data !== 'object') return fallback;
  const detail = (data as { detail?: unknown }).detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item === 'string') return item;
        if (item && typeof item === 'object' && 'msg' in item) {
          return String((item as { msg?: string }).msg);
        }
        return JSON.stringify(item);
      })
      .join('; ');
  }
  if (detail && typeof detail === 'object' && 'message' in detail) {
    return String((detail as { message?: string }).message);
  }
  return fallback;
}

export async function readJsonResponse(res: Response): Promise<unknown> {
  const text = await res.text();
  if (!text) return {};
  try {
    return JSON.parse(text);
  } catch {
    return { detail: text };
  }
}
