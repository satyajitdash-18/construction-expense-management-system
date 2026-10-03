import { useEffect, useState } from 'react';
import { 
  Building, 
  Receipt, 
  TrendingUp, 
  DollarSign, 
  CheckCircle, 
  FileText, 
  Download 
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import { Skeleton } from '@/components/ui/Skeleton';
import { api } from '@/services/api';
import { DashboardStats, Expense, ExpenseCategory } from '@/types/api';
import { 
  LineChart, 
  Line, 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip, 
  ResponsiveContainer, 
  BarChart, 
  Bar, 
  Cell,
  Legend
} from 'recharts';

const COLORS = ['#3b82f6', '#22c55e', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899'];

const formatTooltipValue = (value: number | string | readonly (string | number)[] | undefined) => {
  const num = Array.isArray(value) ? Number(value[0] || 0) : Number(value || 0);
  return [`₹${num.toLocaleString()}`, 'Amount'] as [string, string];
};

export default function Dashboard() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [recentExpenses, setRecentExpenses] = useState<Expense[]>([]);
  const [categories, setCategories] = useState<ExpenseCategory[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [statsRes, expensesRes, categoriesRes] = await Promise.all([
          api.getDashboardStats().catch(() => null),
          api.getExpenses({ limit: 10 }).catch(() => ({ items: [], total: 0 })),
          api.getCategories().catch(() => []),
        ]);
        setStats(statsRes);
        setRecentExpenses(expensesRes.items || []);
        setCategories(categoriesRes || []);
      } catch (error) {
        console.error('Failed to fetch dashboard data:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, []);

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

  const safeStats: DashboardStats = stats || {
    total_projects: 0,
    active_projects: 0,
    total_expenses: 0,
    pending_expenses: 0,
    reconciled_expenses: 0,
    posted_expenses: 0,
    total_budget: 0,
    spent_budget: 0,
    pending_reconciliation: 0,
  };

  const statsCards = [
    {
      title: 'Total Projects',
      value: safeStats.total_projects,
      icon: Building,
      color: 'blue',
      trend: { value: `${safeStats.active_projects} active`, label: 'current' },
    },
    {
      title: 'Total Expenses',
      value: safeStats.total_expenses,
      icon: Receipt,
      color: 'emerald',
      trend: { value: `${safeStats.pending_expenses} pending`, label: 'status' },
    },
    {
      title: 'Reconciled',
      value: safeStats.reconciled_expenses,
      icon: CheckCircle,
      color: 'green',
      trend: { value: `${safeStats.pending_reconciliation} pending`, label: 'matching' },
    },
    {
      title: 'Posted to Ledger',
      value: safeStats.posted_expenses,
      icon: FileText,
      color: 'purple',
      trend: { value: 'Verified', label: 'ledger state' },
    },
    {
      title: 'Total Budget',
      value: `₹${Number(safeStats.total_budget || 0).toLocaleString()}`,
      icon: DollarSign,
      color: 'indigo',
      trend: { value: 'Allocated', label: 'total' },
    },
    {
      title: 'Spent Budget',
      value: `₹${Number(safeStats.spent_budget || 0).toLocaleString()}`,
      icon: DollarSign,
      color: 'rose',
      trend: { value: 'Tracked', label: 'actuals' },
    },
  ];

  // Dynamic monthly expense trend
  const monthMap: Record<string, { expenses: number; budget: number }> = {};
  const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  recentExpenses.forEach((exp) => {
    if (exp.transaction_date) {
      const d = new Date(exp.transaction_date);
      if (!isNaN(d.getTime())) {
        const m = monthNames[d.getMonth()];
        if (!monthMap[m]) monthMap[m] = { expenses: 0, budget: 0 };
        monthMap[m].expenses += Number(exp.total) || 0;
        monthMap[m].budget += (Number(exp.total) || 0) * 1.1;
      }
    }
  });

  const expenseChartData = Object.keys(monthMap).length > 0
    ? Object.entries(monthMap).map(([name, data]) => ({
        name,
        expenses: Math.round(data.expenses),
        budget: Math.round(data.budget),
      }))
    : [
        { name: 'Current', expenses: safeStats.spent_budget, budget: safeStats.total_budget },
      ];

  // Dynamic category breakdown
  const categoryTotals: Record<string, number> = {};
  recentExpenses.forEach((exp) => {
    const catName = exp.category?.name || 'General';
    categoryTotals[catName] = (categoryTotals[catName] || 0) + (Number(exp.total) || 0);
  });
  if (Object.keys(categoryTotals).length === 0 && categories.length > 0) {
    categories.slice(0, 5).forEach((c) => {
      categoryTotals[c.name] = 0;
    });
  }

  const categoryData = Object.keys(categoryTotals).length > 0
    ? Object.entries(categoryTotals).map(([name, value]) => ({
        name,
        value: Math.round(value),
      }))
    : [{ name: 'Operational', value: safeStats.spent_budget || 0 }];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Dashboard</h1>
          <p className="text-muted-foreground">Overview of your construction expenses</p>
        </div>
        <Button variant="outline" size="sm">
          <Download className="mr-2 h-4 w-4" />
          Export Report
        </Button>
      </div>

      {/* Stats Grid */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
        {statsCards.map((stat, index) => {
          const Icon = stat.icon;
          return (
            <Card key={index} className="relative overflow-hidden">
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">{stat.title}</CardTitle>
                <div className="h-10 w-10 rounded-lg flex items-center justify-center bg-primary/10 text-primary">
                  <Icon className="h-5 w-5" />
                </div>
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{stat.value}</div>
                <div className="flex items-center gap-1 text-xs text-muted-foreground mt-2">
                  <TrendingUp className="h-3 w-3 text-green-500" />
                  <span className="text-green-600 font-medium">{stat.trend.value}</span>
                  <span>{stat.trend.label}</span>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Charts Row */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* Monthly Trend */}
        <Card>
          <CardHeader>
            <CardTitle>Monthly Expenses vs Budget</CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={expenseChartData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" />
                <YAxis />
                <Tooltip formatter={formatTooltipValue} />
                <Legend />
                <Line type="monotone" dataKey="expenses" stroke="#3b82f6" strokeWidth={2} name="Expenses" dot={false} />
                <Line type="monotone" dataKey="budget" stroke="#94a3b8" strokeWidth={2} strokeDasharray="5 5" name="Budget" dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        {/* Category Breakdown */}
        <Card>
          <CardHeader>
            <CardTitle>Expenses by Category</CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={categoryData} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis type="number" />
                <YAxis type="category" dataKey="name" width={100} />
                <Tooltip formatter={formatTooltipValue} />
                <Legend />
                <Bar dataKey="value" fill="#3b82f6" radius={[0, 4, 4, 0]} name="Expense">
                  {categoryData.map((_, idx) => (
                    <Cell key={`cell-${idx}`} fill={COLORS[idx % COLORS.length]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>

      {/* Recent Activity */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>Recent Expenses</CardTitle>
          <Button variant="ghost" size="sm" onClick={() => window.location.href = '/expenses'}>View All</Button>
        </CardHeader>
        <CardContent>
          {recentExpenses.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              No recent expenses recorded yet. Create an expense to get started.
            </div>
          ) : (
            <div className="space-y-4">
              {recentExpenses.slice(0, 5).map((expense) => {
                const title = expense.vendor?.name ? `Expense from ${expense.vendor.name}` : `Expense #${expense.id?.slice(0, 8)}`;
                const desc = `${expense.project?.name || 'Project'} • ₹${Number(expense.total || 0).toLocaleString()} (${expense.payment_method})`;
                const dateStr = expense.transaction_date ? new Date(expense.transaction_date).toLocaleDateString() : 'Recent';
                return (
                  <div key={expense.id} className="flex items-center gap-4 p-4 bg-gray-50 rounded-lg">
                    <div className="shrink-0 w-10 h-10 rounded-full bg-blue-100 flex items-center justify-center">
                      <Receipt className="h-5 w-5 text-blue-600" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-gray-900">{title}</p>
                      <p className="text-sm text-gray-500 truncate">{desc}</p>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-gray-500">{dateStr}</span>
                      <Badge variant={expense.lifecycle_status === 'POSTED' || expense.lifecycle_status === 'RECONCILED' ? 'default' : 'secondary'}>
                        {expense.lifecycle_status}
                      </Badge>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}