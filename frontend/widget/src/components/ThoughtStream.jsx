import { useState, useEffect, useRef } from 'preact/hooks';
import { ChevronDown, ChevronUp, BrainCircuit } from 'lucide-preact';
import { marked } from 'marked';

marked.setOptions({ breaks: true, gfm: true });

function renderMarkdown(text) {
    try {
        return { __html: marked.parse(text) };
    } catch {
        return { __html: text };
    }
}

export function ThoughtStream({ thought }) {
    const [isExpanded, setIsExpanded] = useState(false);
    const [seconds, setSeconds] = useState(0);
    const timerRef = useRef(null);
    const contentRef = useRef(null);

    // Auto-expand when first thought content arrives
    useEffect(() => {
        if (thought && !isExpanded) {
            setIsExpanded(true);
        }
    }, [!!thought]);

    // Timer: start counting when thought content appears, stop when cleared
    useEffect(() => {
        if (thought && !timerRef.current) {
            setSeconds(0);
            timerRef.current = setInterval(() => {
                setSeconds(prev => +(prev + 0.1).toFixed(1));
            }, 100);
        }
        if (!thought && timerRef.current) {
            clearInterval(timerRef.current);
            timerRef.current = null;
        }
        return () => {
            if (timerRef.current) {
                clearInterval(timerRef.current);
                timerRef.current = null;
            }
        };
    }, [!!thought]);

    // Auto-scroll the thought content to bottom as new tokens arrive
    useEffect(() => {
        if (contentRef.current && isExpanded) {
            contentRef.current.scrollTop = contentRef.current.scrollHeight;
        }
    }, [thought, isExpanded]);

    if (!thought) return null;

    return (
        <div className="thought-container bot" style={{ marginBottom: '0.5rem', padding: '0 1rem' }}>
            <div
                className="thought-header"
                onClick={() => setIsExpanded(!isExpanded)}
            >
                <BrainCircuit size={14} />
                <span style={{ fontWeight: 600, flex: 1 }}>
                    🧠 Smart-bot đang thinking... {seconds > 0 ? `(${seconds}s)` : ''}
                </span>
                {isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            </div>

            {isExpanded && (
                <div
                    ref={contentRef}
                    className="thought-content"
                    dangerouslySetInnerHTML={renderMarkdown(thought)}
                />
            )}
        </div>
    );
}
