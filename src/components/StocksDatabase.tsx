'use client';

import { Button } from '@/components/ui/button';
import { useAuth } from '@/contexts/AuthContext';
import {
    createStockCategory,
    createStockChart,
    deleteStockCategory,
    deleteStockChart,
    getStockCategories,
    getStockChartsByCategory,
    updateStockCategory,
    updateStockChart
} from '@/lib/api';
import { StockCategory, StockChart } from '@/types/trade';
import React, { useEffect, useState } from 'react';

interface TradingViewEmbedProps {
  url: string;
  title: string;
}

const TradingViewEmbed: React.FC<TradingViewEmbedProps> = ({ url, title }) => {
  // Function to extract chart ID from TradingView URL
  const getChartId = (url: string): string | null => {
    const match = url.match(/tradingview\.com\/x\/([^\/]+)/);
    return match ? match[1] : null;
  };

  const chartId = getChartId(url);
  
  if (!chartId) {
    return (
      <div className="bg-gray-100 dark:bg-gray-700 p-4 rounded-lg text-center border border-gray-200 dark:border-gray-600">
        <p className="text-gray-600 dark:text-gray-400">Invalid TradingView URL</p>
        <p className="text-sm text-gray-500 dark:text-gray-500">Please provide a valid TradingView chart share URL</p>
      </div>
    );
  }

  const embedUrl = `https://www.tradingview.com/x/${chartId}/`;

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md overflow-hidden border border-gray-200 dark:border-gray-600">
      <div className="bg-gray-50 dark:bg-gray-700 px-4 py-2 border-b border-gray-200 dark:border-gray-600">
        <h4 className="font-medium text-gray-900 dark:text-white">{title}</h4>
      </div>
      <div className="relative" style={{ paddingBottom: '56.25%', height: 0 }}>
        <iframe
          src={embedUrl}
          className="absolute top-0 left-0 w-full h-full"
          frameBorder="0"
          allowTransparency={true}
          scrolling="no"
          allowFullScreen={true}
        />
      </div>
    </div>
  );
};

