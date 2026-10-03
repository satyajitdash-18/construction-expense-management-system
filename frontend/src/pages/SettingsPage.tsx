import { useState, useEffect } from 'react';
import { Loader2, CheckCircle } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription, CardFooter } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Separator } from '@/components/ui/Separator';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/Tabs';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/Form';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/Table';
import { Badge } from '@/components/ui/Badge';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useAuth } from '@/store/authStore';
import { api } from '@/services/api';
import { useToast } from '@/hooks/use-toast';

const profileSchema = z.object({
  full_name: z.string().min(1, 'Full name is required'),
  email: z.string().email('Invalid email address'),
  phone: z.string().optional(),
  avatar_url: z.string().url().optional().or(z.literal('')),
});

type ProfileFormData = z.infer<typeof profileSchema>;

const passwordSchema = z.object({
  current_password: z.string().min(1, 'Current password is required'),
  new_password: z.string().min(8, 'Password must be at least 8 characters'),
  confirm_password: z.string(),
}).refine((data) => data.new_password === data.confirm_password, {
  message: 'Passwords do not match',
  path: ['confirm_password'],
});

type PasswordFormData = z.infer<typeof passwordSchema>;

const notificationSchema = z.object({
  email_notifications: z.boolean(),
  sms_notifications: z.boolean(),
  push_notifications: z.boolean(),
  expense_alerts: z.boolean(),
  payment_alerts: z.boolean(),
  budget_alerts: z.boolean(),
  reconciliation_alerts: z.boolean(),
  weekly_digest: z.boolean(),
});

type NotificationFormData = z.infer<typeof notificationSchema>;

