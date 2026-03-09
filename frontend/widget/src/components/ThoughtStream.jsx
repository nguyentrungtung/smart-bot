import { useState } from 'preact/hooks';
import { ChevronDown, ChevronUp, BrainCircuit } from 'lucide-preact';

export function ThoughtStream({ thoughts }) {
    const [isExpanded, setIsExpanded] = useState(false);

    if (!thoughts || thoughts.length === 0) return null;

    return (
        <div className="thought-container bot" style={{ marginBottom: '1rem' }}>
            <div
                className="thought-header"
                onClick={() => setIsExpanded(!isExpanded)}
                style={{
                    display: 'flex',
                    alignSelf: 'flex-start',
                    alignItems: 'center',
                    gap: '0.5rem',
                    padding: '0.5rem 0.75rem',
                    background: 'rgba(99, 102, 241, 0.1)',
                    borderRadius: 'var(--radius-md)',
                    cursor: 'pointer',
                    fontSize: '0.8125rem',
                    color: 'var(--primary)',
                    border: '1px solid rgba(99, 102, 241, 0.2)',
                    transition: 'var(--transition)'
                }}
            >
                <BrainCircuit size={16} />
                <span style={{ fontWeight: 600 }}>Tiến trình suy nghĩ</span>
                {isExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
            </div>

            {isExpanded && (
                <div
                    className="thought-content"
                    style={{
                        marginTop: '0.5rem',
                        padding: '0.75rem',
                        background: 'rgba(15, 23, 42, 0.4)',
                        borderRadius: 'var(--radius-md)',
                        fontSize: '0.8125rem',
                        color: 'var(--text-muted)',
                        lineHeight: '1.4',
                        borderLeft: '2px solid var(--primary)',
                        animation: 'fadeIn 0.3s ease'
                    }}
                >
                    {thoughts.map((t, i) => (
                        <div key={i} style={{ marginBottom: i < thoughts.length - 1 ? '0.5rem' : 0 }}>
                            {t}
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}
