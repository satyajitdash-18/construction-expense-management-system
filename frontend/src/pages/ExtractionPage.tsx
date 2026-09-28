import { useEffect, useState } from 'react';
import { Search, Sparkles, Eye, Download, Trash2, MoreHorizontal, ArrowUpDown, Upload, RefreshCw, ChevronLeft, ChevronRight } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/Select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/Table';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/DropdownMenu';
import { Skeleton } from '@/components/ui/Skeleton';
import { Badge } from '@/components/ui/Badge';
import { api } from '@/services/api';
import { formatDistanceToNow } from 'date-fns';

export default function ExtractionPage() {
  const [jobs, setJobs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const pageSize = 10;
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');

  useEffect(() => {
    fetchJobs();
  }, [page, search, statusFilter]);

  const fetchJobs = async () => {
    setLoading(true);
    try {
      const response = await api.getExtractionJobs({ page, page_size: pageSize, status: statusFilter || undefined });
      setJobs(response.items || []);
      setTotal(response.total || 0);
    } catch (error) {
      console.error('Failed to fetch extraction jobs:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleSort = (_field: string) => {
    // sort handled client-side in future
  };

  const getStatusVariant = (status: string) => {
    switch (status) {
      case 'SUCCEEDED': return 'success' as const;
      case 'FAILED': return 'destructive' as const;
      case 'RUNNING': return 'default' as const;
      default: return 'secondary' as const;
    }
  };

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <Skeleton className="h-8 w-48" />
            <Skeleton className="h-4 w-64 mt-2" />
          </div>
        </div>
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          {[1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-24" />)}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">LLM Extraction</h1>
          <p className="text-muted-foreground">Extract structured data from receipts and invoices using AI</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => { /* upload evidence first */ }}>
            <Upload className="mr-2 h-4 w-4" />
            Upload & Extract
          </Button>
        </div>
      </div>

      {/* Search and Filters */}
      <div className="flex flex-col sm:flex-row gap-4 mb-6">
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search extraction jobs..."
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
            <SelectItem value="PENDING">Pending</SelectItem>
            <SelectItem value="RUNNING">Running</SelectItem>
            <SelectItem value="SUCCEEDED">Succeeded</SelectItem>
            <SelectItem value="FAILED">Failed</SelectItem>
            <SelectItem value="RETRYING">Retrying</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Extraction Jobs Table */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>Extraction Jobs ({total})</CardTitle>
        </CardHeader>
        <CardContent>
          {jobs.length === 0 ? (
            <div className="text-center py-12">
              <Sparkles className="h-12 w-12 mx-auto text-muted-foreground" />
              <h3 className="mt-4 text-lg font-medium">No extraction jobs found</h3>
              <p className="text-muted-foreground mt-2">Upload a receipt or invoice to start AI extraction</p>
            </div>
          ) : (
            <>
              <div className="rounded-md border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="cursor-pointer" onClick={() => handleSort('created_at')}>
                        <span className="flex items-center">Created <ArrowUpDown className="ml-1 h-4 w-4" /></span>
                      </TableHead>
                      <TableHead className="cursor-pointer" onClick={() => handleSort('status')}>
                        <span className="flex items-center">Status <ArrowUpDown className="ml-1 h-4 w-4" /></span>
                      </TableHead>
                      <TableHead>Evidence</TableHead>
                      <TableHead>Source Event</TableHead>
                      <TableHead>Model</TableHead>
                      <TableHead>Confidence</TableHead>
                      <TableHead className="text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {jobs.map((job) => (
                      <TableRow key={job.id}>
                        <TableCell>
                          {job.created_at ? formatDistanceToNow(new Date(job.created_at), { addSuffix: true }) : 'N/A'}
                        </TableCell>
                        <TableCell>
                          <Badge variant={getStatusVariant(job.status)}>
                            {job.status}
                          </Badge>
                        </TableCell>
                        <TableCell>{job.evidence?.file_name || 'N/A'}</TableCell>
                        <TableCell>{job.source_event_id || 'N/A'}</TableCell>
                        <TableCell>{job.model || 'N/A'}</TableCell>
                        <TableCell>
                          {job.confidence_score ? (job.confidence_score * 100).toFixed(1) + '%' : 'N/A'}
                        </TableCell>
                        <TableCell className="text-right">
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <Button variant="ghost" size="icon"><MoreHorizontal className="h-4 w-4" /></Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end">
                              {(job.status === 'PENDING' || job.status === 'RUNNING') ? (
                                <DropdownMenuItem onClick={() => { /* retry */ }}>
                                  <RefreshCw className="mr-2 h-4 w-4" /> Retry
                                </DropdownMenuItem>
                              ) : (
                                <DropdownMenuItem onClick={() => { /* view result */ }}>
                                  <Eye className="mr-2 h-4 w-4" /> View Result
                                </DropdownMenuItem>
                              )}
                              <DropdownMenuSeparator />
                              <DropdownMenuItem onClick={() => { /* download */ }}>
                                <Download className="mr-2 h-4 w-4" /> Download Result
                              </DropdownMenuItem>
                              <DropdownMenuSeparator />
                              <DropdownMenuItem onClick={() => { /* delete */ }} className="text-red-600">
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
                  Showing {((page - 1) * pageSize) + 1} to {Math.min(page * pageSize, total)} of {total} jobs
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
    </div>
  );
}