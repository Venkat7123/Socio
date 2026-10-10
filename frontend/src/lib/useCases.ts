"use client";
import { useState, useEffect } from 'react';
import { mockCases } from './mockData';

export function useCases() {
  const [cases, setCases] = useState<any[]>([]);
  const [isLoaded, setIsLoaded] = useState(false);

  useEffect(() => {
    const stored = localStorage.getItem('civic_cases');
    if (stored) {
      setCases(JSON.parse(stored));
    } else {
      localStorage.setItem('civic_cases', JSON.stringify(mockCases));
      setCases(mockCases);
    }
    setIsLoaded(true);
  }, []);

  const addCase = (newCase: any) => {
    const updated = [newCase, ...cases];
    setCases(updated);
    localStorage.setItem('civic_cases', JSON.stringify(updated));
  };

  const updateCase = (caseId: string, updates: any) => {
    const updated = cases.map(c => c.case_id === caseId ? { ...c, ...updates } : c);
    setCases(updated);
    localStorage.setItem('civic_cases', JSON.stringify(updated));
  }

  return { cases, addCase, updateCase, isLoaded };
}
