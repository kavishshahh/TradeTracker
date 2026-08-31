'use client';

import { useAuth } from '@/contexts/AuthContext';
import { trackNavigation, trackUserEngagement } from '@/lib/analytics';
import { Activity, BarChart3, BookOpen, Calculator, Calendar, ChevronLeft, List, LogOut, Menu, Plus, TrendingUp, User, X } from 'lucide-react';
import { usePathname } from 'next/navigation';
import { useEffect, useRef, useState } from 'react';
import { ToastContainer } from 'react-toastify';
import 'react-toastify/dist/ReactToastify.css';

interface LayoutProps {
  children: React.ReactNode;
}

const navigation = [
  { name: 'Dashboard', href: '/', icon: BarChart3 },
  { name: 'Add Trade', href: '/add-trade', icon: Plus },
  { name: 'Active Trades', href: '/active-trades', icon: Activity },
  { name: 'Trades', href: '/trades', icon: List },
  { name: 'Calendar', href: '/calendar', icon: Calendar },
  { name: 'Journal', href: '/journal', icon: BookOpen },
  { name: 'Monthly Returns', href: '/monthly-returns', icon: TrendingUp },
  { name: 'Qty Calculator', href: '/qty-calculator', icon: Calculator },
];

function BrandMark() {
  return (
    <span className="app-brand-mark" aria-hidden="true">
      <i /><i /><i />
    </span>
  );
}

export default function Layout({ children }: LayoutProps) {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const pathname = usePathname();
  const { currentUser, logout } = useAuth();
  const previousPathnameRef = useRef(pathname);
  const activePage = navigation.find((item) => item.href === pathname)?.name || 'TradeBud';

  useEffect(() => {
    setSidebarOpen(window.innerWidth >= 900);
  }, []);

  useEffect(() => {
    const previousPathname = previousPathnameRef.current;
    if (previousPathname !== pathname) {
      trackNavigation(previousPathname, pathname);
      trackUserEngagement('page_navigation');
      previousPathnameRef.current = pathname;
      if (window.innerWidth < 900) setSidebarOpen(false);
    }
  }, [pathname, activePage]);

  const toggleSidebar = () => {
    setSidebarOpen((open) => !open);
    trackUserEngagement('sidebar_toggle');
  };

  return (
    <div className="app-shell">
      {sidebarOpen && <button className="sidebar-scrim" onClick={() => setSidebarOpen(false)} aria-label="Close navigation" />}

      <aside className={sidebarOpen ? 'app-sidebar is-open' : 'app-sidebar is-collapsed'}>
        <div className="sidebar-header">
          <a className="app-brand" href="/" aria-label="TradeBud dashboard">
            <BrandMark />
            {sidebarOpen && <span>TradeBud</span>}
          </a>
          <button onClick={toggleSidebar} className="sidebar-toggle" aria-label={sidebarOpen ? 'Collapse navigation' : 'Expand navigation'}>
            {sidebarOpen ? <ChevronLeft size={18} /> : <Menu size={18} />}
          </button>
        </div>

        {sidebarOpen && <p className="nav-label">WORKSPACE</p>}
        <nav className="app-nav" aria-label="Workspace navigation">
          {navigation.map((item) => {
            const Icon = item.icon;
            const isActive = pathname === item.href;
            return (
              <a
                key={item.name}
                href={item.href}
                title={!sidebarOpen ? item.name : undefined}
                className={isActive ? 'nav-item active' : 'nav-item'}
                aria-current={isActive ? 'page' : undefined}
              >
                <Icon size={17} strokeWidth={1.8} />
                {sidebarOpen && <span>{item.name}</span>}
              </a>
            );
          })}
        </nav>

        <div className="sidebar-footer">
          <a href="/profile" className={pathname === '/profile' ? 'account-link active' : 'account-link'} title={!sidebarOpen ? 'Profile settings' : undefined}>
            <span className="avatar"><User size={16} /></span>
            {sidebarOpen && (
              <span className="account-copy">
                <strong>{currentUser?.email?.split('@')[0] || 'Trader'}</strong>
                <small>Account settings</small>
              </span>
            )}
          </a>
          {sidebarOpen && (
            <div className="sidebar-legal">
              <a href="https://tradebud.xyz/privacy">Privacy</a>
              <a href="https://tradebud.xyz/terms">Terms</a>
            </div>
          )}
          <button
            onClick={() => {
              trackUserEngagement('logout');
              logout();
            }}
            className="logout-button"
            title={!sidebarOpen ? 'Sign out' : undefined}
          >
            <LogOut size={17} />
            {sidebarOpen && <span>Sign out</span>}
          </button>
        </div>
      </aside>

      <div className="app-workspace">
        <header className="mobile-app-header">
          <button onClick={toggleSidebar} aria-label="Open navigation"><Menu size={20} /></button>
          <span>{activePage}</span>
          <a href="/profile" aria-label="Profile"><User size={18} /></a>
        </header>
        <main className="app-content">{children}</main>
      </div>

      <ToastContainer
        position="top-right"
        autoClose={3000}
        hideProgressBar={false}
        newestOnTop={false}
        closeOnClick
        rtl={false}
        pauseOnFocusLoss
        draggable
        pauseOnHover
        theme="light"
        toastClassName="tradebud-toast"
        progressClassName="tradebud-toast-progress"
      />
    </div>
  );
}
