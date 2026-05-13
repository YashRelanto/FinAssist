import React, { useRef } from 'react';
import { FileText, Download, Filter, Calendar, Upload, FileCheck } from 'lucide-react';
import { useAppContext } from '../context/AppContext';
import { Report } from '../types';

export const Reports: React.FC = () => {
  const { reports, uploadReport } = useAppContext();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      uploadReport(file);
    }
  };

  const downloadFile = (report: Report) => {
    // Basic download simulation for browser experience
    const content = `Report Title: ${report.title}\nDate: ${report.date}\nType: ${report.type}`;
    const blob = new Blob([content], { type: 'text/plain' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${report.title.replace(/\s+/g, '_')}_${report.date.replace(/\s+/g, '_')}.${report.type.toLowerCase()}`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-8">
      <header className="flex justify-between items-end">
        <div>
          <h2 className="text-3xl font-bold text-on-surface">Financial Reports</h2>
          <p className="text-on-surface-variant font-medium text-sm mt-1">Generated statements and analytics exports.</p>
        </div>
        <button 
          onClick={() => fileInputRef.current?.click()}
          className="flex items-center gap-2 px-6 py-2.5 bg-secondary text-white font-bold rounded-lg shadow-md hover:brightness-110 transition-all"
        >
          <Upload className="w-4 h-4" /> Upload Report
        </button>
        <input 
          type="file" 
          ref={fileInputRef} 
          onChange={handleFileChange} 
          className="hidden" 
          accept=".pdf,.csv"
        />
      </header>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {reports.map((report) => (
          <div key={report.id} className="bg-surface-container-lowest p-6 rounded-2xl border border-outline-variant/30 soft-shadow flex items-center justify-between group hover:bg-primary-container/10 transition-colors">
            <div className="flex items-center gap-4">
              <div className="w-12 h-12 rounded-xl bg-surface-container-high flex items-center justify-center text-primary group-hover:bg-white transition-colors">
                {report.type === 'PDF' ? <FileText className="w-6 h-6" /> : <FileCheck className="w-6 h-6" />}
              </div>
              <div className="overflow-hidden">
                <h4 className="font-bold text-on-surface truncate">{report.title}</h4>
                <p className="text-[10px] font-bold text-outline uppercase tracking-widest">{report.date} • {report.size}</p>
              </div>
            </div>
            <button 
              onClick={() => downloadFile(report.title)}
              className="p-2 text-outline hover:text-primary transition-colors flex-shrink-0"
            >
              <Download className="w-5 h-5" />
            </button>
          </div>
        ))}
      </div>

      <div className="bg-surface-container-lowest rounded-2xl border border-outline-variant/30 p-10 flex flex-col items-center justify-center text-center space-y-4">
        <div className="w-16 h-16 rounded-full bg-surface-container-high flex items-center justify-center mb-2">
          <Calendar className="w-8 h-8 text-outline" />
        </div>
        <h3 className="text-xl font-bold">Request Custom Period</h3>
        <p className="text-sm text-outline max-w-md mx-auto">Select a specific timeframe and data points to generate a comprehensive bespoke financial breakdown.</p>
        <button className="mt-4 px-8 py-3 bg-primary text-white font-bold rounded-xl shadow-md hover:brightness-110 transition-all">Select Parameters</button>
      </div>
    </div>
  );
};
