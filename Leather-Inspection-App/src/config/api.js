const HOST_IP_ADDRESS = '192.168.100.114';

export const API_BASE_URL = `http://${HOST_IP_ADDRESS}:5000`;
export const STREAM_URL = `http://${HOST_IP_ADDRESS}:5000`;
export const VIDEO_FEED_URL = `http://${HOST_IP_ADDRESS}:5000/video_feed`;
export const SNAPSHOT_URL = `http://${HOST_IP_ADDRESS}:5000/api/stream/snapshot`;
export const WS_URL = `http://${HOST_IP_ADDRESS}:5000`;

export default {
  API_BASE_URL,
  STREAM_URL,
  VIDEO_FEED_URL,
  SNAPSHOT_URL,
  WS_URL,
  HOST_IP_ADDRESS,
};