export default function StocksDatabase() {
  const { currentUser } = useAuth();
  const [categories, setCategories] = useState<StockCategory[]>([]);
  const [selectedCategory, setSelectedCategory] = useState<StockCategory | null>(null);
  const [charts, setCharts] = useState<StockChart[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Category form state
  const [showCategoryForm, setShowCategoryForm] = useState(false);
  const [categoryFormData, setCategoryFormData] = useState({ name: '', description: '' });
  const [editingCategory, setEditingCategory] = useState<StockCategory | null>(null);

  // Chart form state
  const [showChartForm, setShowChartForm] = useState(false);
  const [chartFormData, setChartFormData] = useState({
    stock_symbol: '',
    stock_name: '',
    before_tradingview_url: '',
    after_tradingview_url: '',
    notes: ''
  });
  const [editingChart, setEditingChart] = useState<StockChart | null>(null);

  // Fetch categories on component mount
  useEffect(() => {
    if (currentUser?.uid) {
      fetchCategories();
    }
  }, [currentUser]);

  // Fetch charts when category is selected
  useEffect(() => {
    if (selectedCategory?.id) {
      fetchCharts(selectedCategory.id);
    }
  }, [selectedCategory]);

  const fetchCategories = async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await getStockCategories(currentUser!.uid);
      setCategories(response.categories);
      
      // Auto-select first category if available
      if (response.categories.length > 0 && !selectedCategory) {
        setSelectedCategory(response.categories[0]);
      }
    } catch (err) {
      setError('Failed to fetch categories');
      console.error('Error fetching categories:', err);
    } finally {
      setLoading(false);
    }
  };

  const fetchCharts = async (categoryId: string) => {
    try {
      const response = await getStockChartsByCategory(categoryId);
      setCharts(response.charts);
    } catch (err) {
      setError('Failed to fetch charts');
      console.error('Error fetching charts:', err);
    }
  };

  const handleCreateCategory = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await createStockCategory(categoryFormData);
      setCategoryFormData({ name: '', description: '' });
      setShowCategoryForm(false);
      await fetchCategories();
    } catch (err) {
      setError('Failed to create category');
      console.error('Error creating category:', err);
    }
  };

  const handleUpdateCategory = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingCategory?.id) return;
    
    try {
      await updateStockCategory(editingCategory.id, categoryFormData);
      setCategoryFormData({ name: '', description: '' });
      setEditingCategory(null);
      setShowCategoryForm(false);
      await fetchCategories();
    } catch (err) {
      setError('Failed to update category');
      console.error('Error updating category:', err);
    }
  };

  const handleDeleteCategory = async (categoryId: string) => {
    if (!confirm('Are you sure you want to delete this category and all its charts?')) return;
    
    try {
      await deleteStockCategory(categoryId);
      await fetchCategories();
      if (selectedCategory?.id === categoryId) {
        setSelectedCategory(null);
        setCharts([]);
      }
    } catch (err) {
      setError('Failed to delete category');
      console.error('Error deleting category:', err);
    }
  };

  const handleCreateChart = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedCategory?.id) return;
    
    try {
      await createStockChart({
        ...chartFormData,
        category_id: selectedCategory.id
      });
      setChartFormData({
        stock_symbol: '',
        stock_name: '',
        before_tradingview_url: '',
        after_tradingview_url: '',
        notes: ''
      });
      setShowChartForm(false);
      await fetchCharts(selectedCategory.id);
    } catch (err) {
      setError('Failed to create chart');
      console.error('Error creating chart:', err);
    }
  };

  const handleUpdateChart = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingChart?.id || !selectedCategory?.id) return;
    
    try {
      await updateStockChart(editingChart.id, chartFormData);
      setChartFormData({
        stock_symbol: '',
        stock_name: '',
        before_tradingview_url: '',
        after_tradingview_url: '',
        notes: ''
      });
      setEditingChart(null);
      setShowChartForm(false);
      await fetchCharts(selectedCategory.id);
    } catch (err) {
      setError('Failed to update chart');
      console.error('Error updating chart:', err);
    }
  };

  const handleDeleteChart = async (chartId: string) => {
    if (!confirm('Are you sure you want to delete this chart?')) return;
    
    try {
      await deleteStockChart(chartId);
      if (selectedCategory?.id) {
        await fetchCharts(selectedCategory.id);
      }
    } catch (err) {
      setError('Failed to delete chart');
      console.error('Error deleting chart:', err);
    }
  };

  const startEditCategory = (category: StockCategory) => {
    setEditingCategory(category);
    setCategoryFormData({
      name: category.name,
      description: category.description || ''
    });
    setShowCategoryForm(true);
  };

  const startEditChart = (chart: StockChart) => {
    setEditingChart(chart);
    setChartFormData({
      stock_symbol: chart.stock_symbol,
      stock_name: chart.stock_name || '',
      before_tradingview_url: chart.before_tradingview_url || '',
      after_tradingview_url: chart.after_tradingview_url || '',
      notes: chart.notes || ''
    });
    setShowChartForm(true);
  };

  const cancelCategoryForm = () => {
    setShowCategoryForm(false);
    setEditingCategory(null);
    setCategoryFormData({ name: '', description: '' });
  };

  const cancelChartForm = () => {
    setShowChartForm(false);
    setEditingChart(null);
    setChartFormData({
      stock_symbol: '',
      stock_name: '',
      before_tradingview_url: '',
      after_tradingview_url: '',
      notes: ''
    });
  };

  if (loading) {
    return (
      <div className="p-6">
        <div className="flex items-center justify-center min-h-[400px]">
          <div className="text-center">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
            <p className="mt-4 text-gray-600">Loading stocks database...</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6">
      <div className="mb-6">
        <h1 className="text-3xl font-bold text-gray-900 dark:text-white mb-2">Stocks Database</h1>
        <p className="text-gray-600 dark:text-gray-400">Organize your stock analysis with categories and TradingView charts</p>
      </div>

      {error && (
        <div className="mb-6 bg-red-50 dark:bg-red-900/50 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 px-4 py-3 rounded">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Categories Sidebar */}
        <div className="lg:col-span-1">
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md border border-gray-200 dark:border-gray-700 p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-semibold text-gray-900 dark:text-white">Categories</h2>
              <Button
                onClick={() => setShowCategoryForm(true)}
                className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-md text-sm transition-colors"
              >
                Add Category
              </Button>
            </div>

            {/* Category Form */}
            {showCategoryForm && (
              <div className="mb-4 p-4 bg-gray-50 dark:bg-gray-700 rounded-md border border-gray-200 dark:border-gray-600">
                <form onSubmit={editingCategory ? handleUpdateCategory : handleCreateCategory}>
                  <div className="mb-3">
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Name</label>
                    <input
                      type="text"
                      value={categoryFormData.name}
                      onChange={(e) => setCategoryFormData({ ...categoryFormData, name: e.target.value })}
                      className="w-full p-2 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                      required
                      placeholder="Enter category name"
                    />
                  </div>
                  <div className="mb-3">
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Description</label>
                    <textarea
                      value={categoryFormData.description}
                      onChange={(e) => setCategoryFormData({ ...categoryFormData, description: e.target.value })}
                      className="w-full p-2 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                      rows={2}
                      placeholder="Optional description"
                    />
                  </div>
                  <div className="flex gap-2">
                    <Button type="submit" className="bg-green-600 hover:bg-green-700 text-white px-3 py-1 rounded text-sm transition-colors">
                      {editingCategory ? 'Update' : 'Create'}
                    </Button>
                    <Button
                      type="button"
                      onClick={cancelCategoryForm}
                      className="bg-gray-500 hover:bg-gray-600 text-white px-3 py-1 rounded text-sm transition-colors"
                    >
                      Cancel
                    </Button>
                  </div>
                </form>
              </div>
            )}

            {/* Categories List */}
            <div className="space-y-2">
              {categories.length === 0 ? (
                <p className="text-gray-500 dark:text-gray-400 text-sm">No categories yet. Create one to get started!</p>
              ) : (
                categories.map((category) => (
                  <div
                    key={category.id}
                    className={`p-3 rounded-md cursor-pointer transition-colors border ${
                      selectedCategory?.id === category.id
                        ? 'bg-blue-50 dark:bg-blue-900/50 border-blue-300 dark:border-blue-600 text-blue-900 dark:text-blue-100'
                        : 'bg-gray-50 dark:bg-gray-700 hover:bg-gray-100 dark:hover:bg-gray-600 border-gray-200 dark:border-gray-600 text-gray-900 dark:text-white'
                    }`}
                    onClick={() => setSelectedCategory(category)}
                  >
                    <div className="flex items-center justify-between">
                      <div>
                        <h3 className="font-medium">{category.name}</h3>
                        {category.description && (
                          <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">{category.description}</p>
                        )}
                      </div>
                      <div className="flex gap-1">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            startEditCategory(category);
                          }}
                          className="text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300 p-1 transition-colors"
                          title="Edit"
                        >
                          ✏️
                        </button>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDeleteCategory(category.id!);
                          }}
                          className="text-red-600 dark:text-red-400 hover:text-red-800 dark:hover:text-red-300 p-1 transition-colors"
                          title="Delete"
                        >
                          🗑️
                        </button>
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>

        {/* Charts Content */}
        <div className="lg:col-span-2">
          {selectedCategory ? (
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md border border-gray-200 dark:border-gray-700 p-6">
              <div className="flex items-center justify-between mb-6">
                <div>
                  <h2 className="text-xl font-semibold text-gray-900 dark:text-white">{selectedCategory.name} Charts</h2>
                  {selectedCategory.description && (
                    <p className="text-gray-600 dark:text-gray-400 text-sm mt-1">{selectedCategory.description}</p>
                  )}
                </div>
                <Button
                  onClick={() => setShowChartForm(true)}
                  className="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-md transition-colors"
                >
                  Add Chart
                </Button>
              </div>

              {/* Chart Form */}
              {showChartForm && (
                <div className="mb-6 p-4 bg-gray-50 dark:bg-gray-700 rounded-md border border-gray-200 dark:border-gray-600">
                  <form onSubmit={editingChart ? handleUpdateChart : handleCreateChart}>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                      <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Stock Symbol *</label>
                        <input
                          type="text"
                          value={chartFormData.stock_symbol}
                          onChange={(e) => setChartFormData({ ...chartFormData, stock_symbol: e.target.value.toUpperCase() })}
                          className="w-full p-2 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                          placeholder="e.g., AAPL"
                          required
                        />
                      </div>
                      <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Stock Name</label>
                        <input
                          type="text"
                          value={chartFormData.stock_name}
                          onChange={(e) => setChartFormData({ ...chartFormData, stock_name: e.target.value })}
                          className="w-full p-2 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                          placeholder="e.g., Apple Inc."
                        />
                      </div>
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                      <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Before TradingView URL</label>
                        <input
                          type="url"
                          value={chartFormData.before_tradingview_url}
                          onChange={(e) => setChartFormData({ ...chartFormData, before_tradingview_url: e.target.value })}
                          className="w-full p-2 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                          placeholder="https://www.tradingview.com/x/..."
                        />
                      </div>
                      <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">After TradingView URL</label>
                        <input
                          type="url"
                          value={chartFormData.after_tradingview_url}
                          onChange={(e) => setChartFormData({ ...chartFormData, after_tradingview_url: e.target.value })}
                          className="w-full p-2 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                          placeholder="https://www.tradingview.com/x/..."
                        />
                      </div>
                    </div>
                    <div className="mb-4">
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Notes</label>
                      <textarea
                        value={chartFormData.notes}
                        onChange={(e) => setChartFormData({ ...chartFormData, notes: e.target.value })}
                        className="w-full p-2 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                        rows={3}
                        placeholder="Analysis notes, trade reasoning, etc."
                      />
                    </div>
                    <div className="flex gap-2">
                      <Button type="submit" className="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded transition-colors">
                        {editingChart ? 'Update Chart' : 'Add Chart'}
                      </Button>
                      <Button
                        type="button"
                        onClick={cancelChartForm}
                        className="bg-gray-500 hover:bg-gray-600 text-white px-4 py-2 rounded transition-colors"
                      >
                        Cancel
                      </Button>
                    </div>
                  </form>
                </div>
              )}

              {/* Charts List */}
              <div className="space-y-6">
                {charts.length === 0 ? (
                  <p className="text-gray-500 dark:text-gray-400 text-center py-8">No charts in this category yet. Add one to get started!</p>
                ) : (
                  charts.map((chart) => (
                    <div key={chart.id} className="border border-gray-200 dark:border-gray-600 rounded-lg p-4 bg-gray-50 dark:bg-gray-700/50">
                      <div className="flex items-center justify-between mb-4">
                        <div>
                          <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                            {chart.stock_symbol}
                            {chart.stock_name && <span className="text-gray-600 dark:text-gray-400 ml-2">- {chart.stock_name}</span>}
                          </h3>
                          {chart.notes && (
                            <p className="text-gray-600 dark:text-gray-400 text-sm mt-1">{chart.notes}</p>
                          )}
                        </div>
                        <div className="flex gap-2">
                          <button
                            onClick={() => startEditChart(chart)}
                            className="text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300 p-2 transition-colors"
                            title="Edit"
                          >
                            ✏️
                          </button>
                          <button
                            onClick={() => handleDeleteChart(chart.id!)}
                            className="text-red-600 dark:text-red-400 hover:text-red-800 dark:hover:text-red-300 p-2 transition-colors"
                            title="Delete"
                          >
                            🗑️
                          </button>
                        </div>
                      </div>

                      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                        {chart.before_tradingview_url && (
                          <TradingViewEmbed
                            url={chart.before_tradingview_url}
                            title="Before Analysis"
                          />
                        )}
                        {chart.after_tradingview_url && (
                          <TradingViewEmbed
                            url={chart.after_tradingview_url}
                            title="After Analysis"
                          />
                        )}
                      </div>

                      {!chart.before_tradingview_url && !chart.after_tradingview_url && (
                        <div className="text-center py-8 text-gray-500 dark:text-gray-400">
                          No charts available. Edit this entry to add TradingView URLs.
                        </div>
                      )}
                    </div>
                  ))
                )}
              </div>
            </div>
          ) : (
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md border border-gray-200 dark:border-gray-700 p-6">
              <div className="text-center py-12">
                <div className="text-gray-400 dark:text-gray-500 mb-4">
                  <svg className="w-16 h-16 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                  </svg>
                </div>
                <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">Select a Category</h3>
                <p className="text-gray-600 dark:text-gray-400">Choose a category from the sidebar to view and manage your stock charts.</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
