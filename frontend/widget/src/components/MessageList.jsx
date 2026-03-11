import { useEffect, useRef, useState } from 'preact/hooks';
import { marked } from 'marked';
import { ChevronDown, ChevronUp, BrainCircuit } from 'lucide-preact';

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

export function MessageList({ messages, partialResponse }) {
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
                            <div dangerouslySetInnerHTML={renderMarkdown(msg.text)} />
                        ) : (
                            msg.text
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
