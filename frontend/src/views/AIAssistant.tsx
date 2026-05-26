import React, { useState, useRef, useEffect } from 'react';
import { Send, User, Bot, Paperclip, Sparkles, Loader2 } from 'lucide-react';
import { cn, formatCurrency } from '../lib/utils';
import { useAppContext } from '../context/AppContext';

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
  const { user } = useAppContext();
  const [messages, setMessages] = useState<any[]>(initialMessages);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

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
      const response = await fetch('http://localhost:8000/api/chat/message', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          user_id: user.userId || 'guest-user',
          message: text,
          thread_id: 'default-thread'
        })
      });

      if (!response.ok) throw new Error('API request failed');

      const data = await response.json();
      
      const aiMessage = {
        id: Date.now() + 1,
        role: 'ai',
        time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        text: data.answer || data.response || "I didn't quite catch that.",
        type: 'text'
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
    <div className="flex h-[calc(100vh-140px)] gap-6">
      {/* Sidebar - Recent interactions */}
      <aside className="w-80 bg-surface-container-lowest border border-outline-variant/30 rounded-2xl flex flex-col overflow-hidden shadow-sm">
        <div className="p-4 border-b border-outline-variant/30">
          <button className="w-full flex items-center justify-center gap-2 py-2.5 bg-primary text-white rounded-xl font-bold shadow-md hover:brightness-110 active:scale-95 transition-all">
            <Sparkles className="w-4 h-4" /> New Insight
          </button>
        </div>
        <div className="flex-1 overflow-y-auto scrollbar-hide p-2 space-y-1">
           <h3 className="px-3 py-4 text-[10px] font-bold text-outline uppercase tracking-widest">Recent Interactions</h3>
           {[
             { title: 'Spending Prediction Oct', time: 'Today', sub: 'Based on current trajectory...' },
             { title: 'September Spend Summary', time: 'Yesterday', sub: 'You saved 12% more than...' },
             { title: 'Budget Advice: Dining', time: '2 days ago', sub: 'Recommendations for dining...' },
             { title: 'Stock Portfolio Analysis', time: 'Oct 12', sub: 'Diversification check complete.' },
           ].map((item, i) => (
             <button key={i} className={cn(
               "w-full text-left p-3 rounded-xl transition-all duration-200",
               i === 0 ? "bg-surface-container-low border-l-4 border-primary" : "hover:bg-surface-container-low"
             )}>
                <p className="text-sm font-bold text-on-surface truncate">{item.title}</p>
                <p className="text-[10px] text-outline font-medium mt-1">{item.time} • {item.sub}</p>
             </button>
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
      </aside>

      {/* Main Chat Interface */}
      <section className="flex-1 flex flex-col bg-surface-container-lowest border border-outline-variant/30 rounded-2xl shadow-sm overflow-hidden relative">
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
        </div>

        {/* Input Area */}
        <div className="absolute bottom-0 left-0 right-0 p-8 bg-gradient-to-t from-surface-container-lowest via-surface-container-lowest/90 to-transparent">
           <div className="max-w-3xl mx-auto">
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
