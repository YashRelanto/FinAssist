import React, { useState, useRef, useEffect } from 'react';
import { Send, User, Bot, Paperclip, Loader2 } from 'lucide-react';
import { cn, formatCurrency, APP_NAME, APP_ADVISOR_GREETING } from '../lib/utils';
import { useAppContext } from '../context/AppContext';
import { ChatChart } from '../components/ChatChart';
import { PageHeader, PageShell } from '../components/PageShell';
import { Markdown } from '../components/Markdown';
import { ClarificationCard } from '../components/ClarificationCard';
import type { ClarificationQuestion } from '../components/ClarificationCard';

interface Message {
  id: number;
  role: 'user' | 'ai';
  time: string;
  text: string;
  type: 'text' | 'clarification' | 'card';
  artifacts?: any[];
  clarificationQuestions?: ClarificationQuestion[];
  clarificationAnswered?: boolean;
  data?: any[];
}

const initialMessages = [
  { 
    id: 1, 
    role: 'ai', 
    time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }), 
    text: APP_ADVISOR_GREETING,
    type: 'text' 
  }
];

export const AIAssistant: React.FC = () => {
  const { user, chatMessages: messages, setChatMessages: setMessages } = useAppContext();
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  // Which message currently has an unanswered clarification card
  const [pendingClarificationId, setPendingClarificationId] = useState<number | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  const sendToApi = async (text: string) => {
    const response = await fetch('http://localhost:8000/api/chat/message', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: user.userId || 'guest-user',
        message: text,
        thread_id: 'default-thread',
      }),
    });
    if (!response.ok) throw new Error('API request failed');
    return response.json();
  };

  const handleSendMessage = async (text: string) => {
    if (!text.trim()) return;

    const userMessage: Message = {
      id: Date.now(),
      role: 'user',
      time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      text,
      type: 'text',
    };

    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);

    try {
      const data = await sendToApi(text);

      const isClarification = data.intent === 'clarification';
      const questions: ClarificationQuestion[] = data.clarification_questions || [];

      const aiMessage: Message = {
        id: Date.now() + 1,
        role: 'ai',
        time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        text: data.answer || data.response || "I didn't quite catch that.",
        type: isClarification && questions.length > 0 ? 'clarification' : 'text',
        artifacts: Array.isArray(data.artifacts) ? data.artifacts : [],
        clarificationQuestions: isClarification && questions.length > 0 ? questions : undefined,
        clarificationAnswered: false,
      };

      setMessages(prev => [...prev, aiMessage]);

      if (isClarification && questions.length > 0) {
        setPendingClarificationId(aiMessage.id);
      }
    } catch (error) {
      console.error('Chat API error:', error);
      setMessages(prev => [
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

  // Called when the user completes all clarification questions
  const handleClarificationComplete = async (messageId: number, answers: Record<string, string>) => {
    // Mark the clarification card as answered (shows summary)
    setMessages(prev =>
      prev.map(m => m.id === messageId ? { ...m, clarificationAnswered: true } : m)
    );
    setPendingClarificationId(null);

    // Send all answers as a single JSON string to resume the paused graph
    const payload = JSON.stringify(answers);
    await handleSendMessage(payload);
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage(input);
    }
  };

  const isInputDisabled = isLoading || pendingClarificationId !== null;

  return (
    <PageShell>
      <PageHeader
        title={`${APP_NAME} Assistant`}
        description="Ask questions about your finances with context from your live transaction data."
      />
      <div className="h-[calc(100vh-220px)]">
      <section className="h-full flex flex-col bento-card !p-0 overflow-hidden relative">
        <div className="flex-1 overflow-y-auto p-10 space-y-10 scrollbar-hide pb-32">
          {messages.map((m) => (
            <div key={m.id} className={cn("flex gap-4 max-w-2xl", m.role === 'user' ? "ml-auto flex-row-reverse text-right" : "")}>
              <div className={cn(
                "w-10 h-10 rounded-full flex items-center justify-center shrink-0 shadow-sm",
                m.role === 'user' ? "bg-surface-container-high" : "bg-primary-container text-white"
              )}>
                {m.role === 'user' ? <User className="w-5 h-5 text-on-surface-variant" /> : <Bot className="w-5 h-5" />}
              </div>
              <div className="space-y-2 w-full max-w-lg">
                <div className={cn(
                  "p-5 rounded-2xl soft-shadow border border-outline-variant/10 leading-relaxed font-medium",
                  m.role === 'user' ? "bg-primary text-white rounded-tr-none text-left whitespace-pre-wrap" : "bg-surface-container-low rounded-tl-none text-on-surface"
                )}>
                  {m.role === 'ai'
                    ? <Markdown>{m.text}</Markdown>
                    : <p className="text-sm">{m.text}</p>}

                  {/* Clarification card — shown inside the AI message bubble */}
                  {m.role === 'ai' && m.type === 'clarification' && m.clarificationQuestions && !m.clarificationAnswered && (
                    <ClarificationCard
                      questions={m.clarificationQuestions}
                      onComplete={(answers) => handleClarificationComplete(m.id, answers)}
                    />
                  )}

                  {/* Answered clarification summary */}
                  {m.role === 'ai' && m.type === 'clarification' && m.clarificationAnswered && (
                    <div className="mt-3 pt-3 border-t border-outline-variant/20">
                      <p className="text-[10px] font-black text-primary uppercase tracking-widest mb-1">Answers submitted</p>
                    </div>
                  )}

                  {/* Chart artifacts */}
                  {m.role === 'ai' && Array.isArray(m.artifacts) && m.artifacts.length > 0 && (
                    <div className="mt-1">
                      {m.artifacts
                        .filter((a: any) => a && a.type === 'chart')
                        .map((a: any, i: number) => (
                          <ChatChart key={i} artifact={a} />
                        ))}
                    </div>
                  )}

                  {/* Legacy card data */}
                  {m.type === 'card' && m.data && (
                    <div className="mt-4 bg-surface-container-lowest p-4 rounded-xl border border-outline-variant/50 space-y-4">
                      {m.data.map((item: any, i: number) => (
                        <div key={i}>
                          <div className="flex justify-between items-center mb-2">
                            <div className="flex items-center gap-2">
                              <div className="w-2 h-2 rounded-full" style={{ backgroundColor: item.color }}></div>
                              <span className="text-[10px] font-bold text-on-surface uppercase tracking-widest">{item.label}</span>
                            </div>
                            <span className="text-xs font-bold text-on-surface">{formatCurrency(item.value)}</span>
                          </div>
                          <div className="w-full bg-surface-container-low h-1.5 rounded-full overflow-hidden">
                            <div className="h-full transition-all duration-1000" style={{ width: `${item.percent}%`, backgroundColor: item.color }}></div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
                <span className="text-[10px] font-bold text-outline px-1 block uppercase tracking-widest">{m.time}</span>
              </div>
            </div>
          ))}

          {isLoading && (
            <div className="flex gap-4 max-w-2xl">
              <div className="w-10 h-10 rounded-full flex items-center justify-center shrink-0 shadow-sm bg-primary-container text-white">
                <Bot className="w-5 h-5" />
              </div>
              <div className="space-y-2 w-full max-w-lg">
                <div className="p-5 rounded-2xl soft-shadow border border-outline-variant/10 leading-relaxed font-medium bg-surface-container-low rounded-tl-none text-on-surface flex items-center gap-2">
                  <Loader2 className="w-4 h-4 animate-spin text-primary" />
                  <span className="text-sm text-outline font-bold">Thinking…</span>
                </div>
              </div>
            </div>
          )}

          {/* Hint banner while clarification is pending */}
          {pendingClarificationId !== null && !isLoading && (
            <div className="flex justify-center">
              <div className="px-4 py-2 bg-primary/8 border border-primary/20 rounded-full">
                <p className="text-[10px] font-black text-primary uppercase tracking-widest">
                  Please answer the questions above to continue
                </p>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input Area */}
        <div className="absolute bottom-0 left-0 right-0 p-8 bg-gradient-to-t from-surface-container-lowest via-surface-container-lowest/90 to-transparent">
          <div className="max-w-3xl mx-auto">
            {!messages.some(m => m.role === 'user') && (
              <div className="flex gap-2 mb-4 overflow-x-auto scrollbar-hide pb-2">
                {['Best FD rates in India?', "Predict next month's expenses", "How much should I save for emergency?"].map((chip) => (
                  <button
                    key={chip}
                    onClick={() => handleSendMessage(chip)}
                    className="shrink-0 px-4 py-1.5 bg-white border border-outline-variant/50 rounded-full text-[10px] font-bold text-outline hover:border-primary hover:text-primary transition-all shadow-sm"
                  >
                    {chip}
                  </button>
                ))}
              </div>
            )}
            <div className={cn(
              "bg-surface-container-low border rounded-2xl p-2 flex items-center gap-2 shadow-sm transition-all",
              isInputDisabled
                ? "border-outline-variant/20 opacity-60 cursor-not-allowed"
                : "border-outline-variant/50 focus-within:ring-2 focus-within:ring-primary"
            )}>
              <button className="p-2.5 text-outline hover:text-primary transition-colors" disabled={isInputDisabled}>
                <Paperclip className="w-5 h-5 -rotate-45" />
              </button>
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyPress}
                placeholder={pendingClarificationId !== null ? "Answer the questions above first…" : "Ask about your finances or portfolio…"}
                className="flex-1 bg-transparent border-none focus:ring-0 text-sm font-medium py-3 px-1"
                disabled={isInputDisabled}
              />
              <button
                onClick={() => handleSendMessage(input)}
                disabled={isInputDisabled || !input.trim()}
                className="bg-primary text-white w-12 h-12 rounded-xl flex items-center justify-center hover:scale-105 active:scale-95 transition-all shadow-lg disabled:opacity-50 disabled:hover:scale-100"
              >
                {isLoading ? <Loader2 className="w-5 h-5 animate-spin" /> : <Send className="w-5 h-5" />}
              </button>
            </div>
          </div>
        </div>
      </section>
      </div>
    </PageShell>
  );
};
