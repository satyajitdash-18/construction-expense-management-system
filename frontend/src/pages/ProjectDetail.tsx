import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Plus } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/Select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/Table';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogDescription, DialogFooter } from '@/components/ui/Dialog';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/Form';
import { Input } from '@/components/ui/Input';
import { format } from 'date-fns';
import { api } from '@/services/api';
import { useToast } from '@/hooks/use-toast';
import { Skeleton } from '@/components/ui/Skeleton';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';

const budgetSchema = z.object({
  category_id: z.string().optional(),
  amount: z.coerce.number().min(0.01, 'Amount must be greater than 0'),
  currency: z.string().default('INR'),
  effective_from: z.string().min(1, 'Effective from date is required'),
  effective_to: z.string().optional(),
});

type BudgetFormData = z.infer<typeof budgetSchema>;

export default function ProjectDetail() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const { toast } = useToast();
  const [project, setProject] = useState<any>(null);
  const [budgetVsActual, setBudgetVsActual] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'details' | 'budget' | 'expenses'>('details');
  const [editingBudget, setEditingBudget] = useState<any | null>(null);
  const [budgetDialogOpen, setBudgetDialogOpen] = useState(false);

  const form = useForm<any>({
    resolver: zodResolver(budgetSchema) as any,
    defaultValues: { currency: 'INR' },
  });
  const { reset } = form;

  const fetchData = async () => {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    try {
      const [projectRes, budgetRes] = await Promise.all([
        api.getProject(projectId),
        api.getProjectBudgets(projectId),
      ]);
      setProject(projectRes);
      setBudgetVsActual(budgetRes);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch project data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [projectId]);

  const onBudgetSubmit = async (data: BudgetFormData) => {
    try {
      if (editingBudget) {
        await api.updateProjectBudget(project.id, editingBudget.id, data);
        toast({ title: 'Budget updated', description: 'Budget has been updated successfully' });
      } else {
        await api.createProjectBudget(project.id, data as any);
        toast({ title: 'Budget created', description: 'Budget has been created successfully' });
      }
      setBudgetDialogOpen(false);
      setEditingBudget(null);
      reset();
      fetchData();
    } catch (error: any) {
      toast({ title: 'Error', description: error.message || 'Failed to save budget', variant: 'destructive' });
    }
  };

  const handleDeleteBudget = async (budgetId: string) => {
    if (!confirm('Are you sure you want to delete this budget?')) return;
    try {
      await api.deleteProjectBudget(project.id, budgetId);
      toast({ title: 'Budget deleted', description: 'Budget has been deleted successfully' });
      fetchData();
    } catch (error: any) {
      toast({ title: 'Error', description: error.message || 'Failed to delete budget', variant: 'destructive' });
    }
  };

  const formatCurrency = (amount: number, currency = 'INR') =>
    new Intl.NumberFormat('en-IN', { style: 'currency', currency, minimumFractionDigits: 0 }).format(amount);

  if (loading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-64" />
        <div className="grid gap-4 md:grid-cols-3">
          {[1, 2, 3].map(i => <Skeleton key={i} className="h-24" />)}
        </div>
      </div>
    );
  }

  if (error || !project) {
    return (
      <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded">
        {error || 'Project not found'}
        <Button variant="ghost" className="ml-4" onClick={() => navigate('/projects')}>
          ← Back to Projects
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">{project.name}</h1>
          <p className="text-muted-foreground">Code: {project.code}</p>
        </div>
        <Button variant="outline" onClick={() => navigate('/projects')}>
          <ArrowLeft className="mr-2 h-4 w-4" />
          Back to Projects
        </Button>
      </div>

      {/* Tab navigation */}
      <div className="border-b border-gray-200">
        <nav className="flex gap-8">
          {(['details', 'budget', 'expenses'] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`py-3 px-1 border-b-2 font-medium text-sm capitalize ${
                activeTab === tab
                  ? 'border-blue-600 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              {tab}
            </button>
          ))}
        </nav>
      </div>

      {/* Details tab */}
      {activeTab === 'details' && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <Card>
            <CardHeader>
              <CardTitle>Project Information</CardTitle>
            </CardHeader>
            <CardContent>
              <dl className="space-y-4">
                <div>
                  <dt className="text-sm text-gray-500">ID</dt>
                  <dd className="text-sm font-mono text-gray-900">{project.id}</dd>
                </div>
                <div>
                  <dt className="text-sm text-gray-500">Code</dt>
                  <dd className="text-sm font-medium text-gray-900">{project.code}</dd>
                </div>
                <div>
                  <dt className="text-sm text-gray-500">Status</dt>
                  <dd className="text-sm">
                    <Badge variant={
                      project.status === 'active' ? 'success' :
                      project.status === 'on_hold' ? 'warning' :
                      project.status === 'completed' ? 'success' : 'secondary'
                    }>
                      {project.status.replace('_', ' ')}
                    </Badge>
                  </dd>
                </div>
                <div>
                  <dt className="text-sm text-gray-500">Created By</dt>
                  <dd className="text-sm font-mono text-gray-900">{project.created_by}</dd>
                </div>
                <div>
                  <dt className="text-sm text-gray-500">Created At</dt>
                  <dd className="text-sm text-gray-900">{format(new Date(project.created_at), 'PPP')}</dd>
                </div>
                {project.updated_at && (
                  <div>
                    <dt className="text-sm text-gray-500">Updated At</dt>
                    <dd className="text-sm text-gray-900">{format(new Date(project.updated_at), 'PPP')}</dd>
                  </div>
                )}
              </dl>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Budget tab */}
      {activeTab === 'budget' && (
        <div className="space-y-6">
          {budgetVsActual && Array.isArray(budgetVsActual) && budgetVsActual.length > 0 && (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              {budgetVsActual.slice(0, 3).map((item: any, i: number) => (
                <Card key={i}>
                  <CardHeader>
                    <CardTitle>{item.category_id || 'Overall'}</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <p className="text-xl font-bold">{formatCurrency(item.budget || 0, item.currency)}</p>
                    <p className="text-sm text-muted-foreground">Actual: {formatCurrency(item.actual || 0, item.currency)}</p>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}

          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle>Budget Entries</CardTitle>
              <Dialog open={budgetDialogOpen} onOpenChange={setBudgetDialogOpen}>
                <DialogTrigger asChild>
                  <Button onClick={() => { setEditingBudget(null); reset(); }}>
                    <Plus className="mr-2 h-4 w-4" />
                    Add Budget
                  </Button>
                </DialogTrigger>
                <DialogContent className="sm:max-w-[500px]">
                  <DialogHeader>
                    <DialogTitle>{editingBudget ? 'Edit Budget' : 'Add Budget Entry'}</DialogTitle>
                    <DialogDescription>
                      {editingBudget ? 'Update budget entry details' : 'Add a new budget entry for this project'}
                    </DialogDescription>
                  </DialogHeader>
                  <Form {...form}>
                    <form onSubmit={form.handleSubmit(onBudgetSubmit)}>
                      <div className="space-y-4 py-4">
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
                                    <SelectItem value="">Overall Project</SelectItem>
                                    <SelectItem value="materials">Materials</SelectItem>
                                    <SelectItem value="labor">Labor</SelectItem>
                                    <SelectItem value="equipment">Equipment</SelectItem>
                                    <SelectItem value="transport">Transport</SelectItem>
                                    <SelectItem value="permits">Permits</SelectItem>
                                    <SelectItem value="other">Other</SelectItem>
                                  </SelectContent>
                                </Select>
                              </FormControl>
                              <FormMessage />
                            </FormItem>
                          )}
                        />
                        <FormField
                          control={form.control}
                          name="amount"
                          render={({ field }) => (
                            <FormItem>
                              <FormLabel>Amount</FormLabel>
                              <FormControl>
                                <Input type="number" step="0.01" min="0.01" placeholder="Enter amount" {...field} />
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
                          name="effective_from"
                          render={({ field }) => (
                            <FormItem>
                              <FormLabel>Effective From</FormLabel>
                              <FormControl>
                                <Input type="date" {...field} />
                              </FormControl>
                              <FormMessage />
                            </FormItem>
                          )}
                        />
                        <FormField
                          control={form.control}
                          name="effective_to"
                          render={({ field }) => (
                            <FormItem>
                              <FormLabel>Effective To (Optional)</FormLabel>
                              <FormControl>
                                <Input type="date" {...field} />
                              </FormControl>
                              <FormMessage />
                            </FormItem>
                          )}
                        />
                      </div>
                      <DialogFooter className="flex justify-end gap-2">
                        <Button type="button" variant="outline" onClick={() => { setBudgetDialogOpen(false); reset(); }}>
                          Cancel
                        </Button>
                        <Button type="submit">Save Budget</Button>
                      </DialogFooter>
                    </form>
                  </Form>
                </DialogContent>
              </Dialog>
            </CardHeader>
            <CardContent>
              {Array.isArray(budgetVsActual) && budgetVsActual.length > 0 ? (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Category</TableHead>
                      <TableHead className="text-right">Budget</TableHead>
                      <TableHead className="text-right">Actual</TableHead>
                      <TableHead className="text-right">Variance</TableHead>
                      <TableHead>Period</TableHead>
                      <TableHead>Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {budgetVsActual.map((item: any, index: number) => (
                      <TableRow key={index}>
                        <TableCell className="font-medium">
                          {item.category_id ? `Category: ${item.category_id}` : 'Overall Project'}
                        </TableCell>
                        <TableCell className="text-right">{formatCurrency(item.budget || 0, item.currency)}</TableCell>
                        <TableCell className="text-right">{formatCurrency(item.actual || 0, item.currency)}</TableCell>
                        <TableCell className="text-right font-medium">
                          <span className={(item.variance || 0) >= 0 ? 'text-green-600' : 'text-red-600'}>
                            {formatCurrency(item.variance || 0, item.currency)}
                          </span>
                        </TableCell>
                        <TableCell className="text-gray-500">
                          {item.effective_from && item.effective_to
                            ? `${item.effective_from} → ${item.effective_to}`
                            : item.effective_from
                            ? `From ${item.effective_from}`
                            : 'All time'}
                        </TableCell>
                        <TableCell>
                          <Button variant="ghost" size="sm" onClick={() => handleDeleteBudget(item.id)}>
                            Delete
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              ) : (
                <div className="text-center py-8 text-muted-foreground">
                  No budget entries yet. Click "Add Budget" to create one.
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {/* Expenses tab */}
      {activeTab === 'expenses' && (
        <Card>
          <CardHeader>
            <CardTitle>Project Expenses</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-center py-8 text-muted-foreground">
              View all expenses for this project in the <a href="/expenses" className="text-primary hover:underline">Expenses page</a> filtered by this project.
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}