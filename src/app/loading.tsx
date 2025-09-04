export default function Loading() {
  return (
    <div className="min-h-screen bg-white dark:bg-gray-900 flex items-center justify-center">
      <div className="text-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
        <h1 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">Loading TradeBud</h1>
        <p className="text-gray-600 dark:text-gray-400">Preparing your trading dashboard...</p>
      </div>
    </div>
  )
}
