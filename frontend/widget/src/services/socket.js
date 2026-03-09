import { io } from "socket.io-client";

class SocketService {
    constructor() {
        this.socket = null;
        this.handlers = new Map();
    }

    connect(token) {
        if (this.socket) return;

        // The backend URL is typically fixed or passed via config
        // For local dev, we assume port 8000
        const url = import.meta.env.VITE_BACKEND_URL || "http://localhost:8000";

        this.socket = io(url, {
            auth: { token },
            reconnection: true,
            reconnectionAttempts: 5,
            reconnectionDelay: 1000,
        });

        this.socket.on("connect", () => {
            console.log("Connected to Smart-Bot Backend");
        });

        this.socket.on("disconnect", (reason) => {
            console.warn("Disconnected:", reason);
        });

        this.socket.on("connect_error", (err) => {
            console.error("Connection Error:", err.message);
        });

        // Register any global handlers
        this.handlers.forEach((handler, event) => {
            this.socket.on(event, handler);
        });
    }

    on(event, handler) {
        this.handlers.set(event, handler);
        if (this.socket) {
            this.socket.on(event, handler);
        }
    }

    emit(event, data) {
        if (this.socket) {
            this.socket.emit(event, data);
        }
    }

    disconnect() {
        if (this.socket) {
            this.socket.disconnect();
            this.socket = null;
        }
    }
}

export const socketService = new SocketService();
