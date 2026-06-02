import React, { useState, useRef, useEffect } from 'react';
import { Lock, Eye, EyeOff, X, ShieldAlert } from 'lucide-react';

interface PdfPasswordModalProps {
  fileName: string;
  isWrongPassword?: boolean;
  onSubmit: (password: string) => void;
  onCancel: () => void;
}

export const PdfPasswordModal: React.FC<PdfPasswordModalProps> = ({
  fileName,
  isWrongPassword = false,
  onSubmit,
  onCancel,
}) => {
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (password.trim()) onSubmit(password);
  };

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-md bg-surface-container-lowest rounded-3xl border border-outline-variant/30 shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="bg-primary/5 border-b border-outline-variant/20 p-6 flex items-start justify-between gap-4">
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 rounded-2xl bg-primary/10 flex items-center justify-center text-primary shrink-0">
              <ShieldAlert className="w-6 h-6" />
            </div>
            <div>
              <h3 className="text-lg font-bold text-on-surface">Password Protected PDF</h3>
              <p className="text-[11px] text-outline font-bold uppercase tracking-widest mt-0.5 truncate max-w-[220px]">
                {fileName}
              </p>
            </div>
          </div>
          <button
            onClick={onCancel}
            className="text-outline hover:text-on-surface transition-colors p-1 rounded-lg hover:bg-surface-container-low"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Body */}
        <form onSubmit={handleSubmit} className="p-6 space-y-5">
          <p className="text-sm text-on-surface-variant leading-relaxed">
            This PDF is encrypted. Enter the password provided by your bank to unlock and parse the statement.
          </p>

          {isWrongPassword && (
            <div className="flex items-center gap-2 px-4 py-3 bg-error/10 border border-error/20 rounded-xl text-error">
              <ShieldAlert className="w-4 h-4 shrink-0" />
              <span className="text-[12px] font-bold">Incorrect password. Please try again.</span>
            </div>
          )}

          <div className="space-y-2">
            <label className="text-[10px] font-black text-outline uppercase tracking-widest">
              PDF Password
            </label>
            <div className="relative">
              <Lock className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-outline" />
              <input
                ref={inputRef}
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter password..."
                className="w-full pl-11 pr-11 py-3 bg-surface-container-low border border-outline-variant/50 rounded-xl font-bold text-sm focus:ring-2 focus:ring-primary outline-none transition-all"
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-4 top-1/2 -translate-y-1/2 text-outline hover:text-on-surface transition-colors"
              >
                {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>

          <div className="flex gap-3 pt-1">
            <button
              type="button"
              onClick={onCancel}
              className="flex-1 py-3 bg-surface-container-high text-on-surface font-bold rounded-xl text-sm hover:brightness-95 transition-all"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!password.trim()}
              className="flex-[2] py-3 bg-primary text-white font-bold rounded-xl text-sm shadow-md hover:brightness-110 active:scale-95 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Unlock & Parse
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
