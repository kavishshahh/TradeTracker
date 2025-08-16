'use client';

import { Calendar, ChevronLeft, ChevronRight } from 'lucide-react';

interface MonthSelectorProps {
  currentDate: Date;
  onPreviousMonth: () => void;
  onNextMonth: () => void;
  onDateChange?: (date: Date) => void;
}

export default function MonthSelector({ 
  currentDate, 
  onPreviousMonth, 
  onNextMonth, 
  onDateChange 
}: MonthSelectorProps) {
  const formatMonthYear = (date: Date) => {
    return date.toLocaleDateString('en-US', { 
      month: 'long', 
      year: 'numeric' 
    });
  };

  const handleDateChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const newDate = new Date(event.target.value);
    onDateChange?.(newDate);
  };

  return (
    <div className="flex items-center space-x-4 bg-white rounded-lg shadow p-4">
      <div className="flex items-center space-x-2">
        <Calendar className="h-5 w-5 text-gray-500" />
        <span className="text-sm font-medium text-gray-700">Period:</span>
      </div>
      
      <button
        onClick={onPreviousMonth}
        className="p-2 rounded-md hover:bg-gray-100 transition-colors"
        title="Previous Month"
      >
        <ChevronLeft className="h-5 w-5 text-gray-600" />
      </button>
      
      <div className="flex items-center space-x-2">
        <h2 className="text-lg font-semibold text-gray-900 min-w-[120px] text-center">
          {formatMonthYear(currentDate)}
        </h2>
        <input
          type="month"
          value={`${currentDate.getFullYear()}-${String(currentDate.getMonth() + 1).padStart(2, '0')}`}
          onChange={handleDateChange}
          className="text-sm border border-gray-300 rounded px-2 py-1 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
        />
      </div>
      
      <button
        onClick={onNextMonth}
        className="p-2 rounded-md hover:bg-gray-100 transition-colors"
        title="Next Month"
      >
        <ChevronRight className="h-5 w-5 text-gray-600" />
      </button>
    </div>
  );
}
