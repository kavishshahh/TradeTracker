import { useCallback } from 'react';

interface ToastOptions {
  className?: string;
  progressClassName?: string;
}

export const useToast = () => {
  const showToast = useCallback((message: string, type: 'success' | 'error', options?: ToastOptions) => {
    // Create a simple toast notification without heavy library
    const toast = document.createElement('div');
    toast.className = `fixed top-4 right-4 z-50 px-4 py-3 rounded-md shadow-lg text-white font-medium transition-all duration-300 transform ${
      type === 'success' 
        ? 'bg-gradient-to-r from-green-400 to-green-600' 
        : 'bg-gradient-to-r from-red-400 to-red-600'
    } ${options?.className || ''}`;
    
    toast.textContent = message;
    document.body.appendChild(toast);
    
    // Auto remove after 3 seconds
    setTimeout(() => {
      toast.style.transform = 'translateX(100%)';
      toast.style.opacity = '0';
      setTimeout(() => {
        if (document.body.contains(toast)) {
          document.body.removeChild(toast);
        }
      }, 300);
    }, 3000);
  }, []);

  return { showToast };
};
