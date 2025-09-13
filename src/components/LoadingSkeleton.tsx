export default function LoadingSkeleton() {
  return (
    <div className="max-w-2xl mx-auto">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg p-6">
        <div className="animate-pulse">
          {/* Header */}
          <div className="mb-6">
            <div className="h-8 bg-gray-200 dark:bg-gray-700 rounded mb-2"></div>
            <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-3/4"></div>
          </div>
          
          {/* Trade Type Toggle */}
          <div className="mb-6">
            <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-20 mb-2"></div>
            <div className="flex rounded-md shadow-sm">
              <div className="flex-1 h-10 bg-gray-200 dark:bg-gray-700 rounded-l-md"></div>
              <div className="flex-1 h-10 bg-gray-200 dark:bg-gray-700 rounded-r-md"></div>
            </div>
          </div>
          
          {/* Form Fields */}
          <div className="space-y-6">
            {/* Date and Ticker */}
            <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
              <div className="h-10 bg-gray-200 dark:bg-gray-700 rounded"></div>
              <div className="h-10 bg-gray-200 dark:bg-gray-700 rounded"></div>
            </div>
            
            {/* Status Toggle */}
            <div className="flex rounded-md shadow-sm">
              <div className="flex-1 h-10 bg-gray-200 dark:bg-gray-700 rounded-l-md"></div>
              <div className="flex-1 h-10 bg-gray-200 dark:bg-gray-700 rounded-r-md"></div>
            </div>
            
            {/* Price Fields */}
            <div className="grid grid-cols-1 gap-6 sm:grid-cols-3">
              <div className="h-10 bg-gray-200 dark:bg-gray-700 rounded"></div>
              <div className="h-10 bg-gray-200 dark:bg-gray-700 rounded"></div>
              <div className="h-10 bg-gray-200 dark:bg-gray-700 rounded"></div>
            </div>
            
            {/* Risk Fields */}
            <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
              <div className="h-10 bg-gray-200 dark:bg-gray-700 rounded"></div>
              <div className="h-10 bg-gray-200 dark:bg-gray-700 rounded"></div>
            </div>
            
            {/* Notes */}
            <div className="h-20 bg-gray-200 dark:bg-gray-700 rounded"></div>
            
            {/* Submit Button */}
            <div className="flex justify-end">
              <div className="h-10 w-24 bg-gray-200 dark:bg-gray-700 rounded"></div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
