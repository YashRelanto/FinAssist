import React, { useState } from 'react';
import { Send, User, Bot, Paperclip, Sparkles } from 'lucide-react';
import { cn, formatCurrency } from '../lib/utils';

const initialMessages = [
  { id: 1, role: 'ai', time: '10:42 AM', text: `Hello. I've analyzed your transaction patterns for the first half of October. Based on your current trajectory, I predict your month-end expenses will be approximately ${formatCurrency(4250)}.`, type: 'text' },
  { id: 2, role: 'user', time: '10:43 AM', text: "That seems higher than last month. Where is the increase coming from?", type: 'text' },
  { id: 3, role: 'ai', time: '10:44 AM', text: "The primary driver is a 24% increase in 'Home Improvement' and 'Subscriptions'. Here is the breakdown of your top categories:", type: 'card', data: [
    { label: 'Home Improvement', value: 842, percent: 65, color: '#004ac6' },
    { label: 'Essential Utilities', value: 315, percent: 40, color: '#006c49' },
  ]},
  { id: 4, role: 'ai', time: '10:44 AM', text: `If you reduce non-essential subscriptions, you could save approximately ${formatCurrency(120)} by the end of the quarter. Would you like me to identify which subscriptions have low engagement?`, type: 'text' },
];

export const AIAssistant: React.FC = () => {
  const [messages, setMessages] = useState(initialMessages);
  const [input, setInput] = useState('');

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
                     "p-5 rounded-2xl soft-shadow border border-outline-variant/10 leading-relaxed font-medium",
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
               {['Summarize my spending', "Predict next month's expenses", "Where can I save?"].map((chip) => (
                 <button key={chip} className="shrink-0 px-4 py-1.5 bg-white border border-outline-variant/50 rounded-full text-[10px] font-bold text-outline hover:border-primary hover:text-primary transition-all shadow-sm">
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
                  placeholder="Ask about your finances or portfolio..." 
                  className="flex-1 bg-transparent border-none focus:ring-0 text-sm font-medium py-3 px-1"
                />
                <button className="bg-primary text-white w-12 h-12 rounded-xl flex items-center justify-center hover:scale-105 active:scale-95 transition-all shadow-lg">
                  <Send className="w-5 h-5" />
                </button>
             </div>
           </div>
        </div>
      </section>
    </div>
  );
};
