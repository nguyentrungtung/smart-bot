import { useRef, useState, useEffect } from 'preact/hooks';
import { Send, Image as ImageIcon, Mic, X, StopCircle } from 'lucide-preact';

export function InputArea({ onSendMessage, msgInProgress }) {
    const textareaRef = useRef();
    const fileInputRef = useRef();
    const [isRecording, setIsRecording] = useState(false);
    const [selectedImage, setSelectedImage] = useState(null);
    const [mediaRecorder, setMediaRecorder] = useState(null);

    const handleSend = () => {
        const text = textareaRef.current.value.trim();
        if (text || selectedImage) {
            onSendMessage(text, { image: selectedImage });
            textareaRef.current.value = '';
            setSelectedImage(null);
        }
    };

    const handleKeyDown = (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSend();
        }
    };

    const handleImageSelect = (e) => {
        const file = e.target.files[0];
        if (file) {
            if (file.size > 5 * 1024 * 1024) {
                alert("File quá lớn. Vui lòng chọn ảnh dưới 5MB.");
                return;
            }
            const reader = new FileReader();
            reader.onloadend = () => {
                setSelectedImage(reader.result);
            };
            reader.readAsDataURL(file);
        }
    };

    const startRecording = async () => {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            const recorder = new MediaRecorder(stream);
            const chunks = [];

            recorder.ondataavailable = (e) => chunks.push(e.data);
            recorder.onstop = () => {
                const blob = new Blob(chunks, { type: 'audio/webm' });
                onSendMessage('', { audio: blob });
                stream.getTracks().forEach(track => track.stop());
            };

            recorder.start();
            setMediaRecorder(recorder);
            setIsRecording(true);
        } catch (err) {
            console.error("Microphone access denied:", err);
            alert("Không thể truy cập Microphone.");
        }
    };

    const stopRecording = () => {
        if (mediaRecorder) {
            mediaRecorder.stop();
            setIsRecording(false);
        }
    };

    return (
        <div className="input-container">
            {selectedImage && (
                <div className="image-preview" style={{ padding: '0.5rem', display: 'flex', gap: '0.5rem' }}>
                    <div style={{ position: 'relative' }}>
                        <img src={selectedImage} style={{ width: '60px', height: '60px', borderRadius: '8px', objectFit: 'cover' }} />
                        <button
                            onClick={() => setSelectedImage(null)}
                            style={{ position: 'absolute', top: '-5px', right: '-5px', background: 'red', color: 'white', border: 'none', borderRadius: '50%', width: '20px', height: '20px', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyCenter: 'center' }}
                        >
                            <X size={12} />
                        </button>
                    </div>
                </div>
            )}

            <div className="input-area">
                <input
                    type="file"
                    ref={fileInputRef}
                    style={{ display: 'none' }}
                    accept="image/*"
                    onChange={handleImageSelect}
                />

                <button
                    className={`icon-btn ${selectedImage ? 'primary' : ''}`}
                    onClick={() => fileInputRef.current.click()}
                    title="Tải ảnh"
                >
                    <ImageIcon size={20} />
                </button>

                <button
                    className={`icon-btn ${isRecording ? 'recording' : ''}`}
                    onClick={isRecording ? stopRecording : startRecording}
                    title={isRecording ? "Dừng ghi" : "Ghi âm"}
                    style={isRecording ? { color: '#ef4444' } : {}}
                >
                    {isRecording ? <StopCircle size={20} className="pulse" /> : <Mic size={20} />}
                </button>

                <textarea
                    ref={textareaRef}
                    placeholder={isRecording ? "Đang ghi âm..." : "Nhập tin nhắn..."}
                    onKeyDown={handleKeyDown}
                    disabled={msgInProgress || isRecording}
                    rows={1}
                />

                <button
                    className="icon-btn primary"
                    onClick={handleSend}
                    disabled={msgInProgress || isRecording}
                    title="Gửi"
                >
                    <Send size={20} />
                </button>
            </div>

            <style dangerouslySetInnerHTML={{
                __html: `
        .recording { animation: pulse 1.5s infinite; }
        @keyframes pulse {
          0% { transform: scale(1); opacity: 1; }
          50% { transform: scale(1.1); opacity: 0.7; }
          100% { transform: scale(1); opacity: 1; }
        }
      `}} />
        </div>
    );
}
