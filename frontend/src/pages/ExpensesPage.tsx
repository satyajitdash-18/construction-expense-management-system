import { useEffect, useState, useCallback } from 'react';
import { Plus, Search, Eye, Trash2, ArrowUpDown, X, MoreHorizontal, FileText, ChevronLeft, ChevronRight, Receipt } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/Select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/Table';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/DropdownMenu';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/Dialog';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/Form';
import { Badge } from '@/components/ui/Badge';
import { Skeleton } from '@/components/ui/Skeleton';
import { format } from 'date-fns';
import { api } from '@/services/api';
import type { Expense, Project, Vendor, ExpenseCategory } from '@/types/api';
import { useForm, useFieldArray } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useToast } from '@/hooks/use-toast';

const expenseSchema = z.object({
  project_id: z.string().min(1, 'Please select a project'),
  transaction_date: z.string().min(1, 'Transaction date is required'),
  subtotal: z.coerce.number().min(0.01, 'Subtotal must be greater than 0'),
  tax_amount: z.coerce.number().min(0, 'Tax amount cannot be negative'),
  total: z.coerce.number().min(0.01, 'Total must be greater than 0'),
  currency: z.string().default('INR'),
  payment_method: z.enum(['CASH', 'UPI', 'BANK_TRANSFER', 'CARD', 'CHEQUE', 'OTHER']).default('CASH'),
  vendor_id: z.string().optional(),
  category_id: z.string().optional(),
  vendor_name: z.string().optional(),
  gstin_supplier: z.string().optional(),
  hsn_sac_code: z.string().optional(),
  cgst_amount: z.coerce.number().optional(),
  sgst_amount: z.coerce.number().optional(),
  igst_amount: z.coerce.number().optional(),
  irn: z.string().optional(),
  line_items: z.array(z.object({
    description: z.string().min(1, 'Description is required'),
    quantity: z.coerce.number().optional(),
    unit_price: z.coerce.number().optional(),
    amount: z.coerce.number().min(0.01, 'Amount must be greater than 0'),
    tax_amount: z.coerce.number().optional(),
  })).optional(),
}).refine(
  (data) => Math.abs((Number(data.subtotal) + Number(data.tax_amount || 0)) - Number(data.total)) <= 0.05,
  {
    message: 'Subtotal + Tax Amount must equal Total',
    path: ['total'],
  }
);

type ExpenseFormData = z.infer<typeof expenseSchema>;

type SortField = 'transaction_date' | 'project_id' | 'vendor_id' | 'total' | 'lifecycle_status' | 'payment_method';

const getStatusVariant = (status: string) => {
  switch (status) {
    case 'POSTED':
    case 'RECONCILED':
    case 'VALIDATED':
      return 'success' as const;
    case 'REJECTED':
    case 'FAILED':
      return 'destructive' as const;
    default:
      return 'default' as const;
  }
};

