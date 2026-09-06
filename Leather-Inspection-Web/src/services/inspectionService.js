import { API_BASE_URL, STREAM_URL, VIDEO_FEED_URL } from '../config/api';

const REQUEST_TIMEOUT_MS = 5000;

async function request(url, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  try {
    const response = await fetch(url, { ...options, signal: controller.signal });
    const data = await response.json().catch(() => null);

    if (!response.ok) {
      throw new Error(data?.error || data?.message || `Request failed (${response.status})`);
    }

    return data;
  } finally {
    clearTimeout(timeout);
  }
}

export const inspectionService = {
  status: () => request(`${API_BASE_URL}/api/status`).catch((error) => ({ status: 'offline', error: error.message, session: {} })),
  latest: () => request(`${API_BASE_URL}/api/inspections/latest`).catch(() => null),
  history: (limit = 10) => request(`${API_BASE_URL}/api/inspections?limit=${limit}`).catch(() => ({ inspections: [] })),
  stream: () => request(`${STREAM_URL}/api/stream/status`).catch((error) => ({ status: 'offline', error: error.message, machine: {} })),
  analytics: (period) => request(`${API_BASE_URL}/api/analytics?period=${period}`).catch(() => ({})),
  defects: (period) => request(`${API_BASE_URL}/api/analytics/defects?period=${period}`).catch(() => ({ defects: [] })),
  timeline: (period) => request(`${API_BASE_URL}/api/analytics/timeline?period=${period}`).catch(() => ({ timeline: [] })),
  quality: (period) => request(`${API_BASE_URL}/api/analytics/quality?period=${period}`).catch(() => ({ good: 0, bad: 0, total: 0 })),
  defectArea: (period) => request(`${API_BASE_URL}/api/analytics/defect-area?period=${period}`).catch(() => ({ min_percent: 0, max_percent: 0, avg_percent: 0 })),
  reset: () => request(`${API_BASE_URL}/api/history/reset`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ delete_captures: false }),
  }),
};

export function subscribeToInspections() {
  return () => {};
}

export { API_BASE_URL, STREAM_URL, VIDEO_FEED_URL };
