const PI_IP_ADDRESS = '192.168.100.114';

export const API_BASE_URL = `http://${PI_IP_ADDRESS}:5000`;
export const STREAM_URL = `http://${PI_IP_ADDRESS}:5001`;
export const VIDEO_FEED_URL = `http://${PI_IP_ADDRESS}:5001/video_feed`;
export const SNAPSHOT_URL = `http://${PI_IP_ADDRESS}:5001/api/stream/snapshot`;
export const WS_URL = `http://${PI_IP_ADDRESS}:5000`;

export default {
  API_BASE_URL,
  STREAM_URL,
  VIDEO_FEED_URL,
  SNAPSHOT_URL,
  WS_URL,
  PI_IP_ADDRESS,
};