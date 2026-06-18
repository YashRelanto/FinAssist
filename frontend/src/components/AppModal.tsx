import React from 'react';
import { createPortal } from 'react-dom';
import { cn } from '../lib/utils';

interface AppModalProps {
  isOpen: boolean;
  onClose?: () => void;
  children: React.ReactNode;
  className?: string;
  overlayClassName?: string;
}

/** Full-screen modal portal above TopNav (z-50) with blurred backdrop. */
export const AppModal: React.FC<AppModalProps> = ({
  isOpen,
  onClose,
  children,
  className,
  overlayClassName,
}) => {
  if (!isOpen) return null;

  return createPortal(
    <div className="fixed inset-0 z-[110] flex items-center justify-center p-4">
      <div
        className={cn('absolute inset-0 bg-black/40 backdrop-blur-sm', overlayClassName)}
        onClick={onClose}
        aria-hidden
      />
      <div
        className={cn('relative w-full max-w-lg max-h-[90vh] overflow-y-auto', className)}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        {children}
      </div>
    </div>,
    document.body,
  );
};
