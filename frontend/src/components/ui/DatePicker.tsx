import { format } from 'date-fns';
import { cn } from '@/utils/cn';

export interface DatePickerProps {
  date?: Date;
  onSelect?: (date?: Date) => void;
  className?: string;
  placeholder?: string;
  disabled?: boolean;
}

export function DatePicker({
  date,
  onSelect,
  className,
  disabled = false,
}: DatePickerProps) {
  return (
    <div className={cn('relative', className)}>
      <input
        type="date"
        value={date ? format(date, 'yyyy-MM-dd') : ''}
        onChange={(e) => {
          const val = e.target.value;
          if (onSelect) {
            onSelect(val ? new Date(val) : undefined);
          }
        }}
        disabled={disabled}
        className={cn(
          'flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50',
          className
        )}
      />
    </div>
  );
}

export default DatePicker;
