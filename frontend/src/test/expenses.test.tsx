import { describe, it, expect } from 'vitest';
import { z } from 'zod';

// Test the financial invariant logic directly
const expenseValidationSchema = z.object({
  project_id: z.string().min(1, 'Please select a project'),
  transaction_date: z.string().min(1, 'Transaction date is required'),
  subtotal: z.coerce.number().min(0.01, 'Subtotal must be greater than 0'),
  tax_amount: z.coerce.number().min(0, 'Tax amount cannot be negative'),
  total: z.coerce.number().min(0.01, 'Total must be greater than 0'),
  currency: z.string().default('INR'),
}).refine(
  (data) => Math.abs((Number(data.subtotal) + Number(data.tax_amount || 0)) - Number(data.total)) <= 0.05,
  {
    message: 'Subtotal + Tax Amount must equal Total',
    path: ['total'],
  }
);

describe('Expense Financial Invariants & Form Validation Suite', () => {
  it('accepts balanced expense numbers (subtotal + tax == total)', () => {
    const validData = {
      project_id: 'proj-123',
      transaction_date: '2026-10-01',
      subtotal: 1000.00,
      tax_amount: 180.00,
      total: 1180.00,
      currency: 'INR',
    };

    const result = expenseValidationSchema.safeParse(validData);
    expect(result.success).toBe(true);
  });

  it('accepts zero-tax expenses where subtotal == total', () => {
    const zeroTaxData = {
      project_id: 'proj-123',
      transaction_date: '2026-10-01',
      subtotal: 500.00,
      tax_amount: 0.00,
      total: 500.00,
      currency: 'INR',
    };

    const result = expenseValidationSchema.safeParse(zeroTaxData);
    expect(result.success).toBe(true);
  });

  it('rejects unbalanced totals (1000 + 180 != 1200)', () => {
    const unbalancedData = {
      project_id: 'proj-123',
      transaction_date: '2026-10-01',
      subtotal: 1000.00,
      tax_amount: 180.00,
      total: 1200.00,
      currency: 'INR',
    };

    const result = expenseValidationSchema.safeParse(unbalancedData);
    expect(result.success).toBe(false);
    if (!result.success) {
      const issue = result.error.issues.find((i) => i.path.includes('total'));
      expect(issue).toBeDefined();
      expect(issue?.message).toMatch(/Subtotal \+ Tax Amount must equal Total/i);
    }
  });

  it('rejects negative subtotal and negative total values', () => {
    const negativeData = {
      project_id: 'proj-123',
      transaction_date: '2026-10-01',
      subtotal: -100.00,
      tax_amount: 0.00,
      total: -100.00,
      currency: 'INR',
    };

    const result = expenseValidationSchema.safeParse(negativeData);
    expect(result.success).toBe(false);
  });
});
