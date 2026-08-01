import { Monitor, Settings } from 'lucide-react';

interface SidebarProps {
  activeView: 'mission-control' | 'settings';
  onViewChange: (view: 'mission-control' | 'settings') => void;
}

export function Sidebar({ activeView, onViewChange }: SidebarProps) {
  return (
    <aside className="fixed left-0 top-0 h-full w-[64px] bg-surface-container-low border-r border-outline-variant flex flex-col items-center py-4 z-40">
      <div className="mb-8 text-primary">
        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
        </svg>
      </div>

      <nav className="flex flex-col gap-4 flex-1">
        <button
          onClick={() => onViewChange('mission-control')}
          className={`w-12 h-12 flex items-center justify-center rounded-lg transition-colors ${
            activeView === 'mission-control'
              ? 'bg-primary-container text-on-primary-container scale-95'
              : 'text-on-surface-variant hover:bg-surface-container-highest'
          }`}
          title="Mission Control"
        >
          <Monitor size={22} />
        </button>
        <button
          onClick={() => onViewChange('settings')}
          className={`w-12 h-12 flex items-center justify-center rounded-lg transition-colors ${
            activeView === 'settings'
              ? 'bg-primary-container text-on-primary-container scale-95'
              : 'text-on-surface-variant hover:bg-surface-container-highest'
          }`}
          title="Settings"
        >
          <Settings size={22} />
        </button>
      </nav>
    </aside>
  );
}
