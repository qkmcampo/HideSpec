import { io } from 'socket.io-client';
import { API_BASE_URL, STREAM_URL, WS_URL } from '../config/api';

let socket = null;

async function safeJson(response) {
  const text = await response.text();

  try {
    return text ? JSON.parse(text) : null;
  } catch (error) {
    throw new Error(`Invalid JSON response: ${text}`);
  }
}

async function apiGet(path) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'GET',
    headers: {
      Accept: 'application/json',
    },
  });

  const data = await safeJson(response);

  if (!response.ok) {
    const message =
      data?.error ||
      data?.message ||
      `Request failed with status ${response.status}`;
    throw new Error(message);
  }

  return data;
}

async function streamGet(path) {
  const response = await fetch(`${STREAM_URL}${path}`, {
    method: 'GET',
    headers: {
      Accept: 'application/json',
    },
  });

  const data = await safeJson(response);

  if (!response.ok) {
    const message =
      data?.error ||
      data?.message ||
      `Request failed with status ${response.status}`;
    throw new Error(message);
  }

  return data;
}

export async function getSystemStatus() {
  try {
    return await apiGet('/api/status');
  } catch (error) {
    console.error('getSystemStatus error:', error.message);
    return {
      status: 'offline',
      session: {
        total_inspected: 0,
        good_count: 0,
        bad_count: 0,
        defect_rate: 0,
      },
    };
  }
}

export async function getLatestInspection() {
  try {
    return await apiGet('/api/inspections/latest');
  } catch (error) {
    console.error('getLatestInspection error:', error.message);
    return null;
  }
}

export async function getInspections(limit = 20) {
  try {
    return await apiGet(`/api/inspections?limit=${limit}`);
  } catch (error) {
    console.error('getInspections error:', error.message);
    return {
      count: 0,
      inspections: [],
    };
  }
}

export async function getStreamStatus() {
  try {
    return await streamGet('/api/stream/status');
  } catch (error) {
    console.error('getStreamStatus error:', error.message);
    return null;
  }
}

export async function getAnalytics(period = 'today') {
  try {
    return await apiGet(`/api/analytics?period=${period}`);
  } catch (error) {
    console.error('getAnalytics error:', error.message);
    return {
      total_inspections: 0,
      good_count: 0,
      bad_count: 0,
      pass_rate: 0,
      defect_rate: 0,
      avg_defects_per_hide: 0,
      period,
    };
  }
}

export async function getAnalyticsSummary() {
  try {
    return await apiGet('/api/analytics/summary');
  } catch (error) {
    console.error('getAnalyticsSummary error:', error.message);
    return {
      total_inspections: 0,
      good_count: 0,
      bad_count: 0,
      pass_rate: 0,
      defect_rate: 0,
      avg_defects_per_hide: 0,
    };
  }
}

export async function getDefectDistribution(period = 'today') {
  try {
    return await apiGet(`/api/analytics/defects?period=${period}`);
  } catch (error) {
    console.error('getDefectDistribution error:', error.message);
    return {
      defects: [],
    };
  }
}

export async function getTimeline(period = 'today') {
  try {
    return await apiGet(`/api/analytics/timeline?period=${period}`);
  } catch (error) {
    console.error('getTimeline error:', error.message);
    return {
      timeline: [],
    };
  }
}

export async function resetHistory(deleteCaptures = false) {
  try {
    const response = await fetch(`${API_BASE_URL}/api/history/reset`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      body: JSON.stringify({
        delete_captures: deleteCaptures,
      }),
    });

    const data = await safeJson(response);

    if (!response.ok) {
      const message =
        data?.error ||
        data?.message ||
        `Request failed with status ${response.status}`;
      throw new Error(message);
    }

    return data;
  } catch (error) {
    console.error('resetHistory error:', error.message);
    throw error;
  }
}

export function connectWebSocket(handlers = {}) {
  const {
    onConnect,
    onDisconnect,
    onNewInspection,
    onStatusUpdate,
    onConnectedMessage,
  } = handlers;

  if (socket) {
    return socket;
  }

  socket = io(WS_URL, {
    transports: ['websocket', 'polling'],
    reconnection: true,
    reconnectionAttempts: Infinity,
    reconnectionDelay: 1000,
    timeout: 5000,
  });

  socket.on('connect', () => {
    if (onConnect) onConnect();
  });

  socket.on('disconnect', () => {
    if (onDisconnect) onDisconnect();
  });

  socket.on('connected', (data) => {
    if (onConnectedMessage) onConnectedMessage(data);
  });

  socket.on('new_inspection', (data) => {
    if (onNewInspection) onNewInspection(data);
  });

  socket.on('status_update', (data) => {
    if (onStatusUpdate) onStatusUpdate(data);
  });

  socket.on('connect_error', (error) => {
    console.error('WebSocket connect_error:', error.message);
  });

  return socket;
}

export function disconnectWebSocket() {
  if (socket) {
    socket.disconnect();
    socket = null;
  }
}

export default {
  getSystemStatus,
  getLatestInspection,
  getInspections,
  getStreamStatus,
  getAnalytics,
  getAnalyticsSummary,
  getDefectDistribution,
  getTimeline,
  resetHistory,
  connectWebSocket,
  disconnectWebSocket,
};