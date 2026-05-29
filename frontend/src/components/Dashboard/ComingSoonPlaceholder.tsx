import React from 'react';
import { Clock } from 'lucide-react';
import { cn } from '../../lib/utils';

interface ComingSoonPlaceholderProps {
  className?: string;
  message?: string;
}

export const ComingSoonPlaceholder: React.FC<ComingSoonPlaceholderProps> = ({ 
  className, 
  message = "Feature Coming Soon" 
}) => {
  return (
    <div className={cn(
      "flex-1 flex flex-col items-center justify-center text-outline min-h-[200px]",
      className
    )}>
      <Clock className="w-8 h-8 mb-3 opacity-20" />
      <p className="text-[11px] font-black uppercase tracking-[0.2em] opacity-40 text-center px-4">
        {message}
      </p>
    </div>
  );
};
