import * as React from 'react';
import { cn } from '@/utils/cn';

interface SeparatorProps extends React.HTMLAttributes<HTMLHRElement> {
  orientation?: 'horizontal' | 'vertical';
  decorative?: boolean;
}

const Separator = React.forwardRef<HTMLHRElement, SeparatorProps>(
  ({ className, orientation = 'horizontal', decorative = true, ...props }, ref) => (
  <hr
    ref={ref}
    role={decorative ? 'none' : 'separator'}
    aria-orientation={decorative ? undefined : orientation}
    className={cn(
      'shrink-0 bg-border',
      className,
      orientation === 'horizontal' ? 'h-[1px] w-full' : 'w-[1px] h-full'
    )}
    {...props}
  />
));
Separator.displayName = 'Separator';

export { Separator };