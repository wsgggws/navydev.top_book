/* The API client. One place that knows about URLs and error codes. */

const BASE = '/api/v1';
const TOKEN_KEY = 'lector.token';

/** The access token, when the server asks for one. */
export function getToken() {
  try { return localStorage.getItem(TOKEN_KEY) || ''; } catch (error) { return ''; }
}

export function setToken(token) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch (error) { /* storage may be unavailable */ }
}

export class ApiError extends Error {
  constructor(status, code, message, detail) {
    super(message || code);
    this.status = status;
    this.code = code;
    this.detail = detail;
  }
}

async function request(path, options = {}) {
  const headers = new Headers(options.headers || {});
  const token = getToken();
  if (token) headers.set('Authorization', `Bearer ${token}`);
  const response = await fetch(`${BASE}${path}`, { ...options, headers });
  if (response.status === 204) return null;
  const type = response.headers.get('content-type') || '';
  if (!type.includes('application/json')) {
    if (!response.ok) throw new ApiError(response.status, 'INTERNAL_ERROR', response.statusText);
    return response;
  }
  const payload = await response.json();
  if (!response.ok) {
    const error = payload && payload.error ? payload.error : {};
    throw new ApiError(response.status, error.code || 'INTERNAL_ERROR', error.message, error.detail);
  }
  return payload;
}

export const api = {
  health: () => request('/health'),
  voices: () => request('/tts/voices'),

  listBooks: () => request('/books'),
  getBook: (bookId) => request(`/books/${bookId}`),
  deleteBook: (bookId) => request(`/books/${bookId}`, { method: 'DELETE' }),
  uploadBook: (file, fields = {}) => {
    const form = new FormData();
    form.append('file', file, file.name || 'book.epub');
    for (const [key, value] of Object.entries(fields)) {
      if (value) form.append(key, value);
    }
    return request('/books', { method: 'POST', body: form });
  },

  getToc: (bookId) => request(`/books/${bookId}/toc`),
  getChapter: (bookId, chapterId) => request(`/books/${bookId}/chapters/${chapterId}`),
  getTimeline: (bookId, chapterId) => request(`/books/${bookId}/chapters/${chapterId}/timeline`),

  audioUrl: (bookId, sentenceId, voiceId, rate) => {
    const query = new URLSearchParams();
    if (voiceId) query.set('voice_id', voiceId);
    if (rate && rate !== '+0%') query.set('rate', rate);
    const suffix = query.toString() ? `?${query}` : '';
    return `${BASE}/books/${bookId}/audio/${sentenceId}.mp3${suffix}`;
  },
  getWords: (bookId, sentenceId, voiceId, rate) => {
    const query = new URLSearchParams();
    if (voiceId) query.set('voice_id', voiceId);
    if (rate && rate !== '+0%') query.set('rate', rate);
    const suffix = query.toString() ? `?${query}` : '';
    return request(`/books/${bookId}/audio/${sentenceId}.words${suffix}`);
  },
  warmAudio: (bookId, body) => request(`/books/${bookId}/audio/warm`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }),
  clearAudio: (bookId) => request(`/books/${bookId}/audio`, { method: 'DELETE' }),

  getProgress: (bookId) => request(`/books/${bookId}/progress`),
  setProgress: (bookId, body) => request(`/books/${bookId}/progress`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', 'X-Lector-Client': 'web' },
    body: JSON.stringify(body),
  }),

  search: (bookId, query, limit = 50) =>
    request(`/books/${bookId}/search?q=${encodeURIComponent(query)}&limit=${limit}`),

  createShortCode: (body) => request('/s', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }),
  resolveShortCode: (code) => request(`/s/${code}`),
};
