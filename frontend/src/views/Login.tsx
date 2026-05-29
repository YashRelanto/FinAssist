import React, { useState } from 'react';
import { motion } from 'motion/react';
import {
  Mail,
  Lock,
  LogIn,
  ChevronRight,
  LayoutDashboard,
  ShieldCheck,
  Zap
} from 'lucide-react';

import { useAppContext } from '../context/AppContext';
import { cn } from '../lib/utils';

export const Login: React.FC = () => {
  const { updateUser } = useAppContext();

  const [isSignUp, setIsSignUp] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [error, setError] = useState('');
  const [isConnecting, setIsConnecting] = useState(false);
  const [emailVerificationSent, setEmailVerificationSent] = useState(false);
  const [verificationEmail, setVerificationEmail] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    setError('');
    setIsConnecting(true);

    const endpoint = isSignUp ? '/api/register' : '/api/login';

    const body = isSignUp
      ? {
          full_name: name,
          email,
          password
        }
      : {
          email,
          password
        };

    try {
      const response = await fetch(`http://localhost:8000${endpoint}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(body)
      });

      const data = await response.json();

      if (!response.ok) {
        const errData = await response.json();
        if (errData.detail === 'email_not_confirmed') {
          setVerificationEmail(email);
          setEmailVerificationSent(true);
          setIsConnecting(false);
          return;
        }
        throw new Error(errData.detail || 'Authentication failed');
      }
      
      
      // Support both flat response (e.g. from auth.py) and nested response (e.g. from api.py)
      const emailConfirmed = data.email_confirmed !== undefined ? data.email_confirmed : data.user?.email_confirmed;
      
      if (isSignUp && emailConfirmed === false) {
        setVerificationEmail(email);
        setEmailVerificationSent(true);
        setIsConnecting(false);
        return;
      }
      
      const resolvedUserId = data.user_id || data.user?.user_id;
      const resolvedName = data.full_name || data.user?.full_name || name || 'User';
      const resolvedEmail = data.email || data.user?.email || email || 'user@example.com';
      const resolvedOnboarded = data.onboarded !== undefined ? data.onboarded : (data.user?.onboarded || false);
      const resolvedIncome = data.income !== undefined ? data.income : (data.user?.income || 0);
      const resolvedCityTier = data.city_tier || data.user?.city_tier || 'Metro';
      const resolvedRent = data.fixed_rent !== undefined ? data.fixed_rent : (data.user?.fixed_rent || 0);
      const resolvedEmi = data.fixed_emi !== undefined ? data.fixed_emi : (data.user?.fixed_emi || 0);
      const resolvedBiggestCategory = data.biggest_category || data.user?.biggest_category || '';
      const resolvedPrimaryGoal = data.primary_goal || data.user?.primary_goal || '';
      const resolvedStatement = data.statement_uploaded !== undefined ? data.statement_uploaded : (data.user?.statement_uploaded || false);

      updateUser({
        isAuthenticated: true,
        userId: resolvedUserId,
        name: resolvedName,
        email: resolvedEmail,
        onboarded: resolvedOnboarded,
        income: resolvedIncome,
        cityTier: resolvedCityTier,
        fixedRent: resolvedRent,
        fixedEMI: resolvedEmi,
        biggestCategory: resolvedBiggestCategory,
        primaryGoal: resolvedPrimaryGoal,
        statementUploaded: resolvedStatement
      });

    } catch (err: any) {
      console.error(err);

      setError(
        err.message || 'Could not connect to authentication server.'
      );

    } finally {
      setIsConnecting(false);
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
        
        {/* Header */}
        <div className="text-center space-y-3">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-primary text-white shadow-xl shadow-primary/20 mb-4">
            <LayoutDashboard className="w-8 h-8" />
          </div>

          <h1 className="text-4xl font-black tracking-tight text-on-surface">
            FinAssist
          </h1>

          <p className="text-outline font-medium">
            Elevate your financial intelligence.
          </p>
        </div>

        {/* Card */}
        <div className="bg-surface-container-lowest p-8 rounded-3xl shadow-2xl border border-outline-variant/30">
          {emailVerificationSent ? (
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              className="text-center space-y-6 py-4"
            >
              <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-primary/10 text-primary mb-2">
                <Mail className="w-8 h-8 animate-pulse text-primary" />
              </div>
              <h2 className="text-2xl font-black text-on-surface">Confirm your email</h2>
              <p className="text-sm text-outline font-medium leading-relaxed">
                We've sent a verification link to <span className="text-on-surface font-bold">{verificationEmail}</span>.
                Please check your inbox and click the link to confirm your account.
              </p>
              
              <div className="p-4 bg-primary/5 rounded-2xl border border-primary/10 space-y-2 text-left">
                <span className="text-[10px] font-bold text-primary uppercase tracking-widest block">Next Steps</span>
                <p className="text-xs text-outline font-medium">
                  Once verified, you will be automatically redirected to complete your onboarding forms and customize your experience.
                </p>
              </div>

              <div className="pt-4 space-y-3">
                <button
                  onClick={() => {
                    const domain = verificationEmail.split('@')[1];
                    if (domain.includes('gmail.com')) {
                      window.open('https://mail.google.com', '_blank');
                    } else if (domain.includes('outlook.com') || domain.includes('hotmail.com')) {
                      window.open('https://outlook.live.com', '_blank');
                    } else {
                      window.open(`https://${domain}`, '_blank');
                    }
                  }}
                  className="w-full py-4 bg-primary text-white font-bold rounded-xl shadow-lg shadow-primary/20 hover:brightness-110 active:scale-[0.98] transition-all flex items-center justify-center gap-2 group"
                >
                  <span>Open Mailbox</span>
                  <ChevronRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
                </button>

                <button 
                  onClick={() => setEmailVerificationSent(false)}
                  className="w-full py-3.5 bg-surface-container-high hover:bg-surface-container-low transition-all rounded-xl font-bold text-sm text-outline hover:text-on-surface shadow-sm active:scale-[0.98]"
                >
                  Back to Sign In
                </button>
              </div>
            </motion.div>
          ) : (
            <>
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

              {/* Continue with Google button */}
              <div className="mb-6 space-y-4">
                <button
                  type="button"
                  onClick={() => {
                    window.location.href = "https://wequiafwuvugkzgqzety.supabase.co/auth/v1/authorize?provider=google&redirect_to=http://localhost:3000";
                  }}
                  className="w-full flex items-center justify-center gap-3 py-3.5 bg-white border border-outline-variant hover:bg-surface-container-low transition-all rounded-xl font-bold text-sm text-on-surface shadow-sm active:scale-[0.98]"
                >
                  <svg className="w-5 h-5 shrink-0" viewBox="0 0 24 24">
                    <path fill="#EA4335" d="M12 5.04c1.66 0 3.2.57 4.38 1.69l3.27-3.27C17.67 1.57 15 0 12 0 7.35 0 3.37 2.67 1.43 6.56l3.86 3C6.26 6.94 8.92 5.04 12 5.04z" />
                    <path fill="#4285F4" d="M23.49 12.27c0-.81-.07-1.59-.2-2.36H12v4.51h6.46c-.29 1.48-1.14 2.73-2.42 3.58l3.76 2.92c2.2-2.03 3.69-5.02 3.69-8.65z" />
                    <path fill="#FBBC05" d="M5.29 14.14c-.24-.72-.38-1.49-.38-2.29s.14-1.57.38-2.29L1.43 6.56C.52 8.38 0 10.42 0 12.5s.52 4.12 1.43 5.94l3.86-3z" />
                    <path fill="#34A853" d="M12 24c3.24 0 5.97-1.08 7.96-2.91l-3.76-2.92c-1.04.7-2.38 1.11-4.2 1.11-3.08 0-5.74-1.9-6.67-4.52L1.47 17.7C3.42 21.39 7.39 24 12 24z" />
                  </svg>
                  <span>Continue with Google</span>
                </button>

                <div className="flex items-center gap-4">
                  <div className="h-[1px] flex-1 bg-outline-variant/30" />
                  <span className="text-[10px] font-black text-outline uppercase tracking-widest leading-none">or continue with email</span>
                  <div className="h-[1px] flex-1 bg-outline-variant/30" />
                </div>
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

                {error && (
                  <div className="p-3 bg-red-500/10 border border-red-500/20 text-red-500 rounded-xl text-xs font-bold">
                    {error}
                  </div>
                )}

                {!isSignUp && (
                  <div className="flex items-center justify-end">
                    <button type="button" className="text-[10px] font-bold text-primary uppercase tracking-widest hover:underline">
                      Forgot Password?
                    </button>
                  </div>
                )}

                <button 
                  type="submit"
                  disabled={isConnecting}
                  className="w-full py-4 bg-primary text-white font-bold rounded-xl shadow-lg shadow-primary/20 hover:brightness-110 active:scale-[0.98] transition-all flex items-center justify-center gap-2 group disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {isConnecting ? 'Authenticating...' : (isSignUp ? 'Create Account' : 'Sign In')}
                  <ChevronRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
                </button>
              </form>
            </>
          )}

            
        

          {/* Security Footer */}
          <div className="mt-8 pt-8 border-t border-outline-variant/30 space-y-4">

            <div className="flex items-center gap-4">
              <div className="h-[1px] flex-1 bg-outline-variant/30" />

              <span className="text-[10px] font-bold text-outline uppercase tracking-widest">
                Trust & Security
              </span>

              <div className="h-[1px] flex-1 bg-outline-variant/30" />
            </div>

            <div className="flex justify-center gap-6">

              <div className="flex items-center gap-2 text-outline">
                <ShieldCheck className="w-4 h-4" />
                <span className="text-[9px] font-bold uppercase tracking-wider">
                  AES-256
                </span>
              </div>

              <div className="flex items-center gap-2 text-outline">
                <Zap className="w-4 h-4" />
                <span className="text-[9px] font-bold uppercase tracking-wider">
                  Fast Auth
                </span>
              </div>

            </div>
          </div>
        </div>

        {/* Footer */}
        <p className="text-center text-[10px] text-outline font-bold uppercase tracking-widest">
          By continuing, you agree to our{' '}
          <button className="text-on-surface hover:underline">
            Terms of Service
          </button>
        </p>
      </motion.div>
    </div>
  );
};