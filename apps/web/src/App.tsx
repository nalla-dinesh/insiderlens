/** App shell — navy sidebar + topbar + routed body (Dashboard / Alert Detail /
 * Explorer). Phase-06 pages are visible-but-disabled nav entries (spec §7.4). */
import { useState } from 'react';
import { Toaster } from 'react-hot-toast';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';

import Sidebar from './components/layout/Sidebar';
import TopBar from './components/layout/TopBar';
import AlertDetailPage from './pages/AlertDetailPage';
import CasesPage from './pages/CasesPage';
import EvaluationPage from './pages/EvaluationPage';
import DashboardPage from './pages/DashboardPage';
import ExplorerPage from './pages/ExplorerPage';

export default function App() {
  // bumped whenever Run Analysis finishes → pages re-fetch
  const [reloadSignal, setReloadSignal] = useState(0);
  return (
    <BrowserRouter>
      <div className="flex min-h-screen bg-slate-50">
        <Sidebar />
        <div className="flex min-w-0 flex-1 flex-col">
          <TopBar onRunFinished={() => setReloadSignal((n) => n + 1)} />
          <main className="flex-1 p-6">
            <Routes>
              <Route path="/" element={<DashboardPage reloadSignal={reloadSignal} />} />
              <Route path="/alerts/:id" element={<AlertDetailPage reloadSignal={reloadSignal} />} />
              <Route path="/explorer" element={<ExplorerPage reloadSignal={reloadSignal} />} />
              <Route path="/cases" element={<CasesPage reloadSignal={reloadSignal} />} />
              <Route path="/evaluation" element={<EvaluationPage reloadSignal={reloadSignal} />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </main>
          <footer className="border-t border-slate-200 px-6 py-3 text-[10px] text-slate-400">
            InsiderLens — explainable insider-threat detection for regional banks · 'a fraud analyst
            should read the score like a ledger' · Phase 05 analyst console.
          </footer>
        </div>
      </div>
      <Toaster
        position="top-right"
        toastOptions={{
          style: { fontSize: '13px', borderRadius: '10px' },
          success: { iconTheme: { primary: '#0284c7', secondary: '#fff' } },
        }}
      />
    </BrowserRouter>
  );
}
