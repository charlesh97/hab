import { Cpu, Radio, Satellite, GitBranch, HelpCircle } from 'lucide-react';

export type SettingsTab = 'device' | 'rf' | 'dvbs2' | 'pipeline' | 'about';

interface SettingsTabsProps {
  activeTab: SettingsTab;
  onTabChange: (tab: SettingsTab) => void;
}

const tabs: { key: SettingsTab; label: string; Icon: typeof Cpu }[] = [
  { key: 'device', label: 'DEVICE', Icon: Cpu },
  { key: 'rf', label: 'RF', Icon: Radio },
  { key: 'dvbs2', label: 'DVB-S2', Icon: Satellite },
  { key: 'pipeline', label: 'PIPELINE', Icon: GitBranch },
  { key: 'about', label: 'ABOUT', Icon: HelpCircle },
];

export function SettingsTabs({ activeTab, onTabChange }: SettingsTabsProps) {
  return (
    <nav className="flex gap-2 mb-10 overflow-x-auto pb-2">
      {tabs.map(({ key, label, Icon }) => (
        <button
          key={key}
          onClick={() => onTabChange(key)}
          className={`flex items-center gap-2 px-6 py-3 rounded-full font-label-caps whitespace-nowrap transition-colors ${
            activeTab === key
              ? 'bg-telemetry-blue text-white'
              : 'bg-surface-container-high text-on-surface-variant hover:bg-surface-container-highest'
          }`}
        >
          <Icon size={18} /> {label}
        </button>
      ))}
    </nav>
  );
}
