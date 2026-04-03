import { API_BASE_URL, WS_URL } from '../config/api';
import { io } from 'socket.io-client';

export async function getSystemStatus() {
  try {
    const response = await fetch(`${API_BASE_URL}/api/status`);
    if (!response.ok) throw new Error('Failed to fetch status');
    return await response.json();
  } catch (error) {
    console.error('getSystemStatus error:', error);
    return null;
  }
}

export async function getInspections(limit = 50, offset = 0, classification = null) {
  try {
    let url = `${API_BASE_URL}/api/inspections?limit=${limit}&offset=${offset}`;
    if (classification) url += `&classification=${classification}`;
    const response = await fetch(url);
    if (!response.ok) throw new Error('Failed to fetch inspections');
    return await response.json();
  } catch (error) {
    console.error('getInspections error:', error);
    return { count: 0, inspections: [] };
  }
}

export async function getLatestInspection() {
  try {
    const response = await fetch(`${API_BASE_URL}/api/inspections/latest`);
    if (!response.ok) throw new Error('No inspections available');
    return await response.json();
  } catch (error) {
    console.error('getLatestInspection error:', error);
    return null;
  }
}

export async function getAnalytics(period = 'today') {
  try {
    const response = await fetch(`${API_BASE_URL}/api/analytics?period=${period}`);
    if (!response.ok) throw new Error('Failed to fetch analytics');
    return await response.json();
  } catch (error) {
    console.error('getAnalytics error:', error);
    return null;
  }
}

export async function getDefectDistribution() {
  try {
    const response = await fetch(`${API_BASE_URL}/api/analytics/defect-distribution`);
    if (!response.ok) throw new Error('Failed to fetch defect distribution');
    return await response.json();
  } catch (error) {
    console.error('getDefectDistribution error:', error);
    return { defects: [] };
  }
}

export async function getTimeline(period = 'today') {
  try {
    const response = await fetch(`${API_BASE_URL}/api/analytics/timeline?period=${period}`);
    if (!response.ok) throw new Error('Failed to fetch timeline');
    return await response.json();
  } catch (error) {
    console.error('getTimeline error:', error);
    return { timeline: [] };
  }
}

export function getInspectionImageUrl(inspectionId) {
  return `${API_BASE_URL}/api/inspections/${inspectionId}/image`;
}

let socket = null;

export function connectWebSocket(handlers = {}) {
  if (socket && socket.connected) return socket;

  socket = io(WS_URL, {
    transports: ['websocket'],
    reconnection: true,
    reconnectionAttempts: 10,
    reconnectionDelay: 2000,
  });

  socket.on('connect', () => {
    console.log('WebSocket connected');
    handlers.onConnect?.();
  });

  socket.on('disconnect', () => {
    console.log('WebSocket disconnected');
    handlers.onDisconnect?.();
  });

  socket.on('new_inspection', (data) => {
    handlers.onNewInspection?.(data);
  });

  socket.on('status_update', (data) => {
    handlers.onStatusUpdate?.(data);
  });

  socket.on('connect_error', (error) => {
    console.error('WebSocket error:', error.message);
  });

  return socket;
}

export function disconnectWebSocket() {
  if (socket) {
    socket.disconnect();
    socket = null;
  }
}

export function isWebSocketConnected() {
  return !!(socket && socket.connected);
}