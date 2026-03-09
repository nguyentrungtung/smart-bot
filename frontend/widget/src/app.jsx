import { useState, useEffect } from 'preact/hooks';
import { MessageCircle, X } from 'lucide-preact';
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
  const [currentThoughts, setCurrentThoughts] = useState([]);

  useEffect(() => {
    // 1. Start reporting height to parent for dynamic resize
    iframeSync.startResizing();

    // 2. Listen for auth tokens from parent site
    iframeSync.listenForEvents((type, payload) => {
      if (type === "auth") {
        console.log("Received JWT Auth via postMessage");
        socketService.connect(payload);
      }
    });

    // 3. Fallback for local development if no postMessage is sent
    const mockToken = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.e30.dummy";
    setTimeout(() => {
      if (!socketService.socket) {
        socketService.connect(mockToken);
      }
    }, 1000);

    socketService.on("message", (data) => {
      setMessages((prev) => [...prev, { sender: 'bot', text: data.content }]);
      setLoading(false);
      setCurrentThoughts([]); // Clear thoughts when final message arrives
    });

    socketService.on("thinking", (data) => {
      setCurrentThoughts((prev) => [...prev, data.content]);
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

  const handleSendMessage = (text, attachments = {}) => {
    const userMsg = {
      sender: 'user',
      text: text || (attachments.audio ? "🎤 Audio message" : "📸 Image message"),
      attachments
    };

    setMessages((prev) => [...prev, userMsg]);
    setLoading(true);

    const payload = {
      session_id: "test-session-123",
      content: text,
      ...attachments
    };

    socketService.emit("message", payload);
  };


  const toggleWidget = () => setIsOpen(!isOpen);

  return (
    <div className="widget-container">
      {isOpen && (
        <div className="chat-window">
          <div className="chat-header">
            <div className="status-dot"></div>
            <h2>Smart-Bot Advisor</h2>
            <button
              className="icon-btn"
              style={{ marginLeft: 'auto' }}
              onClick={toggleWidget}
            >
              <X size={20} />
            </button>
          </div>

          <MessageList messages={messages} />
          <ThoughtStream thoughts={currentThoughts} />

          <InputArea
            onSendMessage={handleSendMessage}
            msgInProgress={loading}
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
