import { useEffect, useState } from 'react';
import { 
  Plus, 
  Shield, 
  FileText, 
  Download, 
  Trash2, 
  CheckCircle, 
  X, 
  MoreHorizontal, 
  Play 
} from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/DropdownMenu';
import { Badge } from '@/components/ui/Badge';
import { Skeleton } from '@/components/ui/Skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/Tabs';
import { api } from '@/services/api';
import { useToast } from '@/hooks/use-toast';

export default function AuditCompliancePage() {
  const [activeTab, setActiveTab] = useState<'policies' | 'gdpr' | 'reports' | 'dashboard'>('dashboard');
  const [loading, setLoading] = useState(true);
  const [policies, setPolicies] = useState<any[]>([]);
  const [gdprRequests, setGdprRequests] = useState<any[]>([]);
  const [reports, setReports] = useState<any[]>([]);
  const [stats, setStats] = useState<any>(null);
  const { toast } = useToast();

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [policiesRes, gdprRes, reportsRes, statsRes] = await Promise.all([
        api.getRetentionPolicies().catch(() => []),
        api.getGdprRequests().catch(() => ({ items: [] })),
        api.getAuditReports().catch(() => []),
        api.getComplianceDashboard().catch(() => null),
      ]);
      setPolicies(Array.isArray(policiesRes) ? policiesRes : (policiesRes as any)?.items || []);
      setGdprRequests(Array.isArray(gdprRes) ? gdprRes : (gdprRes as any)?.items || []);
      setReports(Array.isArray(reportsRes) ? reportsRes : (reportsRes as any)?.items || []);
      setStats(statsRes);
    } catch (error) {
      console.error('Failed to fetch audit compliance data:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleGdprAction = async (id: string, action: 'approve' | 'reject') => {
    try {
      if (action === 'approve') {
        await api.approveGdprRequest(id);
      } else {
        await api.rejectGdprRequest(id, 'Rejected by compliance administrator');
      }
      toast({ title: 'Success', description: `GDPR request ${action}d successfully` });
      fetchData();
    } catch (error: any) {
      toast({ title: 'Error', description: error.message || 'Failed to process request', variant: 'destructive' });
    }
  };

  const handleDownloadReport = async (reportId: string) => {
    try {
      const blob = await api.downloadAuditReport(reportId);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `audit-report-${reportId}.json`;
      a.click();
      window.URL.revokeObjectURL(url);
    } catch (error: any) {
      toast({ title: 'Error', description: error.message || 'Failed to download report', variant: 'destructive' });
    }
  };

  const handleDeleteReport = async (id: string) => {
    if (!confirm('Are you sure you want to delete this report?')) return;
    try {
      await api.deleteAuditReport(id);
      toast({ title: 'Report deleted', description: 'Report has been deleted' });
      fetchData();
    } catch (error: any) {
      toast({ title: 'Error', description: error.message || 'Failed to delete report', variant: 'destructive' });
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
          {[1, 2, 3, 4].map((i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Audit & Compliance</h1>
        <p className="text-muted-foreground">Data retention, GDPR requests, and audit reporting</p>
      </div>

      <Tabs value={activeTab} onValueChange={(val) => setActiveTab(val as any)} className="w-full">
        <TabsList className="grid w-full grid-cols-4">
          <TabsTrigger value="dashboard">Dashboard</TabsTrigger>
          <TabsTrigger value="policies">Retention Policies</TabsTrigger>
          <TabsTrigger value="gdpr">GDPR Requests</TabsTrigger>
          <TabsTrigger value="reports">Audit Reports</TabsTrigger>
        </TabsList>

        <TabsContent value="dashboard" className="space-y-6">
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Audit Events Today</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{stats?.audit_events_today || 0}</div>
                <p className="text-xs text-muted-foreground">Today</p>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Audit Events This Month</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{stats?.audit_events_this_month || 0}</div>
                <p className="text-xs text-muted-foreground">This month</p>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Pending GDPR Requests</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{stats?.pending_gdpr_requests || 0}</div>
                <p className="text-xs text-muted-foreground">Pending review</p>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Completed GDPR This Month</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{stats?.completed_gdpr_requests_this_month || 0}</div>
                <p className="text-xs text-muted-foreground">Completed</p>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="policies" className="space-y-6">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-2xl font-bold">Retention Policies</h2>
              <p className="text-muted-foreground">Configure data retention and archival rules</p>
            </div>
            <Button onClick={() => toast({ title: 'Info', description: 'Create policy dialog can be configured in project settings' })}>
              <Plus className="mr-2 h-4 w-4" />
              Create Policy
            </Button>
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Retention Policies</CardTitle>
            </CardHeader>
            <CardContent>
              {policies.length === 0 ? (
                <div className="text-center py-12">
                  <Shield className="h-12 w-12 mx-auto text-muted-foreground" />
                  <h3 className="mt-4 text-lg font-medium">No retention policies</h3>
                  <p className="text-muted-foreground mt-2">No active policies configured</p>
                </div>
              ) : (
                <div className="space-y-4">
                  {policies.map((policy) => (
                    <div key={policy.id} className="flex items-center justify-between p-4 border rounded-lg bg-white">
                      <div className="flex items-center gap-4">
                        <div className="p-2 bg-primary/10 rounded-lg">
                          <Shield className="h-5 w-5 text-primary" />
                        </div>
                        <div>
                          <h3 className="font-medium">{policy.name}</h3>
                          <p className="text-sm text-muted-foreground">{policy.description || 'No description'}</p>
                          <div className="flex gap-4 text-sm text-muted-foreground mt-1">
                            <span>Retention: {policy.retention_days} days</span>
                            <span>Archive after: {policy.archive_after_days || 'N/A'} days</span>
                            <span>Delete after: {policy.delete_after_days || 'N/A'} days</span>
                          </div>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <Badge variant={policy.is_active ? 'default' : 'secondary'}>
                          {policy.is_active ? 'Active' : 'Inactive'}
                        </Badge>
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button variant="ghost" size="icon"><MoreHorizontal className="h-4 w-4" /></Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuItem onClick={() => api.runRetentionPolicy(policy.id).then(() => toast({ title: 'Policy executed', description: 'Policy has been executed' })).catch(() => toast({ title: 'Error', variant: 'destructive' }))}>
                              <Play className="mr-2 h-4 w-4" /> Run Now
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="gdpr" className="space-y-6">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-2xl font-bold">GDPR Requests</h2>
              <p className="text-muted-foreground">Manage data subject requests</p>
            </div>
          </div>

          <Card>
            <CardHeader>
              <CardTitle>GDPR Requests</CardTitle>
            </CardHeader>
            <CardContent>
              {gdprRequests.length === 0 ? (
                <div className="text-center py-12">
                  <Shield className="h-12 w-12 mx-auto text-muted-foreground" />
                  <h3 className="mt-4 text-lg font-medium">No GDPR requests</h3>
                  <p className="text-muted-foreground mt-2">No data subject requests yet</p>
                </div>
              ) : (
                <div className="space-y-4">
                  {gdprRequests.map((request) => (
                    <div key={request.id} className="flex items-center justify-between p-4 border rounded-lg bg-white">
                      <div className="flex items-center gap-4">
                        <div className="p-2 bg-primary/10 rounded-lg">
                          <Shield className="h-5 w-5 text-primary" />
                        </div>
                        <div>
                          <h3 className="font-medium">{request.request_type}</h3>
                          <p className="text-sm text-muted-foreground">{request.email}</p>
                        </div>
                      </div>
                      <div className="flex items-center gap-4">
                        <Badge variant={request.status === 'COMPLETED' ? 'default' : request.status === 'REJECTED' ? 'destructive' : 'secondary'}>
                          {request.status}
                        </Badge>
                        <span className="text-sm text-muted-foreground">{formatDistanceToNow(new Date(request.created_at), { addSuffix: true })}</span>
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button variant="ghost" size="icon"><MoreHorizontal className="h-4 w-4" /></Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            {request.status === 'PENDING' && (
                              <>
                                <DropdownMenuItem onClick={() => handleGdprAction(request.id, 'approve')}>
                                  <CheckCircle className="mr-2 h-4 w-4" /> Approve
                                </DropdownMenuItem>
                                <DropdownMenuItem onClick={() => handleGdprAction(request.id, 'reject')}>
                                  <X className="mr-2 h-4 w-4" /> Reject
                                </DropdownMenuItem>
                              </>
                            )}
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="reports" className="space-y-6">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-2xl font-bold">Audit Reports</h2>
              <p className="text-muted-foreground">Generate and manage audit reports</p>
            </div>
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Audit Reports</CardTitle>
            </CardHeader>
            <CardContent>
              {reports.length === 0 ? (
                <div className="text-center py-12">
                  <FileText className="h-12 w-12 mx-auto text-muted-foreground" />
                  <h3 className="mt-4 text-lg font-medium">No audit reports</h3>
                  <p className="text-muted-foreground mt-2">Generate your first audit report</p>
                </div>
              ) : (
                <div className="space-y-4">
                  {reports.map((report) => (
                    <div key={report.id} className="flex items-center justify-between p-4 border rounded-lg bg-white">
                      <div className="flex items-center gap-4">
                        <div className="p-2 bg-primary/10 rounded-lg">
                          <FileText className="h-5 w-5 text-primary" />
                        </div>
                        <div>
                          <h3 className="font-medium">{report.report_type}</h3>
                          <p className="text-sm text-muted-foreground">{report.date_from} to {report.date_to}</p>
                        </div>
                      </div>
                      <div className="flex items-center gap-4">
                        <Badge variant={report.status === 'completed' ? 'default' : report.status === 'failed' ? 'destructive' : 'secondary'}>
                          {report.status}
                        </Badge>
                        <span className="text-sm text-muted-foreground">{formatDistanceToNow(new Date(report.created_at), { addSuffix: true })}</span>
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button variant="ghost" size="icon"><MoreHorizontal className="h-4 w-4" /></Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            {report.status === 'completed' && (
                              <DropdownMenuItem onClick={() => handleDownloadReport(report.id)}>
                                <Download className="mr-2 h-4 w-4" /> Download
                              </DropdownMenuItem>
                            )}
                            <DropdownMenuItem onClick={() => handleDeleteReport(report.id)} className="text-red-600">
                              <Trash2 className="mr-2 h-4 w-4" /> Delete
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}