import { useEffect, useState, useCallback } from 'react';
import { Plus, Bell, Eye, Trash2, MoreHorizontal, ArrowUpDown, Globe, Edit, ChevronLeft, ChevronRight } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/Select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/Table';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/DropdownMenu';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogDescription, DialogFooter } from '@/components/ui/Dialog';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/Form';
import { Badge } from '@/components/ui/Badge';
import { Skeleton } from '@/components/ui/Skeleton';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { api } from '@/services/api';
import type { WebhookConfig, NotificationItem, NotificationStats } from '@/types/api';
import { useToast } from '@/hooks/use-toast';
import { formatDistanceToNow } from 'date-fns';

const webhookSchema = z.object({
  url: z.string().url('Invalid URL'),
  events: z.array(z.string()).min(1, 'At least one event is required'),
  secret: z.string().optional(),
  is_active: z.boolean(),
});

type WebhookFormData = z.infer<typeof webhookSchema>;

export default function NotificationsPage() {
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [webhooks, setWebhooks] = useState<WebhookConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const pageSize = 20;
  const [statusFilter, setStatusFilter] = useState('');
  const [webhookDialogOpen, setWebhookDialogOpen] = useState(false);
  const [editingWebhook, setEditingWebhook] = useState<WebhookConfig | null>(null);
  const [stats, setStats] = useState<NotificationStats | null>(null);
  const { toast } = useToast();

  const webhookForm = useForm<WebhookFormData>({
    resolver: zodResolver(webhookSchema),
    defaultValues: { url: '', is_active: true, events: [], secret: '' },
  });

  const fetchNotifications = useCallback(async () => {
    setLoading(true);
    try {
      const result = await api.getNotifications({ page, page_size: pageSize, status: statusFilter || undefined });
      setNotifications(result.items || []);
      setTotal(result.total || 0);
    } catch (error) {
      console.error('Failed to fetch notifications:', error);
    } finally {
      setLoading(false);
    }
  }, [page, statusFilter]);

  const fetchWebhooks = useCallback(async () => {
    try {
      const result = await api.getWebhooks();
      setWebhooks(result.items || []);
    } catch (error) {
      console.error('Failed to fetch webhooks:', error);
    }
  }, []);

  const fetchStats = useCallback(async () => {
    try {
      const statsRes = await api.getNotificationStats();
      setStats(statsRes);
    } catch (error) {
      console.error('Failed to fetch stats:', error);
    }
  }, []);

  useEffect(() => {
    fetchNotifications();
    fetchWebhooks();
    fetchStats();
  }, [fetchNotifications, fetchWebhooks, fetchStats]);

  const handleSort = (_field: string) => {
    // sort handled client-side in future
  };

  const handleSubmitWebhook = async (data: WebhookFormData) => {
    try {
      if (editingWebhook) {
        // No updateWebhook endpoint, delete and recreate
        await api.deleteWebhook(editingWebhook.id);
        await api.createWebhook(data);
        toast({ title: 'Webhook updated', description: 'Webhook has been updated successfully' });
      } else {
        await api.createWebhook(data);
        toast({ title: 'Webhook created', description: 'Webhook has been created successfully' });
      }
      setWebhookDialogOpen(false);
      setEditingWebhook(null);
      webhookForm.reset();
      fetchWebhooks();
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to save webhook';
      toast({ title: 'Error', description: message, variant: 'destructive' });
    }
  };

  const handleDeleteWebhook = async (id: string) => {
    if (!confirm('Are you sure you want to delete this webhook?')) return;
    try {
      await api.deleteWebhook(id);
      toast({ title: 'Webhook deleted' });
      fetchWebhooks();
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to delete webhook';
      toast({ title: 'Error', description: message, variant: 'destructive' });
    }
  };

  const handleEditWebhook = (webhook: WebhookConfig) => {
    setEditingWebhook(webhook);
    webhookForm.reset({
      url: webhook.url,
      events: webhook.events,
      secret: webhook.secret || '',
      is_active: webhook.is_active,
    });
    setWebhookDialogOpen(true);
  };

  if (loading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-48" />
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
          <h1 className="text-3xl font-bold tracking-tight">Notifications</h1>
          <p className="text-muted-foreground">Manage notifications and webhooks</p>
        </div>
        <div className="flex gap-2">
          <Dialog open={webhookDialogOpen} onOpenChange={setWebhookDialogOpen}>
            <DialogTrigger asChild>
              <Button onClick={() => { setEditingWebhook(null); webhookForm.reset({ is_active: true, events: [] }); }}>
                <Plus className="mr-2 h-4 w-4" />
                Add Webhook
              </Button>
            </DialogTrigger>
            <DialogContent className="sm:max-w-[500px]">
              <DialogHeader>
                <DialogTitle>{editingWebhook ? 'Edit Webhook' : 'Add Webhook'}</DialogTitle>
                <DialogDescription>Configure a webhook endpoint for event notifications</DialogDescription>
              </DialogHeader>
              <Form {...webhookForm}>
                <form onSubmit={webhookForm.handleSubmit(handleSubmitWebhook)}>
                  <div className="space-y-4 py-4">
                    <FormField
                      control={webhookForm.control}
                      name="url"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Webhook URL</FormLabel>
                          <FormControl>
                            <Input placeholder="https://your-domain.com/webhook" {...field} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={webhookForm.control}
                      name="secret"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Secret (optional)</FormLabel>
                          <FormControl>
                            <Input placeholder="Signing secret" {...field} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  </div>
                  <DialogFooter>
                    <Button type="button" variant="outline" onClick={() => setWebhookDialogOpen(false)}>Cancel</Button>
                    <Button type="submit">Save Webhook</Button>
                  </DialogFooter>
                </form>
              </Form>
            </DialogContent>
          </Dialog>
        </div>
      </div>

      {/* Stats */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Sent</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats?.total_sent || 0}</div>
            <p className="text-xs text-muted-foreground">All time</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Failed</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-red-600">{stats?.total_failed || 0}</div>
            <p className="text-xs text-muted-foreground">All time</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">By Channel</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {Object.entries(stats?.by_channel || {}).map(([channel, count]) => (
                <div key={channel} className="flex justify-between text-sm">
                  <span className="capitalize">{channel}</span>
                  <span className="font-medium">{String(count)}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">By Status</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {Object.entries(stats?.by_status || {}).map(([status, count]) => (
                <div key={status} className="flex justify-between text-sm">
                  <span className="capitalize">{status}</span>
                  <span className="font-medium">{String(count)}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Notifications Table */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>Notifications ({total})</CardTitle>
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger className="w-[180px]">
              <SelectValue placeholder="All Status" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="">All Status</SelectItem>
              <SelectItem value="sent">Sent</SelectItem>
              <SelectItem value="pending">Pending</SelectItem>
              <SelectItem value="failed">Failed</SelectItem>
            </SelectContent>
          </Select>
        </CardHeader>
        <CardContent>
          {notifications.length === 0 ? (
            <div className="text-center py-12">
              <Bell className="h-12 w-12 mx-auto text-muted-foreground" />
              <h3 className="mt-4 text-lg font-medium">No notifications</h3>
              <p className="text-muted-foreground mt-2">No notifications found</p>
            </div>
          ) : (
            <>
              <div className="rounded-md border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="cursor-pointer" onClick={() => handleSort('channel')}>
                        <span className="flex items-center">Channel <ArrowUpDown className="ml-1 h-4 w-4" /></span>
                      </TableHead>
                      <TableHead className="cursor-pointer" onClick={() => handleSort('status')}>
                        <span className="flex items-center">Status <ArrowUpDown className="ml-1 h-4 w-4" /></span>
                      </TableHead>
                      <TableHead className="cursor-pointer" onClick={() => handleSort('created_at')}>
                        <span className="flex items-center">Created <ArrowUpDown className="ml-1 h-4 w-4" /></span>
                      </TableHead>
                      <TableHead className="cursor-pointer" onClick={() => handleSort('subject')}>
                        <span className="flex items-center">Subject <ArrowUpDown className="ml-1 h-4 w-4" /></span>
                      </TableHead>
                      <TableHead className="text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {notifications.map((notification) => (
                      <TableRow key={notification.id}>
                        <TableCell>
                          <Badge variant={notification.channel === 'whatsapp' ? 'success' : 'default'}>
                            {notification.channel}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          <Badge variant={
                            notification.status === 'sent' ? 'success' :
                            notification.status === 'failed' ? 'destructive' : 'secondary'
                          }>
                            {notification.status}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          {notification.created_at ? formatDistanceToNow(new Date(notification.created_at), { addSuffix: true }) : 'N/A'}
                        </TableCell>
                        <TableCell className="max-w-xs truncate">
                          {notification.subject || notification.body?.substring(0, 50) || 'No subject'}
                        </TableCell>
                        <TableCell className="text-right">
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <Button variant="ghost" size="icon"><MoreHorizontal className="h-4 w-4" /></Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end">
                              <DropdownMenuItem onClick={() => { /* view */ }}>
                                <Eye className="mr-2 h-4 w-4" /> View
                              </DropdownMenuItem>
                              <DropdownMenuSeparator />
                              <DropdownMenuItem className="text-red-600" onClick={() => { /* delete */ }}>
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
                  Showing {((page - 1) * pageSize) + 1} to {Math.min(page * pageSize, total)} of {total} notifications
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

      {/* Webhooks Section */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-2xl font-bold">Webhooks</h2>
            <p className="text-muted-foreground">Configure webhook endpoints for event notifications</p>
          </div>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Webhook Configurations</CardTitle>
          </CardHeader>
          <CardContent>
            {webhooks.length === 0 ? (
              <div className="text-center py-12">
                <Globe className="h-12 w-12 mx-auto text-muted-foreground" />
                <h3 className="mt-4 text-lg font-medium">No webhooks configured</h3>
                <p className="text-muted-foreground mt-2">Add a webhook to receive event notifications</p>
              </div>
            ) : (
              <div className="space-y-4">
                {webhooks.map((webhook) => (
                  <div key={webhook.id} className="flex items-center justify-between p-4 border rounded-lg bg-white">
                    <div className="flex items-center gap-4">
                      <div className="p-2 bg-primary/10 rounded-lg">
                        <Globe className="h-5 w-5 text-primary" />
                      </div>
                      <div>
                        <h3 className="font-medium">{webhook.url}</h3>
                        <p className="text-sm text-gray-500">{Array.isArray(webhook.events) ? webhook.events.join(', ') : webhook.events}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-4">
                      <Badge variant={webhook.is_active ? 'success' : 'secondary'}>
                        {webhook.is_active ? 'Active' : 'Inactive'}
                      </Badge>
                      <span className="text-sm text-gray-500">
                        Success: {webhook.success_count || 0} | Failed: {webhook.failure_count || 0}
                      </span>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon"><MoreHorizontal className="h-4 w-4" /></Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem onClick={() => handleEditWebhook(webhook)}>
                            <Edit className="mr-2 h-4 w-4" /> Edit
                          </DropdownMenuItem>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem onClick={() => handleDeleteWebhook(webhook.id)} className="text-red-600">
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
      </div>

      {/* Preferences Section */}
      <div>
        <h2 className="text-2xl font-bold mb-4">Notification Preferences</h2>
        <Card>
          <CardHeader>
            <CardTitle>Notification Preferences</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-muted-foreground mb-4">
              Configure your notification preferences for different event types and channels.
            </p>
            <div className="space-y-4">
              {[
                { event: 'expense.created', label: 'Expense Created' },
                { event: 'expense.approved', label: 'Expense Approved' },
                { event: 'expense.rejected', label: 'Expense Rejected' },
                { event: 'payment.received', label: 'Payment Received' },
                { event: 'reconciliation.matched', label: 'Reconciliation Matched' },
                { event: 'budget.exceeded', label: 'Budget Exceeded' },
              ].map((pref) => (
                <div key={pref.event} className="flex items-center justify-between p-4 border rounded-lg">
                  <div>
                    <p className="font-medium">{pref.label}</p>
                    <p className="text-sm text-muted-foreground">{pref.event}</p>
                  </div>
                  <div className="flex items-center gap-4">
                    {['email', 'sms', 'push', 'webhook'].map((channel) => (
                      <label key={channel} className="flex items-center gap-2">
                        <input type="checkbox" defaultChecked className="rounded border-gray-300" />
                        <span className="text-sm capitalize">{channel}</span>
                      </label>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}