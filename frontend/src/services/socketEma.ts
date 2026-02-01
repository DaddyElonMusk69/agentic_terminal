import type { Socket } from "socket.io-client";
import { createSocket } from "@/services/socketBase";

export const createEmaSocket = () => {
  let socket: Socket | null = null;

  const connect = (exchangeId?: string) => {
    if (socket) return socket;
    socket = createSocket({ exchangeId, path: "/realtime" });
    return socket;
  };

  const disconnect = () => {
    if (socket) {
      socket.disconnect();
      socket = null;
    }
  };

  const getSocket = () => socket;

  return { connect, disconnect, getSocket };
};
