import React from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';
import { QuickAddForm } from './QuickAddForm';

interface QuickAddModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess?: () => void;
  accounts?: any[];
}

export const QuickAddModal: React.FC<QuickAddModalProps> = ({
  isOpen,
  onClose,
  onSuccess,
  accounts,
}) => {
  if (!isOpen) return null;

  const handleSuccess = () => {
    onSuccess?.();
    onClose();
  };

  return createPortal(
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={onClose} />
      <div
        className="relative w-full max-w-lg max-h-[90vh] overflow-y-auto bg-white-card rounded-3xl shadow-2xl border border-lumio-line/40 p-6 md:p-8"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          type="button"
          onClick={onClose}
          className="absolute top-4 right-4 w-8 h-8 rounded-full border border-lumio-line flex items-center justify-center hover:bg-soft-card transition-colors"
          aria-label="Close"
        >
          <X className="w-4 h-4" />
        </button>
        <QuickAddForm
          onSuccess={handleSuccess}
          accounts={accounts}
          variant="modal"
        />
      </div>
    </div>,
    document.body,
  );
};
