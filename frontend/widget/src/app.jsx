import { useState, useEffect, useRef } from 'preact/hooks';

import { MessageCircle, X, Maximize2, Minimize2, RefreshCcw } from 'lucide-preact';
import { socketService } from './services/socket';
import { iframeSync } from './services/iframeSync';
import { MessageList } from './components/MessageList';
import { InputArea } from './components/InputArea';
import { ThoughtStream } from './components/ThoughtStream';
import './app.css';

export function App() {
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [currentThought, setCurrentThought] = useState("");
  const [partialResponse, setPartialResponse] = useState("");
  const partialRef = useRef(""); // Latest value for the complete callback
  const thoughtRef = useRef(""); // Accumulates thought chunks as one string
  const [pendingMetadata, setPendingMetadata] = useState(null);
  const metadataRef = useRef(null);



  const [session_id, setSessionId] = useState(() => {
    const saved = localStorage.getItem("smart_bot_session_id");
    return saved || null; // Return null initially if missing, fetch it below
  });

  const [authError, setAuthError] = useState(false);
  const [capabilities, setCapabilities] = useState({ vision: false, audio: false });

  useEffect(() => {
    // 1. Start reporting height to parent for dynamic resize
    iframeSync.startResizing();

    // 2. Setup Auth Error handling
    socketService.onAuthFailure = () => {
      setAuthError(true);
      setMessages((prev) => [...prev, {
        sender: 'bot',
        text: "⚠️ Session expired. Please refresh the page or login again from the main site."
      }]);
    };

    // 3. Listen for auth tokens from parent site
    iframeSync.listenForEvents((type, payload) => {
      if (type === "auth") {
        console.log("Received JWT Auth via postMessage");
        setAuthError(false);
        socketService.connect(payload);
      }
    });

    // 4. Standalone/First-load Auto Login & Strict Session Check
    const initializeAuthAndSession = async () => {
      const url = import.meta.env.VITE_BACKEND_URL || "http://localhost:8000";
      try {
        let isConnected = false;

        // Try auto-login if no token
        if (!socketService.accessToken) {
          const response = await fetch(`${url}/api/v1/auth/login`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ user_id: "guest-" + Math.random().toString(36).substring(7) })
          });
          if (response.ok) {
            const data = await response.json();
            console.log("Acquired Guest Token for development");
            socketService.setTokens(data.access_token, data.refresh_token);
            socketService.connect();
            isConnected = true;
          } else if (response.status === 401 || response.status === 403) {
            console.warn("Guest login restricted (security enforced)");
            setAuthError(true);
            socketService.clearTokens();
          }
        } else {
          socketService.connect();
          isConnected = true;
        }

        // Enforce Strict Server-side Session
        if (isConnected && !session_id) {
          console.log("No session found. Requesting explicit new session from Backend...");
          const sessionResp = await fetch(`${url}/api/v1/chat/new-session`, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "Authorization": `Bearer ${socketService.accessToken}`
            }
          });
          if (sessionResp.ok) {
            const sData = await sessionResp.json();
            setSessionId(sData.session_id);
            localStorage.setItem("smart_bot_session_id", sData.session_id);
            console.log("Strict Session acquired:", sData.session_id);
          }
        }
      } catch (err) {
        console.error("Initialization failed:", err);
      }
    };

    initializeAuthAndSession();

    socketService.on("message_stream", (data) => {
      console.log("FE Debug: Received message_stream chunk:", data.chunk);
      partialRef.current += data.chunk;
      setPartialResponse(partialRef.current);
      setLoading(false);
    });

    socketService.on("thought_stream", (data) => {
      console.log("FE Debug: Received thought_stream:", data.content);
      thoughtRef.current += data.content;
      setCurrentThought(thoughtRef.current);
      setLoading(false);
    });

    socketService.on("message_complete", () => {
      console.log("FE Debug: Stream complete. Finalizing message:", partialRef.current);
      if (partialRef.current || thoughtRef.current) {
        const finalContent = partialRef.current;
        const finalThinking = thoughtRef.current;
        const interaction_id = metadataRef.current?.interaction_id || null;

        setMessages((prev) => [...prev, {
          sender: 'bot',
          text: finalContent,
          thinking: finalThinking || null,
          interaction_id: interaction_id,
          rated: null
        }]);
      }
      partialRef.current = "";
      thoughtRef.current = "";
      setPartialResponse("");
      setLoading(false);
      setCurrentThought("");
      setPendingMetadata(null);
      metadataRef.current = null;
    });

    socketService.on("message_metadata", (data) => {
      console.log("FE Debug: Received message_metadata:", data);
      setPendingMetadata(data);
      metadataRef.current = data;
    });

    // Listen for multimodal capabilities from backend
    socketService.on("multimodal_config", (config) => {
      console.log("FE Debug: Received multimodal_config:", config);
      setCapabilities(config);
    });

    // Handle incoming audio for TTS
    socketService.on("audio_chunk", (data) => {
      const blob = new Blob([data.buffer], { type: 'audio/mp3' });
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      audio.play().catch(e => console.error("TTS Playback failed:", e));
    });


    return () => socketService.disconnect();
  }, []);

  // Helper: convert Blob to base64 data URL
  const blobToBase64 = (blob) => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onloadend = () => resolve(reader.result);
      reader.onerror = reject;
      reader.readAsDataURL(blob);
    });
  };

  const handleSendMessage = async (text, attachments = {}) => {
    const userMsg = {
      sender: 'user',
      text: text || (attachments.audio ? "🎤 Audio message" : "📸 Image message"),
      attachments
    };

    setMessages((prev) => [...prev, userMsg]);
    setLoading(true);

    // Build payload with proper format for backend
    const payload = {
      session_id,
      content: text,
    };

    // Add image as data URL string (already base64 from FileReader)
    if (attachments.image) {
      payload.image = attachments.image;
      console.log("FE Debug: Attaching image to payload, length:", attachments.image.length);
    }

    // Convert audio Blob to base64 data URL before sending
    if (attachments.audio && attachments.audio instanceof Blob) {
      try {
        const audioBase64 = await blobToBase64(attachments.audio);
        payload.audio = audioBase64;
        console.log("FE Debug: Converted audio Blob to base64, length:", audioBase64.length);
      } catch (err) {
        console.error("FE Error: Failed to convert audio Blob:", err);
      }
    }

    if (!session_id) {
      console.warn("FE Debug: Attempted to send message without session_id. Re-initializing...");
      // Try to re-initialize session if it's missing
      const url = import.meta.env.VITE_BACKEND_URL || "http://localhost:8000";
      try {
        const sessionResp = await fetch(`${url}/api/v1/chat/new-session`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${socketService.accessToken}`
          }
        });
        if (sessionResp.ok) {
          const sData = await sessionResp.json();
          setSessionId(sData.session_id);
          localStorage.setItem("smart_bot_session_id", sData.session_id);
          payload.session_id = sData.session_id; // Update payload with new ID
          console.log("FE Debug: Emergency session acquired:", sData.session_id);
        } else {
          setMessages((prev) => [...prev, {
            sender: 'bot',
            text: "❌ Lỗi khởi tạo phiên làm việc. Vui lòng tải lại trang."
          }]);
          setLoading(false);
          return;
        }
      } catch (err) {
        console.error("FE Error: Emergency session failed:", err);
        setLoading(false);
        return;
      }
    }

    if (!socketService.socket?.connected) {
      setMessages((prev) => [...prev, {
        sender: 'bot',
        text: "🚫 Unable to send. Please refresh or authenticate again."
      }]);
      setLoading(false);
      return;
    }

    socketService.emit("message", payload);
  };

  const handleRateMessage = (interaction_id, rating) => {
    console.log(`FE Debug: Rating interaction ${interaction_id} as ${rating}`);
    socketService.emit("message_rate", { interaction_id, rating });

    // Update local state to show it was rated
    setMessages((prev) => prev.map(m =>
      m.interaction_id === interaction_id ? { ...m, rated: rating } : m
    ));
  };


  const handleNewSession = async () => {
    const url = import.meta.env.VITE_BACKEND_URL || "http://localhost:8000";
    try {
      const response = await fetch(`${url}/api/v1/chat/new-session`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${socketService.accessToken}`
        },
        body: JSON.stringify({ old_session_id: session_id })
      });
      if (response.ok) {
        const data = await response.json();
        console.log("Session reset success:", data.session_id);

        // 1. Update State & Storage
        setSessionId(data.session_id);
        localStorage.setItem("smart_bot_session_id", data.session_id);

        // 2. Clear Messages UI
        setMessages([{
          sender: 'bot',
          text: "✨ Cuộc hội thoại hoàn toàn mới đã được bắt đầu. Em có thể hỗ trợ gì cho anh/chị ạ?"
        }]);

        // 3. Reconnect socket with new thread awareness (though socket uses thread_id per message, 
        // a fresh connection ensures no stale state)
        socketService.disconnect();
        socketService.connect();
      }
    } catch (err) {
      console.error("Failed to reset session:", err);
    }
  };


  const [isMaximized, setIsMaximized] = useState(false);
  const [dimensions, setDimensions] = useState({ width: 400, height: 620 });
  const [isResizing, setIsResizing] = useState(false);

  useEffect(() => {
    const handleMouseMove = (e) => {
      if (!isResizing || isMaximized) return;

      // Since widget is bottom-right, we calculate width/height based on top-left drag
      // Find the parent distance from bottom right
      const rect = document.querySelector('.chat-window')?.getBoundingClientRect();
      if (!rect) return;

      const newWidth = Math.max(320, window.innerWidth - e.clientX - 32); // 32 is roughly the margin
      const newHeight = Math.max(400, window.innerHeight - e.clientY - 96);

      setDimensions({ width: newWidth, height: newHeight });
    };

    const handleMouseUp = () => setIsResizing(false);

    if (isResizing) {
      window.addEventListener('mousemove', handleMouseMove);
      window.addEventListener('mouseup', handleMouseUp);
    }
    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isResizing, isMaximized]);

  useEffect(() => {
    // Notify parent about new dimensions whenever states change
    const finalWidth = isMaximized ? 'calc(100vw - 4rem)' : `${dimensions.width}px`;
    const finalHeight = isMaximized ? 'calc(100vh - 8rem)' : `${dimensions.height}px`;
    iframeSync.reportResize(finalWidth, finalHeight);
  }, [isMaximized, dimensions]);

  const toggleMaximized = (e) => {
    e.stopPropagation();
    setIsMaximized(!isMaximized);
  };

  const toggleWidget = () => setIsOpen(!isOpen);
  return (
    <div className={`widget-container ${isMaximized ? 'maximized' : ''}`}>
      {isOpen && (
        <div
          className={`chat-window ${isMaximized ? 'maximized' : ''}`}
          style={!isMaximized ? { width: `${dimensions.width}px`, height: `${dimensions.height}px` } : {}}
        >
          {/* Resize Handle - Top Left Corner */}
          {!isMaximized && (
            <div
              className="resize-handle"
              onMouseDown={(e) => {
                e.preventDefault();
                setIsResizing(true);
              }}
            />
          )}

          <div className="chat-header">
            <div
              className={`status-dot ${authError ? 'error' : ''}`}
              title={authError ? "Authentication Required" : "Connected"}
            ></div>
            <h2>Smart-Bot Advisor</h2>
            <div style={{ marginLeft: 'auto', display: 'flex', gap: '0.25rem' }}>
              <button
                className="icon-btn"
                onClick={handleNewSession}
                title="New Conversation"
              >
                <RefreshCcw size={18} />
              </button>
              <button
                className="icon-btn"
                onClick={toggleMaximized}
                title={isMaximized ? "Restore" : "Maximize"}
              >
                {isMaximized ? <Minimize2 size={18} /> : <Maximize2 size={18} />}
              </button>
              <button
                className="icon-btn"
                onClick={toggleWidget}
                title="Close"
              >
                <X size={20} />
              </button>
            </div>
          </div>

          <MessageList
            messages={messages}
            partialResponse={partialResponse}
            onRate={handleRateMessage}
          />

          <ThoughtStream thought={currentThought} />


          <InputArea
            onSendMessage={handleSendMessage}
            msgInProgress={false}
            capabilities={capabilities}
          />

        </div>
      )}

      <div
        className={`chat-bubble ${isOpen ? 'active' : ''}`}
        onClick={toggleWidget}
      >
        {isOpen ? <X size={24} /> : <MessageCircle size={24} />}
      </div>
    </div>
  );
}