export default function SettingsPage() {
  const { user, updateUser } = useAuth();
  const { toast } = useToast();
  const [theme, setThemeState] = useState(() => localStorage.getItem('theme') || 'system');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState<'profile' | 'password' | 'notifications' | null>(null);

  const form = useForm<ProfileFormData>({
    resolver: zodResolver(profileSchema),
    defaultValues: {
      full_name: user?.full_name || '',
      email: user?.email || '',
      phone: user?.phone || '',
      avatar_url: user?.avatar_url || '',
    },
  });
  const { reset } = form;

  const formPassword = useForm<PasswordFormData>({
    resolver: zodResolver(passwordSchema),
  });
  const { reset: resetPassword } = formPassword;

  const formNotif = useForm<NotificationFormData>({
    resolver: zodResolver(notificationSchema),
    defaultValues: {
      email_notifications: true,
      sms_notifications: false,
      push_notifications: true,
      expense_alerts: true,
      payment_alerts: true,
      budget_alerts: true,
      reconciliation_alerts: true,
      weekly_digest: false,
    },
  });

  useEffect(() => {
    reset({
      full_name: user?.full_name || '',
      email: user?.email || '',
      phone: user?.phone || '',
      avatar_url: user?.avatar_url || '',
    });
  }, [user, reset]);

  const onProfileSubmit = async (data: ProfileFormData) => {
    setSaving('profile');
    try {
      const updated = await api.updateProfile(data);
      updateUser({ ...user, ...updated });
      toast({ title: 'Profile updated', description: 'Your profile has been updated successfully' });
    } catch (error: unknown) {
      toast({ title: 'Error', description: (error as Error).message || 'Failed to update profile', variant: 'destructive' });
    } finally {
      setSaving(null);
    }
  };

  const onPasswordSubmit = async (data: PasswordFormData) => {
    setSaving('password');
    try {
      await api.changePassword(data.current_password, data.new_password);
      toast({ title: 'Password updated', description: 'Your password has been changed successfully' });
      resetPassword();
    } catch (error: unknown) {
      toast({ title: 'Error', description: (error as Error).message || 'Failed to change password', variant: 'destructive' });
    } finally {
      setSaving(null);
    }
  };

  const onNotificationSubmit = async (data: NotificationFormData) => {
    setSaving('notifications');
    try {
      await api.updateNotificationPreferences(data as Record<string, boolean>);
      toast({ title: 'Preferences updated', description: 'Notification preferences have been saved' });
    } catch (error: unknown) {
      toast({ title: 'Error', description: (error as Error).message || 'Failed to update preferences', variant: 'destructive' });
    } finally {
      setSaving(null);
    }
  };

  const handleThemeChange = (newTheme: string) => {
    setThemeState(newTheme);
    localStorage.setItem('theme', newTheme);
    // Apply to document
    const root = document.documentElement;
    if (newTheme === 'dark') {
      root.classList.add('dark');
    } else if (newTheme === 'light') {
      root.classList.remove('dark');
    } else {
      // system
      const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
      root.classList.toggle('dark', prefersDark);
    }
    toast({ title: 'Theme updated', description: `Theme changed to ${newTheme}` });
  };

  const handleDeleteAccount = async () => {
    if (!confirm('Are you sure you want to delete your account? This action cannot be undone.')) return;
    if (!confirm('This will permanently delete all your data. Are you absolutely sure?')) return;

    setLoading(true);
    try {
      await api.deleteAccount();
      window.location.href = '/login';
    } catch (error: unknown) {
      toast({ title: 'Error', description: (error as Error).message || 'Failed to delete account', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Settings</h1>
        <p className="text-muted-foreground">Manage your account settings and preferences</p>
      </div>

      <Tabs defaultValue="profile" className="w-full">
        <TabsList className="grid w-full grid-cols-4">
          <TabsTrigger value="profile">Profile</TabsTrigger>
          <TabsTrigger value="security">Security</TabsTrigger>
          <TabsTrigger value="notifications">Notifications</TabsTrigger>
          <TabsTrigger value="appearance">Appearance</TabsTrigger>
        </TabsList>

        <TabsContent value="profile" className="space-y-6">
          <Card>
            <Form {...form}>
              <form onSubmit={form.handleSubmit(onProfileSubmit)}>
                <CardHeader>
                  <CardTitle>Profile Information</CardTitle>
                  <CardDescription>Update your personal information</CardDescription>
                </CardHeader>
                <CardContent className="space-y-6">
                  <div className="grid gap-4 md:grid-cols-2">
                    <FormField
                      control={form.control}
                      name="full_name"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Full Name</FormLabel>
                          <FormControl>
                            <Input placeholder="John Doe" {...field} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={form.control}
                      name="email"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Email</FormLabel>
                          <FormControl>
                            <Input type="email" placeholder="john@example.com" {...field} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={form.control}
                      name="phone"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Phone</FormLabel>
                          <FormControl>
                            <Input type="tel" placeholder="+1 (555) 000-0000" {...field} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={form.control}
                      name="avatar_url"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Avatar URL</FormLabel>
                          <FormControl>
                            <Input type="url" placeholder="https://example.com/avatar.png" {...field} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  </div>
                </CardContent>
                <CardFooter className="flex justify-end">
                  <Button type="submit" disabled={saving === 'profile'}>
                    {saving === 'profile' && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                    {saving === 'profile' ? 'Saving...' : 'Save Changes'}
                  </Button>
                </CardFooter>
              </form>
            </Form>
          </Card>
        </TabsContent>

        <TabsContent value="security" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Change Password</CardTitle>
              <CardDescription>Update your password to keep your account secure</CardDescription>
            </CardHeader>
            <CardContent>
              <Form {...formPassword}>
                <form id="password-form" onSubmit={formPassword.handleSubmit(onPasswordSubmit)} className="space-y-6">
                  <div className="grid gap-4 md:grid-cols-2">
                    <FormField
                      control={formPassword.control}
                      name="current_password"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Current Password</FormLabel>
                          <FormControl>
                            <Input type="password" placeholder="Enter current password" {...field} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={formPassword.control}
                      name="new_password"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>New Password</FormLabel>
                          <FormControl>
                            <Input type="password" placeholder="Enter new password" {...field} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={formPassword.control}
                      name="confirm_password"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Confirm New Password</FormLabel>
                          <FormControl>
                            <Input type="password" placeholder="Confirm new password" {...field} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  </div>
                </form>
              </Form>
            </CardContent>
            <CardFooter className="flex justify-end">
              <Button type="submit" form="password-form" disabled={saving === 'password'}>
                {saving === 'password' && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                {saving === 'password' ? 'Updating...' : 'Update Password'}
              </Button>
            </CardFooter>
          </Card>

          <Card className="border-red-200">
            <CardHeader>
              <CardTitle className="text-red-600">Danger Zone</CardTitle>
              <CardDescription>Irreversible actions</CardDescription>
            </CardHeader>
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <div>
                  <h4 className="font-medium text-red-600">Delete Account</h4>
                  <p className="text-sm text-muted-foreground">Permanently delete your account and all associated data</p>
                </div>
                <Button variant="destructive" onClick={handleDeleteAccount} disabled={loading}>
                  {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                  {loading ? 'Deleting...' : 'Delete Account'}
                </Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="notifications" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Notification Preferences</CardTitle>
              <CardDescription>Choose which notifications you want to receive and how</CardDescription>
            </CardHeader>
            <CardContent>
              <Form {...formNotif}>
                <form id="notification-form" onSubmit={formNotif.handleSubmit(onNotificationSubmit)} className="space-y-6">
                  <div className="space-y-4">
                    {[
                      { key: 'email_notifications' as const, label: 'Email Notifications', desc: 'Receive notifications via email' },
                      { key: 'sms_notifications' as const, label: 'SMS Notifications', desc: 'Receive notifications via SMS' },
                      { key: 'push_notifications' as const, label: 'Push Notifications', desc: 'Receive push notifications on your device' },
                    ].map((item) => (
                      <div key={item.key} className="flex items-center justify-between py-4 border-b">
                        <div>
                          <h4 className="font-medium">{item.label}</h4>
                          <p className="text-sm text-muted-foreground">{item.desc}</p>
                        </div>
                        <FormField
                          control={formNotif.control}
                          name={item.key}
                          render={({ field }) => (
                            <FormItem>
                              <FormControl>
                                <input
                                  type="checkbox"
                                  checked={field.value}
                                  onChange={(e) => field.onChange(e.target.checked)}
                                  className="h-4 w-4 rounded border-gray-300 text-primary focus:ring-primary"
                                />
                              </FormControl>
                            </FormItem>
                          )}
                        />
                      </div>
                    ))}
                  </div>

                  <Separator className="my-4" />

                  <h4 className="font-medium mb-4">Notification Types</h4>
                  <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                    {[
                      { key: 'expense_alerts' as const, label: 'Expense Alerts', description: 'New expenses and updates' },
                      { key: 'payment_alerts' as const, label: 'Payment Alerts', description: 'Payment received and failed payments' },
                      { key: 'budget_alerts' as const, label: 'Budget Alerts', description: 'Budget thresholds and limits' },
                      { key: 'reconciliation_alerts' as const, label: 'Reconciliation Alerts', description: 'Reconciliation status updates' },
                      { key: 'weekly_digest' as const, label: 'Weekly Digest', description: 'Weekly summary of activity' },
                    ].map((item) => (
                      <div key={item.key} className="flex items-center justify-between p-4 border rounded-lg">
                        <div>
                          <h4 className="font-medium">{item.label}</h4>
                          <p className="text-sm text-muted-foreground">{item.description}</p>
                        </div>
                        <FormField
                          control={formNotif.control}
                          name={item.key}
                          render={({ field }) => (
                            <FormItem>
                              <FormControl>
                                <input
                                  type="checkbox"
                                  checked={field.value}
                                  onChange={(e) => field.onChange(e.target.checked)}
                                  className="h-4 w-4 rounded border-gray-300 text-primary focus:ring-primary"
                                />
                              </FormControl>
                            </FormItem>
                          )}
                        />
                      </div>
                    ))}
                  </div>
                </form>
              </Form>
            </CardContent>
            <CardFooter className="flex justify-end">
              <Button type="submit" form="notification-form" disabled={saving === 'notifications'}>
                {saving === 'notifications' && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                {saving === 'notifications' ? 'Saving...' : 'Save Preferences'}
              </Button>
            </CardFooter>
          </Card>
        </TabsContent>

        <TabsContent value="appearance" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Appearance</CardTitle>
              <CardDescription>Customize how the application looks</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div>
                <h4 className="font-medium mb-4">Theme</h4>
                <div className="flex gap-4">
                  {['light', 'dark', 'system'].map((t) => (
                    <label key={t} className="flex items-center gap-3 p-4 border rounded-lg cursor-pointer hover:bg-gray-50 transition-colors">
                      <input
                        type="radio"
                        name="theme"
                        value={t}
                        checked={theme === t}
                        onChange={() => handleThemeChange(t)}
                        className="h-4 w-4 text-primary border-gray-300 focus:ring-primary"
                      />
                      <div>
                        <span className="font-medium capitalize">{t}</span>
                        <p className="text-sm text-muted-foreground">
                          {t === 'light' ? 'Light mode' : t === 'dark' ? 'Dark mode' : 'Follow system'}
                        </p>
                      </div>
                    </label>
                  ))}
                </div>
              </div>

              <Separator />

              <div>
                <h4 className="font-medium mb-4">Billing History (Demo)</h4>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Date</TableHead>
                      <TableHead className="text-right">Amount</TableHead>
                      <TableHead className="text-right">Status</TableHead>
                      <TableHead className="text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {[
                      { date: 'Jan 15, 2024', amount: '$49.00' },
                      { date: 'Dec 15, 2023', amount: '$49.00' },
                    ].map((row) => (
                      <TableRow key={row.date}>
                        <TableCell>{row.date}</TableCell>
                        <TableCell className="text-right">{row.amount}</TableCell>
                        <TableCell className="text-right"><Badge variant="success">Paid</Badge></TableCell>
                        <TableCell className="text-right"><Button variant="ghost" size="sm">Download</Button></TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>

              <div>
                <h4 className="font-medium mb-2">Current Plan: Professional</h4>
                <ul className="space-y-2 text-sm">
                  {['Unlimited Projects', 'Unlimited Expenses', 'Advanced Analytics', 'Priority Support'].map((feature) => (
                    <li key={feature} className="flex items-center gap-2">
                      <CheckCircle className="h-4 w-4 text-green-500" /> {feature}
                    </li>
                  ))}
                </ul>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}