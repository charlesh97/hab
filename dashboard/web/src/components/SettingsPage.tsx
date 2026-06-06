import { useState } from 'react';
import { X } from 'lucide-react';
import { SettingsTabs, SettingsTab } from './SettingsTabs';
import { SettingsDevice } from './SettingsDevice';
import { SettingsRf } from './SettingsRf';
import { SettingsDvbs2 } from './SettingsDvbs2';
import { SettingsPipeline } from './SettingsPipeline';
import { SettingsAbout } from './SettingsAbout';

interface SettingsPageProps {
  onClose: () => void;
}

export function SettingsPage({ onClose }: SettingsPageProps) {
  const [activeTab, setActiveTab] = useState<SettingsTab>('device');

  return (
    <div className="ml-[64px] mt-[72px] h-[calc(100vh-72px)] overflow-y-auto">
      <div className="p-8 max-w-[1400px] mx-auto">
        <div className="flex justify-between items-start mb-8">
          <h1 className="font-mission-name text-4xl font-bold tracking-tight text-on-surface">SETTINGS</h1>
          <button onClick={onClose} className="p-2 border border-outline-variant rounded-full hover:bg-surface-container-highest transition-colors text-on-surface-variant">
            <X size={20} />
          </button>
        </div>

        <SettingsTabs activeTab={activeTab} onTabChange={setActiveTab} />

        {activeTab === 'device' && <SettingsDevice />}
        {activeTab === 'rf' && <SettingsRf />}
        {activeTab === 'dvbs2' && <SettingsDvbs2 />}
        {activeTab === 'pipeline' && <SettingsPipeline />}
        {activeTab === 'about' && <SettingsAbout />}
      </div>
    </div>
  );
}
