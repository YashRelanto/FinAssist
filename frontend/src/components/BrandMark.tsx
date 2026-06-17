import React from 'react';
import { cn } from '../lib/utils';
import { APP_NAME } from '../lib/utils';

interface BrandMarkProps {
  variant?: 'dark' | 'light';
  showName?: boolean;
  showIcon?: boolean;
  className?: string;
  nameClassName?: string;
}

export const BrandMark: React.FC<BrandMarkProps> = ({
  variant = 'dark',
  showName = true,
  showIcon = true,
  className,
  nameClassName,
}) => {
  const isDark = variant === 'dark';

  return (
    <div className={cn('flex items-center gap-2.5 min-w-0', className)}>
      {showIcon && (
        <div
          className={cn(
            'w-[34px] h-[34px] rounded-full border flex items-center justify-center shrink-0',
            isDark ? 'border-page-bg/80' : 'border-lumio-text/30',
          )}
        >
          <span
            className={cn(
              'font-bold text-sm leading-none',
              isDark ? 'text-page-bg' : 'text-lumio-text',
            )}
          >
            F
          </span>
        </div>
      )}
      {showName && (
        <span
          className={cn(
            'font-label text-[11px] font-bold uppercase tracking-wider whitespace-nowrap truncate',
            isDark ? 'text-page-bg' : 'text-lumio-text',
            nameClassName,
          )}
        >
          {APP_NAME}
        </span>
      )}
    </div>
  );
};
