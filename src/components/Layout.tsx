'use client';

import { useAuth } from '@/contexts/AuthContext';
import { trackNavigation, trackUserEngagement } from '@/lib/analytics';
import { Activity, BarChart3, BookOpen, Calendar, List, LogOut, Menu, Plus, TrendingUp, User, X } from 'lucide-react';
import { usePathname } from 'next/navigation';
import { useEffect, useRef, useState } from 'react';
import { ToastContainer } from 'react-toastify';
import 'react-toastify/dist/ReactToastify.css';

interface LayoutProps {
  children: React.ReactNode;
}

export default function Layout({ children }: LayoutProps) {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const pathname = usePathname();
  const { currentUser, logout } = useAuth();
  const previousPathnameRef = useRef(pathname);

  const navigation = [
    { name: 'Dashboard', href: '/', icon: BarChart3 },
    { name: 'Add Trade', href: '/add-trade', icon: Plus },
    { name: 'Active Trades', href: '/active-trades', icon: Activity },
    { name: 'Trades', href: '/trades', icon: List },
    { name: 'Calendar', href: '/calendar', icon: Calendar },
    { name: 'Journal', href: '/journal', icon: BookOpen },
    { name: 'Monthly Returns', href: '/monthly-returns', icon: TrendingUp },
  ];

  // Track navigation changes
  useEffect(() => {
    const previousPathname = previousPathnameRef.current;
    
    if (previousPathname !== pathname) {
      // Track navigation from previous to current page
      trackNavigation(previousPathname, pathname);
      
      // Track page engagement
      const pageName = navigation.find(nav => nav.href === pathname)?.name || pathname;
      trackUserEngagement('page_navigation', pageName);
      
      // Update the ref for next navigation
      previousPathnameRef.current = pathname;
    }
  }, [pathname, navigation]);

  return (
    <div className="flex h-screen bg-gray-50">
      {/* Sidebar */}
      <div className={`${sidebarOpen ? 'w-64' : 'w-16'} transition-all duration-300 bg-white shadow-lg`}>
        <div className="flex h-full flex-col">
          {/* Logo */}
          <div className="flex h-16 items-center justify-between px-4 border-b">
            {sidebarOpen && (
              <h1 className="text-xl font-bold text-gray-900">TradeBud</h1>
            )}
            <button
              onClick={() => {
                setSidebarOpen(!sidebarOpen);
                trackUserEngagement('sidebar_toggle', sidebarOpen ? 'collapse' : 'expand');
              }}
              className="rounded-md p-2 text-gray-400 hover:bg-gray-100 hover:text-gray-500"
            >
              {sidebarOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
            </button>
          </div>

          {/* Navigation */}
          <nav className="flex-1 space-y-1 px-2 py-4">
            {navigation.map((item) => {
              const Icon = item.icon;
              const isActive = pathname === item.href;
              return (
                <a
                  key={item.name}
                  href={item.href}
                  className={`
                    ${isActive
                      ? 'bg-blue-50 border-r-2 border-blue-500 text-blue-700'
                      : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
                    }
                    group flex items-center px-2 py-2 text-sm font-medium rounded-md transition-colors
                  `}
                >
                  <Icon
                    className={`
                      ${isActive ? 'text-blue-500' : 'text-gray-400 group-hover:text-gray-500'}
                      ${sidebarOpen ? 'mr-3' : 'mx-auto'}
                      h-5 w-5 flex-shrink-0
                    `}
                  />
                  {sidebarOpen && item.name}
                </a>
              );
            })}
          </nav>

          {/* Footer */}
          {sidebarOpen && (
            <div className="border-t p-4 space-y-2">
              {/* User Profile */}
              <a href="/profile" className="flex items-center hover:bg-gray-50 rounded-md p-2 transition-colors">
                <div className="flex-shrink-0">
                  <div className="h-8 w-8 rounded-full bg-blue-500 flex items-center justify-center">
                    <User className="h-5 w-5 text-white" />
                  </div>
                </div>
                <div className="ml-3">
                  <p className="text-sm font-medium text-gray-700">
                    {currentUser?.email?.split('@')[0] || 'User'}
                  </p>
                  <p className="text-xs text-gray-500">Manage account settings</p>
                </div>
              </a>
              
              {/* Logout */}
              <button
                onClick={() => {
                  trackUserEngagement('logout', 'sidebar');
                  logout();
                }}
                className="w-full flex items-center px-2 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50 hover:text-gray-900 rounded-md transition-colors"
              >
                <LogOut className="h-5 w-5 text-gray-400 mr-3" />
                Logout
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Main content */}
      <div className="flex-1 overflow-auto">
        <main className="flex-1 p-6">
          {children}
        </main>
      </div>

      {/* Toast Container */}
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
        toastClassName="relative flex p-1 min-h-10 rounded-md justify-between overflow-hidden cursor-pointer bg-white shadow-lg border border-gray-200"
        progressClassName="!bg-gradient-to-r !from-blue-500 !to-purple-500"
      />
    </div>
  );
}
