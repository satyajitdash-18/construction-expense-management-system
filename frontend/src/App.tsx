import { Routes, Route, Navigate } from 'react-router-dom';
import Layout from './components/Layout';
import ProtectedRoute from './components/ProtectedRoute';

import LoginPage from './pages/LoginPage';
import Dashboard from './pages/Dashboard';
import ProjectsPage from './pages/ProjectsPage';
import ProjectCreate from './pages/ProjectCreate';
import ProjectDetail from './pages/ProjectDetail';
import ExpensesPage from './pages/ExpensesPage';
import VendorsPage from './pages/VendorsPage';
import CategoriesPage from './pages/CategoriesPage';
import ReconciliationPage from './pages/ReconciliationPage';
import OcrPage from './pages/OcrPage';
import ExtractionPage from './pages/ExtractionPage';
import AuditCompliancePage from './pages/AuditCompliancePage';
import NotificationsPage from './pages/NotificationsPage';
import SettingsPage from './pages/SettingsPage';

function App() {
  return (
    <Routes>
      {/* Public Routes */}
      <Route path="/login" element={<LoginPage />} />

      {/* Protected Routes inside Layout */}
      <Route
        path="/*"
        element={
          <ProtectedRoute>
            <Layout>
              <Routes>
                <Route path="/" element={<Navigate to="/dashboard" replace />} />
                <Route path="/dashboard" element={<Dashboard />} />
                <Route path="/projects" element={<ProjectsPage />} />
                <Route path="/projects/new" element={<ProjectCreate />} />
                <Route path="/projects/:projectId" element={<ProjectDetail />} />
                <Route path="/expenses" element={<ExpensesPage />} />
                <Route path="/vendors" element={<VendorsPage />} />
                <Route path="/categories" element={<CategoriesPage />} />
                <Route path="/reconciliation" element={<ReconciliationPage />} />
                <Route path="/ocr" element={<OcrPage />} />
                <Route path="/extraction" element={<ExtractionPage />} />
                <Route path="/audit-compliance" element={<AuditCompliancePage />} />
                <Route path="/notifications" element={<NotificationsPage />} />
                <Route path="/settings" element={<SettingsPage />} />
                <Route path="*" element={<Navigate to="/dashboard" replace />} />
              </Routes>
            </Layout>
          </ProtectedRoute>
        }
      />
    </Routes>
  );
}

export default App;