import { useEffect, useState, useCallback } from 'react';
import {
  Search, Link, Trash2, MoreHorizontal, Eye, Check,
  ArrowUpDown, RefreshCw, ChevronLeft, ChevronRight
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/Select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/Table';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/DropdownMenu';
import { Badge } from '@/components/ui/Badge';
import { Skeleton } from '@/components/ui/Skeleton';
import { api } from '@/services/api';
import type { ReconciliationRecord } from '@/types/api';
import { useToast } from '@/hooks/use-toast';
import { formatDistanceToNow } from 'date-fns';

type SortField = 'expense_id' | 'payment_event_id' | 'status' | 'match_basis' | 'match_score' | 'created_at';

export default function ReconciliationPage() {
  const [records, setRecords] = useState<ReconciliationRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const pageSize = 10;
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [projectFilter, setProjectFilter] = useState('');
  const [sortField, setSortField] = useState<SortField>('created_at');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);
  const { toast } = useToast();

  const fetchRecords = useCallback(async () => {
    setLoading(true);
    try {
      const response = await api.getReconciliations({
        page,
        page_size: pageSize,
        status: statusFilter || undefined,
        project_id: projectFilter || undefined,
      });
      setRecords(response.items || []);
      setTotal(response.total || 0);
    } catch (error) {
      console.error('Failed to fetch reconciliations:', error);
    } finally {
      setLoading(false);
    }
  }, [page, statusFilter, projectFilter]);

  useEffect(() => {
    fetchRecords();
  }, [fetchRecords]);

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDir('asc');
    }
  };

  const sortedRecords = [...records].sort((a, b) => {
    const aVal = a[sortField] ?? '';
    const bVal = b[sortField] ?? '';
    if (typeof aVal === 'number' && typeof bVal === 'number') {
      return sortDir === 'asc' ? aVal - bVal : bVal - aVal;
    }
    const aStr = String(aVal).toLowerCase();
    const bStr = String(bVal).toLowerCase();
    return sortDir === 'asc' ? aStr.localeCompare(bStr) : bStr.localeCompare(aStr);
  });

  const handleAutoMatch = async () => {
    try {
      const result = await api.autoMatchBatch({ project_id: projectFilter || undefined, confidence_threshold: 0.8 });
      toast({ title: 'Auto-match completed', description: `Processed ${result.processed} records, matched ${result.matched}` });
      fetchRecords();
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to auto-match';
      toast({ title: 'Error', description: message, variant: 'destructive' });
    }
  };

  const handleUnmatch = async (recordId: string) => {
    try {
      await api.unmatchReconciliation(recordId, 'Manual unmatch');
      toast({ title: 'Unmatched', description: 'Reconciliation has been unmatched' });
      fetchRecords();
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to unmatch';
      toast({ title: 'Error', description: message, variant: 'destructive' });
    }
  };

  const handleDeleteConfirm = async (id: string) => {
    try {
      await api.getReconciliation(id); // verify it exists; real delete is via unmatch
      setDeleteConfirm(null);
      toast({ title: 'Action taken', description: 'Record processed' });
      fetchRecords();
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to process';
      toast({ title: 'Error', description: message, variant: 'destructive' });
    }
  };

  const getStatusVariant = (status: string) => {
    switch (status) {
      case 'MATCHED': return 'success' as const;
      case 'UNMATCHED': return 'destructive' as const;
      case 'AMBIGUOUS': return 'warning' as const;
      default: return 'secondary' as const;
    }
  };

  if (loading && records.length === 0) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <Skeleton className="h-8 w-48" />
            <Skeleton className="h-4 w-64 mt-2" />
          </div>
        </div>
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          {[1, 2, 3, 4].map((i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Reconciliation</h1>
          <p className="text-muted-foreground">Match expenses with payment events</p>
        </div>
        <div className="flex gap-2">
          <Button onClick={handleAutoMatch}>
            <RefreshCw className="mr-2 h-4 w-4" />
            Auto Match
          </Button>
        </div>
      </div>

      {/* Search and Filters */}
      <div className="flex flex-col sm:flex-row gap-4 mb-6">
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search reconciliations..."
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
            <SelectItem value="MATCHED">Matched</SelectItem>
            <SelectItem value="UNMATCHED">Unmatched</SelectItem>
            <SelectItem value="AMBIGUOUS">Ambiguous</SelectItem>
            <SelectItem value="MANUALLY_RESOLVED">Manually Resolved</SelectItem>
          </SelectContent>
        </Select>
        <Select value={projectFilter} onValueChange={setProjectFilter}>
          <SelectTrigger className="w-[180px]">
            <SelectValue placeholder="All Projects" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="">All Projects</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Reconciliation Table */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>Reconciliation Records ({total})</CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="space-y-4">
              {[1, 2, 3, 4, 5].map((i) => (
                <Skeleton key={i} className="h-12" />
              ))}
            </div>
          ) : records.length === 0 ? (
            <div className="text-center py-12">
              <Link className="h-12 w-12 mx-auto text-muted-foreground" />
              <h3 className="mt-4 text-lg font-medium">No reconciliation records found</h3>
              <p className="text-muted-foreground mt-2">No matching records found</p>
            </div>
          ) : (
            <>
              <div className="rounded-md border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="cursor-pointer" onClick={() => handleSort('expense_id')}>
                        <span className="flex items-center">Expense <ArrowUpDown className="ml-1 h-4 w-4" /></span>
                      </TableHead>
                      <TableHead className="cursor-pointer" onClick={() => handleSort('payment_event_id')}>
                        <span className="flex items-center">Payment <ArrowUpDown className="ml-1 h-4 w-4" /></span>
                      </TableHead>
                      <TableHead className="cursor-pointer" onClick={() => handleSort('status')}>
                        <span className="flex items-center">Status <ArrowUpDown className="ml-1 h-4 w-4" /></span>
                      </TableHead>
                      <TableHead className="cursor-pointer" onClick={() => handleSort('match_basis')}>
                        <span className="flex items-center">Match Basis <ArrowUpDown className="ml-1 h-4 w-4" /></span>
                      </TableHead>
                      <TableHead className="cursor-pointer" onClick={() => handleSort('match_score')}>
                        <span className="flex items-center">Score <ArrowUpDown className="ml-1 h-4 w-4" /></span>
                      </TableHead>
                      <TableHead className="cursor-pointer" onClick={() => handleSort('created_at')}>
                        <span className="flex items-center">Created <ArrowUpDown className="ml-1 h-4 w-4" /></span>
                      </TableHead>
                      <TableHead className="text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {sortedRecords.map((record) => (
                      <TableRow key={record.id}>
                        <TableCell>{record.expense?.project?.code || record.expense_id}</TableCell>
                        <TableCell>{record.payment_event?.upi_reference || record.payment_event?.bank_reference || 'N/A'}</TableCell>
                        <TableCell>
                          <Badge variant={getStatusVariant(record.status)}>
                            {record.status.replace('_', ' ')}
                          </Badge>
                        </TableCell>
                        <TableCell>{record.match_basis || '—'}</TableCell>
                        <TableCell>{record.match_score ? (record.match_score * 100).toFixed(1) + '%' : '—'}</TableCell>
                        <TableCell>{formatDistanceToNow(new Date(record.created_at), { addSuffix: true })}</TableCell>
                        <TableCell className="text-right">
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <Button variant="ghost" size="icon"><MoreHorizontal className="h-4 w-4" /></Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end">
                              {record.status === 'UNMATCHED' && (
                                <DropdownMenuItem onClick={() => { /* open reconcile dialog */ }}>
                                  <Check className="mr-2 h-4 w-4" /> Reconcile
                                </DropdownMenuItem>
                              )}
                              <DropdownMenuItem onClick={() => { /* view details */ }}>
                                <Eye className="mr-2 h-4 w-4" /> View Details
                              </DropdownMenuItem>
                              {record.status === 'MATCHED' && (
                                <DropdownMenuItem onClick={() => handleUnmatch(record.id)}>
                                  <RefreshCw className="mr-2 h-4 w-4" /> Unmatch
                                </DropdownMenuItem>
                              )}
                              <DropdownMenuSeparator />
                              <DropdownMenuItem onClick={() => setDeleteConfirm(record.id)} className="text-red-600">
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
                  Showing {((page - 1) * pageSize) + 1} to {Math.min(page * pageSize, total)} of {total} records
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

      {/* Delete Confirmation */}
      {deleteConfirm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-background p-6 rounded-lg shadow-lg max-w-md w-full mx-4">
            <h3 className="text-lg font-semibold mb-2">Confirm Action</h3>
            <p className="text-muted-foreground mb-4">Are you sure you want to process this record?</p>
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setDeleteConfirm(null)}>Cancel</Button>
              <Button variant="destructive" onClick={() => handleDeleteConfirm(deleteConfirm)}>Confirm</Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}