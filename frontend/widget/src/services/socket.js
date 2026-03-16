import { io } from "socket.io-client";

class SocketService {
    constructor() {
        this.socket = null;
        this.handlers = new Map();
        this.accessToken = localStorage.getItem("sb_access_token");
        this.refreshToken = localStorage.getItem("sb_refresh_token");
    }

    setTokens(access, refresh) {
        this.accessToken = access;
        if (refresh) this.refreshToken = refresh;
        localStorage.setItem("sb_access_token", access);
        if (refresh) localStorage.setItem("sb_refresh_token", refresh);
    }

    clearTokens() {
        this.accessToken = null;
        this.refreshToken = null;
        localStorage.removeItem("sb_access_token");
        localStorage.removeItem("sb_refresh_token");
    }

    async refresh() {
        if (!this.refreshToken) {
            console.warn("No refresh token available");
            this.clearTokens();
            return false;
        }

        const url = import.meta.env.VITE_BACKEND_URL || "http://localhost:8000";
        try {
            const response = await fetch(`${url}/api/v1/auth/refresh`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ refresh_token: this.refreshToken })
            });

            if (response.status === 200) {
                const data = await response.json();
                this.setTokens(data.access_token);
                console.log("Access token refreshed successfully");
                return true;
            } else if (response.status === 401 || response.status === 403) {
                console.error("Refresh token expired or invalid (401/403)");
                this.clearTokens();
                return false;
            } else {
                console.error("Unexpected error during refresh:", response.status);
                this.clearTokens();
                return false;
            }
        } catch (err) {
            console.error("Failed to call refresh endpoint:", err);
            this.clearTokens();
            return false;
        }
    }

    connect(token = null) {
        if (token) {
            this.setTokens(token);
        }

        if (this.socket) return;

        const url = import.meta.env.VITE_BACKEND_URL || "http://localhost:8000";

        this.socket = io(url, {
            auth: { token: this.accessToken },
            reconnection: true,
            reconnectionAttempts: 3,
            reconnectionDelay: 1000,
        });

        this.socket.on("connect", () => {
            console.log("Connected to Smart-Bot Backend");
        });

        this.socket.on("connect_error", async (err) => {
            console.error("Socket Connection Error:", err.message);

            // If the error looks like a token issue, try refresh
            if (err.message.includes("Expired") || err.message.includes("Invalid") || err.message.includes("rejected")) {
                console.log("Attempting token refresh...");
                this.disconnect();
                const success = await this.refresh();
                if (success) {
                    this.connect(); // Retry with new token
                } else {
                    // Notify UI that login is required
                    if (this.onAuthFailure) this.onAuthFailure();
                }
            }
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
