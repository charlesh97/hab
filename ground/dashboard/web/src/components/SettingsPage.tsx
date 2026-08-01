import { useState } from 'react';
import { X } from 'lucide-react';
import { SettingsTabs, SettingsTab } from './SettingsTabs';
import { SettingsDevice } from './SettingsDevice';
import { SettingsRf } from './SettingsRf';
import { SettingsAbout } from './SettingsAbout';

interface SettingsPageProps {
  onClose: () => void;
  sendCommand: (command: string, data?: any) => void;
  sdrStatus: any;
  engineStatus: any;
  connected: boolean;
}

export function SettingsPage({ onClose, sendCommand, sdrStatus, engineStatus, connected }: SettingsPageProps) {
  const [activeTab, setActiveTab] = useState<SettingsTab>('device');
  const [selectedSerial, setSelectedSerial] = useState('');

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

        <div style={{ display: activeTab === 'device' ? 'block' : 'none' }}>
          <SettingsDevice
            connected={connected}
            sdrStatus={sdrStatus}
            engineStatus={engineStatus}
            selectedSerial={selectedSerial}
            onSerialChange={setSelectedSerial}
            sendCommand={sendCommand}
          />
        </div>
        <div style={{ display: activeTab === 'rf' ? 'block' : 'none' }}>
          <SettingsRf sendCommand={sendCommand} sdrStatus={sdrStatus} selectedSerial={selectedSerial} />
        </div>
        <div style={{ display: activeTab === 'about' ? 'block' : 'none' }}>
          <SettingsAbout />
        </div>
      </div>
    </div>
  );
}
