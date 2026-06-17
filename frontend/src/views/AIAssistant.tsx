import React, { useState, useRef, useEffect } from 'react';
import { Send, User, Bot, Paperclip, Loader2 } from 'lucide-react';
import { cn, formatCurrency } from '../lib/utils';
import { useAppContext } from '../context/AppContext';
import { apiFetch } from '../lib/api';
import { ChatChart } from '../components/ChatChart';

const initialMessages = [
  { 
    id: 1, 
    role: 'ai', 
    time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }), 
    text: "Hello! I am your FinAssist AI Advisor. I have access to your transactions and our latest financial knowledge base. How can I help you today?", 
    type: 'text' 
  }
];

export const AIAssistant: React.FC = () => {
  const { user, chatMessages: messages, setChatMessages: setMessages } = useAppContext();
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new messages or loading state change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  const handleSendMessage = async (text: string) => {
    if (!text.trim()) return;

    const userMessage = {
      id: Date.now(),
      role: 'user',
      time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      text: text,
      type: 'text'
    };

    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);

    try {
      const response = await apiFetch('/api/chat/message', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: text,
          thread_id: 'default-thread',
        }),
      });

      if (!response.ok) throw new Error('API request failed');

      const data = await response.json();

      const aiMessage = {
        id: Date.now() + 1,
        role: 'ai',
        time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        text: data.answer || data.response || "I didn't quite catch that.",
        type: 'text',
        // Visualization specs returned by the backend (charts to render inline).
        artifacts: Array.isArray(data.artifacts) ? data.artifacts : [],
      };

      setMessages(prev => [...prev, aiMessage]);
    } catch (error) {
      console.error("Chat API error:", error);
      const errorMessage = {
        id: Date.now() + 1,
        role: 'ai',
        time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        text: "I'm sorry, I couldn't connect to the backend server. Please make sure the FastAPI server is running.",
        type: 'text'
      };
      setMessages(prev => [...prev, errorMessage]);
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
             <div key={m.id} className={cn("flex gap-4 max-w-2xl", m.role === 'user' ? "ml-auto flex-row-reverse text-right" : "")}>
                <div className={cn(
                  "w-10 h-10 rounded-full flex items-center justify-center shrink-0 shadow-sm",
                  m.role === 'user' ? "bg-surface-container-high" : "bg-primary-container text-white"
                )}>
                  {m.role === 'user' ? <User className="w-5 h-5 text-on-surface-variant" /> : <Bot className="w-5 h-5" />}
                </div>
                <div className="space-y-2 w-full max-w-lg">
                   <div className={cn(
                     "p-5 rounded-2xl soft-shadow border border-outline-variant/10 leading-relaxed font-medium whitespace-pre-wrap",
                     m.role === 'user' ? "bg-primary text-white rounded-tr-none text-left" : "bg-surface-container-low rounded-tl-none text-on-surface"
                   )}>
                      <p className="text-sm">{m.text}</p>
                      {m.role === 'ai' && Array.isArray(m.artifacts) && m.artifacts.length > 0 && (
                        <div className="mt-1">
                          {m.artifacts
                            .filter((a: any) => a && a.type === 'chart')
                            .map((a: any, i: number) => (
                              <ChatChart key={i} artifact={a} />
                            ))}
                        </div>
                      )}
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
                   <span className="text-sm text-outline font-bold">Thinking...</span>
                </div>
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
             <div className="bg-surface-container-low border border-outline-variant/50 rounded-2xl p-2 flex items-center gap-2 shadow-sm focus-within:ring-2 focus-within:ring-primary transition-all">
                <button className="p-2.5 text-outline hover:text-primary transition-colors">
                  <Paperclip className="w-5 h-5 -rotate-45" />
                </button>
                <input 
                  type="text" 
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyPress}
                  placeholder="Ask about your finances or portfolio..." 
                  className="flex-1 bg-transparent border-none focus:ring-0 text-sm font-medium py-3 px-1"
                  disabled={isLoading}
                />
                <button 
                  onClick={() => handleSendMessage(input)}
                  disabled={isLoading || !input.trim()}
                  className="bg-primary text-white w-12 h-12 rounded-xl flex items-center justify-center hover:scale-105 active:scale-95 transition-all shadow-lg disabled:opacity-50 disabled:hover:scale-100"
                >
                  {isLoading ? <Loader2 className="w-5 h-5 animate-spin" /> : <Send className="w-5 h-5" />}
                </button>
             </div>
           </div>
        </div>
      </section>
    </div>
  );
};
