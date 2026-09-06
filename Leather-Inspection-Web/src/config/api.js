const DEFAULT_PI_IP_ADDRESS = '192.168.100.114';
const DEFAULT_API_PORT = 5000;
const DEFAULT_STREAM_PORT = 5001;

function normalizeBaseUrl(value, fallbackPort) {
  if (!value || typeof value !== 'string') return null;

  const trimmed = value.trim();
  if (!trimmed) return null;

  const withProtocol = /^https?:\/\//i.test(trimmed) ? trimmed : `http://${trimmed}`;

  try {
    const url = new URL(withProtocol);
    if (fallbackPort && !url.port) url.port = String(fallbackPort);
    url.pathname = '';
    url.search = '';
    url.hash = '';
    return url.toString().replace(/\/+$/, '');
  } catch {
    return null;
  }
}

const piIpAddress = import.meta.env.VITE_PI_IP_ADDRESS || DEFAULT_PI_IP_ADDRESS;
const apiBaseOverride = import.meta.env.VITE_API_BASE_URL;
const streamOverride = import.meta.env.VITE_STREAM_URL;

export const API_BASE_URL = normalizeBaseUrl(apiBaseOverride, DEFAULT_API_PORT) || normalizeBaseUrl(piIpAddress, DEFAULT_API_PORT);
export const STREAM_URL = normalizeBaseUrl(streamOverride, DEFAULT_STREAM_PORT) || normalizeBaseUrl(piIpAddress, DEFAULT_STREAM_PORT);
export const WS_URL = normalizeBaseUrl(import.meta.env.VITE_WS_URL, DEFAULT_API_PORT) || API_BASE_URL;
export const VIDEO_FEED_URL = import.meta.env.VITE_VIDEO_FEED_URL || `${STREAM_URL}/video_feed`;
