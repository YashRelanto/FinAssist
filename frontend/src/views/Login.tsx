import React, { useState } from 'react';
import { motion } from 'motion/react';
import { Mail, Lock, LogIn, ChevronRight, LayoutDashboard, ShieldCheck, Zap } from 'lucide-react';
import { useAppContext } from '../context/AppContext';
import { cn } from '../lib/utils';

export const Login: React.FC = () => {
  const { updateUser } = useAppContext();
  const [isSignUp, setIsSignUp] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    const endpoint = isSignUp ? '/api/register' : '/api/login';
    const body = isSignUp 
      ? { full_name: name, email, password } 
      : { email, password };

    try {
      const response = await fetch(`http://localhost:8000${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });

      const data = await response.json();

      if (response.ok) {
        alert(data.message); // Showing success message as requested
        updateUser({ 
          isAuthenticated: true, 
          name: data.user.full_name || 'User', 
          email: data.user.email,
          id: data.user.user_id
        });
      } else {
        alert(data.detail || "Authentication failed");
      }
    } catch (error) {
      alert("Error connecting to backend");
    }
  };

  return (
    <div className="min-h-screen bg-surface flex flex-col items-center justify-center p-4 relative overflow-hidden">
      {/* Background Decor */}
      <div className="absolute top-0 left-0 w-full h-full pointer-events-none opacity-5">
        <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-primary rounded-full blur-[120px]" />
        <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-secondary rounded-full blur-[120px]" />
      </div>

      <motion.div 
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="w-full max-w-md space-y-8 z-10"
      >
        <div className="text-center space-y-3">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-primary text-white shadow-xl shadow-primary/20 mb-4">
            <LayoutDashboard className="w-8 h-8" />
          </div>
          <h1 className="text-4xl font-black tracking-tight text-on-surface">FinAssist</h1>
          <p className="text-outline font-medium">Elevate your financial intelligence.</p>
        </div>

        <div className="bg-surface-container-lowest p-8 rounded-3xl shadow-2xl border border-outline-variant/30">
          <div className="flex gap-4 p-1 bg-surface-container-high rounded-xl mb-8">
            <button 
              onClick={() => setIsSignUp(false)}
              className={cn(
                "flex-1 py-2 text-xs font-bold uppercase tracking-widest rounded-lg transition-all",
                !isSignUp ? "bg-white text-primary shadow-sm" : "text-outline hover:text-on-surface"
              )}
            >
              Log In
            </button>
            <button 
              onClick={() => setIsSignUp(true)}
              className={cn(
                "flex-1 py-2 text-xs font-bold uppercase tracking-widest rounded-lg transition-all",
                isSignUp ? "bg-white text-primary shadow-sm" : "text-outline hover:text-on-surface"
              )}
            >
              Sign Up
            </button>
          </div>

          <form onSubmit={handleSubmit} className="space-y-5">
            {isSignUp && (
              <div className="space-y-2">
                <label className="text-[10px] font-bold text-outline uppercase tracking-widest ml-1">Full Name</label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none text-outline">
                    <LogIn className="w-5 h-5 opacity-50" />
                  </div>
                  <input 
                    required 
                    type="text" 
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    className="w-full pl-12 pr-4 py-4 bg-surface-container-low border border-outline-variant rounded-xl focus:ring-2 focus:ring-primary outline-none transition-all font-medium text-sm" 
                    placeholder="Enter your name" 
                  />
                </div>
              </div>
            )}

            <div className="space-y-2">
              <label className="text-[10px] font-bold text-outline uppercase tracking-widest ml-1">Email Address</label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none text-outline">
                  <Mail className="w-5 h-5 opacity-50" />
                </div>
                <input 
                  required 
                  type="email" 
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full pl-12 pr-4 py-4 bg-surface-container-low border border-outline-variant rounded-xl focus:ring-2 focus:ring-primary outline-none transition-all font-medium text-sm" 
                  placeholder="name@company.com" 
                />
              </div>
            </div>

            <div className="space-y-2">
              <label className="text-[10px] font-bold text-outline uppercase tracking-widest ml-1">Password</label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none text-outline">
                  <Lock className="w-5 h-5 opacity-50" />
                </div>
                <input 
                  required 
                  type="password" 
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full pl-12 pr-4 py-4 bg-surface-container-low border border-outline-variant rounded-xl focus:ring-2 focus:ring-primary outline-none transition-all font-medium text-sm" 
                  placeholder="••••••••" 
                />
              </div>
            </div>

            {!isSignUp && (
              <div className="flex items-center justify-end">
                <button type="button" className="text-[10px] font-bold text-primary uppercase tracking-widest hover:underline">
                  Forgot Password?
                </button>
              </div>
            )}

            <button 
              type="submit"
              className="w-full py-4 bg-primary text-white font-bold rounded-xl shadow-lg shadow-primary/20 hover:brightness-110 active:scale-[0.98] transition-all flex items-center justify-center gap-2 group"
            >
              {isSignUp ? 'Create Account' : 'Sign In'}
              <ChevronRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
            </button>
          </form>

          <div className="mt-8 pt-8 border-t border-outline-variant/30 space-y-4">
            <div className="flex items-center gap-4">
              <div className="h-[1px] flex-1 bg-outline-variant/30" />
              <span className="text-[10px] font-bold text-outline uppercase tracking-widest">Trust & Security</span>
              <div className="h-[1px] flex-1 bg-outline-variant/30" />
            </div>
            
            <div className="flex justify-center gap-6">
              <div className="flex items-center gap-2 text-outline">
                <ShieldCheck className="w-4 h-4" />
                <span className="text-[9px] font-bold uppercase tracking-wider">AES-256</span>
              </div>
              <div className="flex items-center gap-2 text-outline">
                <Zap className="w-4 h-4" />
                <span className="text-[9px] font-bold uppercase tracking-wider">Fast Auth</span>
              </div>
            </div>
          </div>
        </div>

        <p className="text-center text-[10px] text-outline font-bold uppercase tracking-widest">
          By continuing, you agree to our <button className="text-on-surface hover:underline">Terms of Service</button>
        </p>
      </motion.div>
    </div>
  );
};
