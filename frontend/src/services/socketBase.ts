import { io, type Socket } from "socket.io-client";

const resolveSocketBase = () => {
  if (import.meta.env.VITE_SOCKET_BASE) {
    return import.meta.env.VITE_SOCKET_BASE as string;
  }
  if (typeof window !== "undefined") {
    return window.location.origin;
  }
  return "http://127.0.0.1:5000";
};

type SocketConfig = {
  exchangeId?: string;
  path?: string;
};

export const createSocket = (config: SocketConfig = {}): Socket => {
  const base = resolveSocketBase();
  const options: { query?: Record<string, string>; path?: string } = {};
  if (config.exchangeId) {
    options.query = { exchange: config.exchangeId };
  }
  if (config.path) {
    options.path = config.path;
  }
  return Object.keys(options).length ? io(base, options) : io(base);
};