export default function ExpensesPage() {
  const [expenses, setExpenses] = useState<Expense[]>([]);
  const [loading, setLoading] = useState(true);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const pageSize = 10;
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [projectFilter, setProjectFilter] = useState('');
  const [vendorFilter, setVendorFilter] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [sortField, setSortField] = useState<SortField>('transaction_date');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingExpense, setEditingExpense] = useState<Expense | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);
  const [selectedExpense, setSelectedExpense] = useState<Expense | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [vendors, setVendors] = useState<Vendor[]>([]);
  const [categories, setCategories] = useState<ExpenseCategory[]>([]);
  const { toast } = useToast();

  const form = useForm<ExpenseFormData>({
    resolver: zodResolver(expenseSchema) as unknown as import('react-hook-form').Resolver<ExpenseFormData>,
    defaultValues: {
      currency: 'INR',
      payment_method: 'CASH',
      subtotal: 0,
      tax_amount: 0,
      total: 0,
      line_items: [],
    },
  });

  const { reset, control } = form;
  const { fields, append, remove } = useFieldArray({
    control,
    name: 'line_items',
  });

  const fetchExpenses = useCallback(async () => {
    setLoading(true);
    try {
      const response = await api.getExpenses({
        page,
        page_size: pageSize,
        status: statusFilter || undefined,
        project_id: projectFilter || undefined,
        vendor_id: vendorFilter || undefined,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
      });
      setExpenses(response.items || []);
      setTotal(response.total || 0);
    } catch (error) {
      console.error('Failed to fetch expenses:', error);
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, statusFilter, projectFilter, vendorFilter, dateFrom, dateTo]);

  const fetchDropdowns = useCallback(async () => {
    try {
      const [projectsRes, vendorsRes, categoriesRes] = await Promise.all([
        api.getProjects({ page_size: 100 }),
        api.getVendors({ page_size: 100 }),
        api.getCategories(),
      ]);
      setProjects(projectsRes.items || []);
      setVendors(vendorsRes.items || []);
      setCategories(categoriesRes || []);
    } catch (error) {
      console.error('Failed to fetch dropdowns:', error);
    }
  }, []);

  useEffect(() => {
    fetchExpenses();
  }, [fetchExpenses]);

  useEffect(() => {
    fetchDropdowns();
  }, [fetchDropdowns]);

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDir('asc');
    }
  };

  const sortedExpenses = [...expenses].sort((a, b) => {
    const aVal = a[sortField] ?? '';
    const bVal = b[sortField] ?? '';
    if (typeof aVal === 'number' && typeof bVal === 'number') {
      return sortDir === 'asc' ? aVal - bVal : bVal - aVal;
    }
    const aStr = String(aVal).toLowerCase();
    const bStr = String(bVal).toLowerCase();
    return sortDir === 'asc' ? aStr.localeCompare(bStr) : bStr.localeCompare(aStr);
  });

  const onExpenseSubmit = async (data: ExpenseFormData) => {
    try {
      if (editingExpense) {
        await api.updateExpense(editingExpense.id, data);
        toast({ title: 'Expense updated', description: 'Expense has been updated successfully' });
      } else {
        await api.createExpense(data);
        toast({ title: 'Expense created', description: 'Expense has been created successfully' });
      }
      setDialogOpen(false);
      setEditingExpense(null);
      fetchExpenses();
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to save expense';
      toast({ title: 'Error', description: message, variant: 'destructive' });
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await api.deleteExpense(id);
      setDeleteConfirm(null);
      fetchExpenses();
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to delete expense';
      toast({ title: 'Error', description: message, variant: 'destructive' });
    }
  };

  const handleEdit = (expense: Expense) => {
    setEditingExpense(expense);
    reset({
      project_id: expense.project_id,
      transaction_date: expense.transaction_date.split('T')[0],
      subtotal: expense.subtotal,
      tax_amount: expense.tax_amount,
      total: expense.total,
      currency: expense.currency,
      payment_method: expense.payment_method,
      vendor_id: expense.vendor_id || '',
      category_id: expense.category_id || '',
      vendor_name: (expense as { vendor_name?: string }).vendor_name || '',
      gstin_supplier: expense.gstin_supplier || '',
      hsn_sac_code: expense.hsn_sac_code || '',
      cgst_amount: expense.cgst_amount || 0,
      sgst_amount: expense.sgst_amount || 0,
      igst_amount: expense.igst_amount || 0,
      irn: expense.irn || '',
      line_items: (expense.line_items || []).map(li => ({
        description: li.description,
        quantity: li.quantity ?? undefined,
        unit_price: li.unit_price ?? undefined,
        amount: li.amount,
        tax_amount: li.tax_amount ?? undefined,
      })),
    });
    setDialogOpen(true);
  };

  const clearFilters = () => {
    setSearch('');
    setStatusFilter('');
    setProjectFilter('');
    setVendorFilter('');
    setDateFrom('');
    setDateTo('');
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Expenses</h1>
          <p className="text-muted-foreground">Manage and track your construction expenses</p>
        </div>
        <Button onClick={() => { setEditingExpense(null); reset(); setDialogOpen(true); }}>
          <Plus className="mr-2 h-4 w-4" />
          New Expense
        </Button>
      </div>

      {/* Search and Filters */}
      <div className="flex flex-col sm:flex-row gap-4 mb-6 flex-wrap">
        <div className="flex-1 relative min-w-[200px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search expenses..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-10"
          />
        </div>
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="w-[180px]">
            <SelectValue placeholder="All Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="">All Status</SelectItem>
            <SelectItem value="RECEIVED">Received</SelectItem>
            <SelectItem value="VALIDATED">Validated</SelectItem>
            <SelectItem value="PROCESSING">Processing</SelectItem>
            <SelectItem value="EXTRACTED">Extracted</SelectItem>
            <SelectItem value="NEEDS_CONFIRMATION">Needs Confirmation</SelectItem>
            <SelectItem value="STAGED">Staged</SelectItem>
            <SelectItem value="RECONCILING">Reconciling</SelectItem>
            <SelectItem value="RECONCILED">Reconciled</SelectItem>
            <SelectItem value="POSTED">Posted</SelectItem>
            <SelectItem value="FAILED">Failed</SelectItem>
            <SelectItem value="REJECTED">Rejected</SelectItem>
          </SelectContent>
        </Select>
        <Select value={projectFilter} onValueChange={setProjectFilter}>
          <SelectTrigger className="w-[180px]">
            <SelectValue placeholder="All Projects" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="">All Projects</SelectItem>
            {projects.map(p => <SelectItem key={p.id} value={p.id}>{p.name} ({p.code})</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={vendorFilter} onValueChange={setVendorFilter}>
          <SelectTrigger className="w-[180px]">
            <SelectValue placeholder="All Vendors" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="">All Vendors</SelectItem>
            {vendors.map(v => <SelectItem key={v.id} value={v.id}>{v.name}</SelectItem>)}
          </SelectContent>
        </Select>
        <div className="flex gap-2">
          <Input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)} className="w-[140px]" />
          <Input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)} className="w-[140px]" />
        </div>
        <Button variant="outline" size="icon" onClick={clearFilters}>
          <X className="h-4 w-4" />
          <span className="sr-only">Clear filters</span>
        </Button>
      </div>

      {/* Expenses Table */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>Expenses ({total})</CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="space-y-4">
              {[1, 2, 3, 4, 5].map((i) => (
                <Skeleton key={i} className="h-12" />
              ))}
            </div>
          ) : expenses.length === 0 ? (
            <div className="text-center py-12">
              <Receipt className="h-12 w-12 mx-auto text-muted-foreground" />
              <h3 className="mt-4 text-lg font-medium">No expenses found</h3>
              <p className="text-muted-foreground mt-2">Get started by creating your first expense</p>
              <Button className="mt-4" onClick={() => { reset(); setDialogOpen(true); }}>
                <Plus className="mr-2 h-4 w-4" />
                Create Expense
              </Button>
            </div>
          ) : (
            <>
              <div className="rounded-md border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="cursor-pointer" onClick={() => handleSort('transaction_date')}>
                        <span className="flex items-center">Date <ArrowUpDown className="ml-1 h-4 w-4" /></span>
                      </TableHead>
                      <TableHead className="cursor-pointer" onClick={() => handleSort('project_id')}>
                        <span className="flex items-center">Project <ArrowUpDown className="ml-1 h-4 w-4" /></span>
                      </TableHead>
                      <TableHead className="cursor-pointer" onClick={() => handleSort('vendor_id')}>
                        <span className="flex items-center">Vendor <ArrowUpDown className="ml-1 h-4 w-4" /></span>
                      </TableHead>
                      <TableHead className="cursor-pointer text-right" onClick={() => handleSort('total')}>
                        <span className="flex items-center justify-end">Amount <ArrowUpDown className="ml-1 h-4 w-4" /></span>
                      </TableHead>
                      <TableHead className="cursor-pointer" onClick={() => handleSort('lifecycle_status')}>
                        <span className="flex items-center">Status <ArrowUpDown className="ml-1 h-4 w-4" /></span>
                      </TableHead>
                      <TableHead className="cursor-pointer" onClick={() => handleSort('payment_method')}>
                        <span className="flex items-center">Payment <ArrowUpDown className="ml-1 h-4 w-4" /></span>
                      </TableHead>
                      <TableHead className="text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {sortedExpenses.map((expense) => (
                      <TableRow key={expense.id}>
                        <TableCell>{format(new Date(expense.transaction_date), 'PP')}</TableCell>
                        <TableCell>{expense.project?.name || 'N/A'}</TableCell>
                        <TableCell>{expense.vendor?.name || expense.vendor_name || 'N/A'}</TableCell>
                        <TableCell className="text-right font-medium">
                          {new Intl.NumberFormat('en-IN', {
                            style: 'currency',
                            currency: expense.currency || 'INR',
                            minimumFractionDigits: 0,
                          }).format(expense.total)}
                        </TableCell>
                        <TableCell>
                          <Badge variant={getStatusVariant(expense.lifecycle_status)}>
                            {(expense.lifecycle_status || '').replace(/_/g, ' ')}
                          </Badge>
                        </TableCell>
                        <TableCell>{(expense.payment_method || '').replace(/_/g, ' ')}</TableCell>
                        <TableCell className="text-right">
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <Button variant="ghost" size="icon"><MoreHorizontal className="h-4 w-4" /></Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end">
                              <DropdownMenuItem onClick={() => handleEdit(expense)}>
                                <Eye className="mr-2 h-4 w-4" /> View / Edit
                              </DropdownMenuItem>
                              <DropdownMenuItem onClick={() => setSelectedExpense(expense)} disabled={!expense.evidence_files?.length}>
                                <FileText className="mr-2 h-4 w-4" /> Evidence
                              </DropdownMenuItem>
                              <DropdownMenuSeparator />
                              <DropdownMenuItem onClick={() => setDeleteConfirm(expense.id)} className="text-red-600">
                                <Trash2 className="mr-2 h-4 w-4" /> Delete
                              </DropdownMenuItem>
                            </DropdownMenuContent>
                          </DropdownMenu>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
              <div className="flex items-center justify-between mt-4">
                <span className="text-sm text-muted-foreground">
                  Showing {((page - 1) * pageSize) + 1} to {Math.min(page * pageSize, total)} of {total} expenses
                </span>
                <div className="flex gap-2">
                  <Button variant="outline" size="sm" onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}>
                    <ChevronLeft className="h-4 w-4" />
                  </Button>
                  <span className="px-3">{page} / {Math.ceil(total / pageSize)}</span>
                  <Button variant="outline" size="sm" onClick={() => setPage(p => Math.min(Math.ceil(total / pageSize), p + 1))} disabled={page >= Math.ceil(total / pageSize)}>
                    <ChevronRight className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            </>
          )}
        </CardContent>
      </Card>

      {/* Evidence viewer placeholder */}
      {selectedExpense && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-background p-6 rounded-lg shadow-lg max-w-md w-full mx-4">
            <h3 className="text-lg font-semibold mb-2">Evidence Files</h3>
            <p className="text-muted-foreground mb-4">Files for expense: {selectedExpense.id}</p>
            <Button onClick={() => setSelectedExpense(null)}>Close</Button>
          </div>
        </div>
      )}

      {/* Create/Edit Expense Dialog */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="sm:max-w-[700px] max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{editingExpense ? 'Edit Expense' : 'Create Expense'}</DialogTitle>
            <DialogDescription>{editingExpense ? 'Update expense details' : 'Create a new expense record'}</DialogDescription>
          </DialogHeader>
          <Form {...form}>
            <form onSubmit={form.handleSubmit(onExpenseSubmit)} className="space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <FormField
                  control={form.control}
                  name="project_id"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Project *</FormLabel>
                      <FormControl>
                        <Select onValueChange={field.onChange} defaultValue={field.value}>
                          <SelectTrigger>
                            <SelectValue placeholder="Select project" />
                          </SelectTrigger>
                          <SelectContent>
                            {projects.map(p => <SelectItem key={p.id} value={p.id}>{p.name} ({p.code})</SelectItem>)}
                          </SelectContent>
                        </Select>
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="transaction_date"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Transaction Date *</FormLabel>
                      <FormControl>
                        <Input type="date" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="subtotal"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Subtotal *</FormLabel>
                      <FormControl>
                        <Input type="number" step="0.01" min="0.01" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="tax_amount"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Tax Amount</FormLabel>
                      <FormControl>
                        <Input type="number" step="0.01" min="0" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="total"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Total *</FormLabel>
                      <FormControl>
                        <Input type="number" step="0.01" min="0.01" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="currency"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Currency</FormLabel>
                      <FormControl>
                        <Select onValueChange={field.onChange} defaultValue={field.value}>
                          <SelectTrigger>
                            <SelectValue placeholder="Select currency" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="INR">INR - Indian Rupee</SelectItem>
                            <SelectItem value="USD">USD - US Dollar</SelectItem>
                            <SelectItem value="EUR">EUR - Euro</SelectItem>
                          </SelectContent>
                        </Select>
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="payment_method"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Payment Method</FormLabel>
                      <FormControl>
                        <Select onValueChange={field.onChange} defaultValue={field.value}>
                          <SelectTrigger>
                            <SelectValue placeholder="Select payment method" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="CASH">Cash</SelectItem>
                            <SelectItem value="UPI">UPI</SelectItem>
                            <SelectItem value="BANK_TRANSFER">Bank Transfer</SelectItem>
                            <SelectItem value="CARD">Card</SelectItem>
                            <SelectItem value="CHEQUE">Cheque</SelectItem>
                            <SelectItem value="OTHER">Other</SelectItem>
                          </SelectContent>
                        </Select>
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="vendor_id"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Vendor</FormLabel>
                      <FormControl>
                        <Select onValueChange={field.onChange} defaultValue={field.value}>
                          <SelectTrigger>
                            <SelectValue placeholder="Select vendor" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="">None</SelectItem>
                            {vendors.map(v => <SelectItem key={v.id} value={v.id}>{v.name}</SelectItem>)}
                          </SelectContent>
                        </Select>
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="category_id"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Category</FormLabel>
                      <FormControl>
                        <Select onValueChange={field.onChange} defaultValue={field.value}>
                          <SelectTrigger>
                            <SelectValue placeholder="Select category" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="">None</SelectItem>
                            {categories.map(c => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}
                          </SelectContent>
                        </Select>
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="vendor_name"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Vendor Name (Manual)</FormLabel>
                      <FormControl>
                        <Input placeholder="Enter vendor name if not in list" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="gstin_supplier"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>GSTIN Supplier</FormLabel>
                      <FormControl>
                        <Input placeholder="GSTIN of supplier" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="hsn_sac_code"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>HSN/SAC Code</FormLabel>
                      <FormControl>
                        <Input placeholder="HSN/SAC code" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <div className="grid gap-4 md:grid-cols-3 md:col-span-2">
                  {(['cgst_amount', 'sgst_amount', 'igst_amount'] as const).map((fieldName) => (
                    <FormField
                      key={fieldName}
                      control={form.control}
                      name={fieldName}
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>{fieldName.replace('_amount', '').toUpperCase()} Amount</FormLabel>
                          <FormControl>
                            <Input type="number" step="0.01" min="0" {...field} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  ))}
                </div>
                <FormField
                  control={form.control}
                  name="irn"
                  render={({ field }) => (
                    <FormItem className="md:col-span-2">
                      <FormLabel>IRN</FormLabel>
                      <FormControl>
                        <Input placeholder="Invoice Reference Number" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>

              {/* Line Items */}
              <div className="space-y-4 border-t pt-6">
                <div className="flex items-center justify-between">
                  <h3 className="text-lg font-semibold">Line Items</h3>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => append({ description: '', quantity: 1, unit_price: 0, amount: 0, tax_amount: 0 })}
                  >
                    <Plus className="mr-2 h-4 w-4" />
                    Add Line Item
                  </Button>
                </div>
                <div className="space-y-3">
                  {fields.map((fieldItem, index) => (
                    <div key={fieldItem.id} className="grid gap-3 md:grid-cols-5 p-4 border rounded-lg bg-gray-50 items-end">
                      <FormField
                        control={form.control}
                        name={`line_items.${index}.description`}
                        render={({ field }) => (
                          <FormItem className="md:col-span-2">
                            <FormLabel>Description *</FormLabel>
                            <FormControl>
                              <Input placeholder="Item description" {...field} />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                      <FormField
                        control={form.control}
                        name={`line_items.${index}.quantity`}
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel>Quantity</FormLabel>
                            <FormControl>
                              <Input type="number" step="0.001" min="0" {...field} />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                      <FormField
                        control={form.control}
                        name={`line_items.${index}.unit_price`}
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel>Unit Price</FormLabel>
                            <FormControl>
                              <Input type="number" step="0.01" min="0" {...field} />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                      <div className="flex items-center gap-2">
                        <FormField
                          control={form.control}
                          name={`line_items.${index}.amount`}
                          render={({ field }) => (
                            <FormItem className="flex-1">
                              <FormLabel>Amount</FormLabel>
                              <FormControl>
                                <Input type="number" step="0.01" min="0" {...field} />
                              </FormControl>
                              <FormMessage />
                            </FormItem>
                          )}
                        />
                        <Button
                          type="button"
                          variant="destructive"
                          size="icon"
                          onClick={() => remove(index)}
                          className="h-10 w-10 shrink-0 mb-1"
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <DialogFooter className="flex justify-end gap-2 pt-4">
                <Button type="button" variant="outline" onClick={() => { setDialogOpen(false); reset(); setEditingExpense(null); }}>
                  Cancel
                </Button>
                <Button type="submit">
                  {editingExpense ? 'Update' : 'Create'}
                </Button>
              </DialogFooter>
            </form>
          </Form>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={!!deleteConfirm} onOpenChange={(open) => { if (!open) setDeleteConfirm(null); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Expense</DialogTitle>
            <DialogDescription>Are you sure you want to delete this expense? This action cannot be undone.</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteConfirm(null)}>Cancel</Button>
            <Button variant="destructive" onClick={() => { if (deleteConfirm) { handleDelete(deleteConfirm); } }}>
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}