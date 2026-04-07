import { useEffect, useRef, useState } from 'preact/hooks';
import { marked } from 'marked';
import { ChevronDown, ChevronUp, BrainCircuit, ThumbsUp, ThumbsDown } from 'lucide-preact';

// Configure marked
marked.setOptions({ breaks: true, gfm: true });

function renderMarkdown(text) {
    try {
        return { __html: marked.parse(text) };
    } catch {
        return { __html: text };
    }
}

function SavedThinking({ thinking, thinkingTime }) {
    const [isExpanded, setIsExpanded] = useState(false);
    if (!thinking) return null;

    return (
        <div className="saved-thinking" style={{ marginBottom: '0.5rem' }}>
            <div
                className="thought-header"
                onClick={() => setIsExpanded(!isExpanded)}
            >
                <BrainCircuit size={14} />
                <span style={{ fontWeight: 600, flex: 1 }}>
                    💭 Đã suy nghĩ
                </span>
                {isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            </div>

            {isExpanded && (
                <div
                    className="thought-content"
                    dangerouslySetInnerHTML={renderMarkdown(thinking)}
                />
            )}
        </div>
    );
}

export function MessageList({ messages, partialResponse, onRate }) {
    const listRef = useRef();

    useEffect(() => {
        if (listRef.current) {
            listRef.current.scrollTo({
                top: listRef.current.scrollHeight,
                behavior: 'smooth'
            });
        }
    }, [messages, partialResponse]);


    return (
        <div className="message-list" ref={listRef}>
            {messages.length === 0 && (
                <div className="message bot">
                    Xin chào! Em là SmartSales Assistant, trợ lý bán hàng AI. Anh/chị cần em hỗ trợ gì ạ?
                </div>
            )}
            {messages.map((msg, i) => (
                <div key={i} className={`message-group ${msg.sender}`}>
                    {msg.sender === 'bot' && msg.thinking && (
                        <SavedThinking thinking={msg.thinking} />
                    )}
                    <div className={`message ${msg.sender}`}>
                        {msg.attachments?.image && (
                            <img
                                src={msg.attachments.image}
                                style={{ maxWidth: '100%', borderRadius: '8px', marginBottom: '0.5rem', display: 'block' }}
                            />
                        )}
                        {msg.sender === 'bot' ? (
                            <div className="bot-message-wrapper">
                                <div dangerouslySetInnerHTML={renderMarkdown(msg.text)} />
                                {msg.interaction_id && (
                                    <div className="message-actions" style={{ display: 'flex', gap: '8px', marginTop: '8px', justifyContent: 'flex-end' }}>
                                        <button
                                            className={`rate-btn ${msg.rated === 'good' ? 'active' : ''}`}
                                            onClick={() => onRate(msg.interaction_id, 'good')}
                                            disabled={!!msg.rated}
                                            style={{ background: 'none', border: 'none', cursor: 'pointer', opacity: msg.rated === 'bad' ? 0.3 : 1 }}
                                            title="Tốt"
                                        >
                                            <ThumbsUp size={14} color={msg.rated === 'good' ? '#22c55e' : '#64748b'} />
                                        </button>
                                        <button
                                            className={`rate-btn ${msg.rated === 'bad' ? 'active' : ''}`}
                                            onClick={() => onRate(msg.interaction_id, 'bad')}
                                            disabled={!!msg.rated}
                                            style={{ background: 'none', border: 'none', cursor: 'pointer', opacity: msg.rated === 'good' ? 0.3 : 1 }}
                                            title="Chưa tốt"
                                        >
                                            <ThumbsDown size={14} color={msg.rated === 'bad' ? '#ef4444' : '#64748b'} />
                                        </button>
                                    </div>
                                )}
                            </div>
                        ) : (
                            <div className="user-message-content">
                                <div>
                                    {msg.text}
                                </div>
                                {msg.localAudioUrl && (
                                    <div style={{ marginTop: '6px' }}>
                                        <audio 
                                            src={msg.localAudioUrl} 
                                            controls 
                                            controlsList="nodownload noplaybackrate" 
                                            style={{ height: '36px', maxWidth: '240px', borderRadius: '4px' }} 
                                        />
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                </div>
            ))}
            {partialResponse && (
                <div className="message bot streaming"
                    dangerouslySetInnerHTML={renderMarkdown(partialResponse)}
                />
            )}
        </div>


    );
}
