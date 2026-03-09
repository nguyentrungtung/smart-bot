export function MessageList({ messages }) {
    return (
        <div className="message-list">
            {messages.length === 0 && (
                <div className="message bot">
                    Xin chào! Tôi là Smart-Bot. Tôi có thể giúp gì cho bạn hôm nay?
                </div>
            )}
            {messages.map((msg, i) => (
                <div key={i} className={`message ${msg.sender}`}>
                    {msg.text}
                </div>
            ))}
        </div>
    );
}
