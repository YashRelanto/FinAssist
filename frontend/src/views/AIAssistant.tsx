import React, { useState, useRef, useEffect } from 'react';
import { Send, User, Bot, Loader2 } from 'lucide-react';
import { cn } from '../lib/utils';
import { useAppContext } from '../context/AppContext';
import { getOrCreateChatThreadId, sendChatMessage } from '../lib/api';
import { loadChatSession, saveChatSession, type StoredChatMessage } from '../lib/chatSession';

type ChatMessage = StoredChatMessage;

const initialMessages: ChatMessage[] = [
  {
    id: 1,
    role: 'ai',
    time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    text: "Hello! I am your FinAssist AI Advisor. I have access to your transactions and our latest financial knowledge base. How can I help you today?",
    type: 'text',
  },
];

export const AIAssistant: React.FC = () => {
  const { user } = useAppContext();
  const userId = user.userId || 'guest-user';
  const [threadId] = useState(() => getOrCreateChatThreadId());
  const [messages, setMessages] = useState<ChatMessage[]>(() => {
    return loadChatSession(userId, threadId) ?? initialMessages;
  });
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    saveChatSession(userId, threadId, messages);
  }, [messages, userId, threadId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  const handleSendMessage = async (text: string) => {
    if (!text.trim() || isLoading) return;

    const userMessage: ChatMessage = {
      id: Date.now(),
      role: 'user',
      time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      text: text.trim(),
      type: 'text',
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);

    try {
      const data = await sendChatMessage(userId, text.trim(), threadId);

      const aiMessage: ChatMessage = {
        id: Date.now() + 1,
        role: 'ai',
        time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        text: data.answer || "I didn't quite catch that.",
        type: 'text',
        intent: data.intent,
        sources: data.sources?.length ? data.sources : undefined,
        clarificationOptions: data.needs_clarification ? data.clarification_options : undefined,
      };

      setMessages((prev) => [...prev, aiMessage]);
    } catch (error) {
      console.error('Chat API error:', error);
      setMessages((prev) => [
        ...prev,
        {
          id: Date.now() + 1,
          role: 'ai',
          time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          text: "I'm sorry, I couldn't connect to the backend server. Please make sure the FastAPI server is running.",
          type: 'text',
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage(input);
    }
  };

  return (
    <div className="h-[calc(100vh-140px)]">
      <section className="h-full flex flex-col bg-surface-container-lowest border border-outline-variant/30 rounded-2xl shadow-sm overflow-hidden relative">
        <div className="flex-1 overflow-y-auto p-10 space-y-10 scrollbar-hide pb-32">
          {messages.map((m) => (
            <div
              key={m.id}
              className={cn(
                'flex gap-4 max-w-2xl',
                m.role === 'user' ? 'ml-auto flex-row-reverse text-right' : ''
              )}
            >
              <div
                className={cn(
                  'w-10 h-10 rounded-full flex items-center justify-center shrink-0 shadow-sm',
                  m.role === 'user' ? 'bg-surface-container-high' : 'bg-primary-container text-white'
                )}
              >
                {m.role === 'user' ? <User size={18} /> : <Bot size={18} />}
              </div>
              <div className="space-y-2">
                <div
                  className={cn(
                    'px-5 py-3 rounded-2xl text-sm leading-relaxed',
                    m.role === 'user'
                      ? 'bg-primary text-white rounded-tr-sm'
                      : 'bg-surface-container-low border border-outline-variant/20 rounded-tl-sm'
                  )}
                >
                  <p className="whitespace-pre-wrap">{m.text}</p>
                </div>
                {m.role === 'ai' && m.intent && (
                  <span className="text-[10px] uppercase tracking-wider text-on-surface-variant/60 px-1">
                    {m.intent.replace(/_/g, ' ')}
                  </span>
                )}
                {m.role === 'ai' && m.sources && m.sources.length > 0 && (
                  <p className="text-xs text-on-surface-variant/70 px-1">
                    Sources: {m.sources.join(', ')}
                  </p>
                )}
                {m.role === 'ai' && m.clarificationOptions && m.clarificationOptions.length > 0 && (
                  <div className="flex flex-wrap gap-2 pt-1">
                    {m.clarificationOptions.map((opt) => (
                      <button
                        key={opt}
                        type="button"
                        onClick={() => handleSendMessage(opt)}
                        className="text-xs px-3 py-1.5 rounded-full border border-primary/30 text-primary hover:bg-primary/10 transition-colors"
                      >
                        {opt}
                      </button>
                    ))}
                  </div>
                )}
                <span className="text-[10px] text-on-surface-variant/50 px-1 block">{m.time}</span>
              </div>
            </div>
          ))}
          {isLoading && (
            <div className="flex gap-4 max-w-2xl">
              <div className="w-10 h-10 rounded-full bg-primary-container text-white flex items-center justify-center">
                <Loader2 size={18} className="animate-spin" />
              </div>
              <div className="px-5 py-3 rounded-2xl bg-surface-container-low border border-outline-variant/20 text-sm text-on-surface-variant">
                Thinking...
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        <div className="absolute bottom-0 left-0 right-0 p-6 bg-gradient-to-t from-surface-container-lowest via-surface-container-lowest to-transparent">
          <div className="flex items-center gap-3 bg-surface-container-low border border-outline-variant/30 rounded-2xl px-4 py-2 shadow-lg">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyPress}
              placeholder="Ask about spending, investments, or financial planning..."
              className="flex-1 bg-transparent border-none outline-none text-sm py-2"
              disabled={isLoading}
            />
            <button
              type="button"
              onClick={() => handleSendMessage(input)}
              disabled={isLoading || !input.trim()}
              className="p-2 rounded-xl bg-primary text-white disabled:opacity-40 hover:bg-primary/90 transition-colors"
            >
              <Send size={18} />
            </button>
          </div>
        </div>
      </section>
    </div>
  );
};
