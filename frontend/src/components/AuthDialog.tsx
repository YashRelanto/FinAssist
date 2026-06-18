import React, { useState } from 'react';
import { Mail, Lock, ChevronRight, ShieldCheck, Zap } from 'lucide-react';
import { useAppContext } from '../context/AppContext';
import { cn, APP_NAME } from '../lib/utils';
import type { UserProfile } from '../types';
import { saveAuthSession } from '../lib/authSession';
import { apiFetch } from '../lib/api';
import { parseApiError, readJsonResponse } from '../lib/apiErrors';
import { getGoogleOAuthUrl } from '../lib/oauth';
import { BrandMark } from './BrandMark';

interface AuthDialogProps {
  open: boolean;
  onClose: () => void;
}

export const AuthDialog: React.FC<AuthDialogProps> = ({ open, onClose }) => {
  const { updateUser } = useAppContext();
  const [isSignUp, setIsSignUp] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [error, setError] = useState('');
  const [isConnecting, setIsConnecting] = useState(false);
  const [emailVerificationSent, setEmailVerificationSent] = useState(false);
  const [verificationEmail, setVerificationEmail] = useState('');

  if (!open) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setIsConnecting(true);

    const endpoint = isSignUp ? '/api/register' : '/api/login';
    const body = isSignUp ? { full_name: name, email, password } : { email, password };

    try {
      const response = await apiFetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await readJsonResponse(response);

      if (!response.ok) {
        const detail = parseApiError(data, 'Authentication failed');
        if (detail === 'email_not_confirmed') {
          setVerificationEmail(email);
          setEmailVerificationSent(true);
          return;
        }
        throw new Error(detail);
      }

      const payload = data as Record<string, unknown>;
      const userPayload = payload.user as Record<string, unknown> | undefined;
      const emailConfirmed = payload.email_confirmed ?? userPayload?.email_confirmed;
      if (isSignUp && emailConfirmed === false) {
        setVerificationEmail(email);
        setEmailVerificationSent(true);
        return;
      }

      const resolvedUserId = (payload.user_id || userPayload?.user_id) as string;
      const loggedInUser = {
        id: resolvedUserId,
        isAuthenticated: true as const,
        userId: resolvedUserId,
        name: (payload.full_name || userPayload?.full_name || name || 'User') as string,
        email: (payload.email || userPayload?.email || email) as string,
        role: (userPayload?.role === 'admin' || payload.role === 'admin' ? 'admin' : 'user') as 'admin' | 'user',
        onboarded: (payload.onboarded ?? userPayload?.onboarded ?? false) as boolean,
        income: Number(payload.income ?? userPayload?.income ?? 0),
        cityTier: (payload.city_tier || userPayload?.city_tier || 'Metro') as UserProfile['cityTier'],
        fixedRent: Number(payload.fixed_rent ?? userPayload?.fixed_rent ?? 0),
        fixedEMI: Number(payload.fixed_emi ?? userPayload?.fixed_emi ?? 0),
        biggestCategory: (payload.biggest_category || userPayload?.biggest_category || '') as string,
        primaryGoal: (payload.primary_goal || userPayload?.primary_goal || '') as string,
        statementUploaded: Boolean(payload.statement_uploaded ?? userPayload?.statement_uploaded ?? false),
      };

      saveAuthSession(
        (payload.access_token as string) || '',
        loggedInUser,
        payload.refresh_token as string | undefined,
      );
      updateUser(loggedInUser, { syncNow: true });
      onClose();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Could not connect to authentication server.');
    } finally {
      setIsConnecting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-lumio-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-md bg-white-card rounded-3xl shadow-2xl border border-lumio-line/30 p-8 max-h-[90vh] overflow-y-auto">
        <button
          type="button"
          onClick={onClose}
          className="absolute top-4 right-4 w-8 h-8 rounded-full border border-lumio-line flex items-center justify-center text-lumio-muted hover:text-lumio-text"
        >
          ×
        </button>

        <div className="text-center mb-8">
          <div className="flex justify-center mb-4">
            <BrandMark variant="light" />
          </div>
          <h2 className="font-display text-2xl font-bold tracking-tight">Welcome to {APP_NAME}</h2>
          <p className="text-sm text-lumio-muted mt-1">Your intelligent financial foundation</p>
        </div>

        {emailVerificationSent ? (
          <div className="text-center space-y-4">
            <Mail className="w-10 h-10 mx-auto text-lumio-black" />
            <p className="text-sm text-lumio-muted">
              Verification link sent to <strong className="text-lumio-text">{verificationEmail}</strong>
            </p>
            <button
              type="button"
              onClick={() => setEmailVerificationSent(false)}
              className="w-full py-3 bg-soft-card rounded-xl font-semibold text-sm"
            >
              Back to Sign In
            </button>
          </div>
        ) : (
          <>
            <div className="flex gap-2 p-1 bg-soft-card rounded-xl mb-6">
              <button
                type="button"
                onClick={() => setIsSignUp(false)}
                className={cn('flex-1 py-2 text-xs font-bold uppercase tracking-widest rounded-lg', !isSignUp && 'bg-white shadow-sm')}
              >
                Log In
              </button>
              <button
                type="button"
                onClick={() => setIsSignUp(true)}
                className={cn('flex-1 py-2 text-xs font-bold uppercase tracking-widest rounded-lg', isSignUp && 'bg-white shadow-sm')}
              >
                Sign Up
              </button>
            </div>

            <button
              type="button"
              onClick={() => {
                const url = getGoogleOAuthUrl();
                if (!url) {
                  setError('Google sign-in is not configured. Set VITE_SUPABASE_URL in your frontend environment.');
                  return;
                }
                window.location.href = url;
              }}
              className="w-full flex items-center justify-center gap-3 py-3 bg-white border border-lumio-line rounded-xl font-semibold text-sm mb-4"
            >
              Continue with Google
            </button>

            <form onSubmit={handleSubmit} className="space-y-4">
              {isSignUp && (
                <input
                  required
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Full name"
                  className="w-full px-4 py-3 bg-soft-card-2 border border-lumio-line/50 rounded-xl text-sm outline-none focus:ring-2 focus:ring-lumio-black/20"
                />
              )}
              <input
                required
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="Email address"
                className="w-full px-4 py-3 bg-soft-card-2 border border-lumio-line/50 rounded-xl text-sm outline-none focus:ring-2 focus:ring-lumio-black/20"
              />
              <input
                required
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Password"
                className="w-full px-4 py-3 bg-soft-card-2 border border-lumio-line/50 rounded-xl text-sm outline-none focus:ring-2 focus:ring-lumio-black/20"
              />
              {error && (
                <p className="text-xs font-semibold text-error bg-error-container/30 rounded-lg px-3 py-2">{error}</p>
              )}
              <button
                type="submit"
                disabled={isConnecting}
                className="w-full py-3.5 bg-lumio-black text-white rounded-full font-label text-xs font-bold uppercase tracking-wider flex items-center justify-center gap-2 disabled:opacity-50"
              >
                {isConnecting ? 'Please wait…' : isSignUp ? 'Create Account' : 'Sign In'}
                <ChevronRight className="w-4 h-4" />
              </button>
            </form>

            <div className="mt-6 pt-6 border-t border-lumio-line/40 flex justify-center gap-6 text-lumio-muted">
              <div className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider">
                <ShieldCheck className="w-3.5 h-3.5" /> AES-256
              </div>
              <div className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider">
                <Zap className="w-3.5 h-3.5" /> Fast Auth
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
};
