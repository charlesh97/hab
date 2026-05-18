import React, { useState } from 'react';
import { VideoIcon, RadioIcon, TerminalIcon } from 'lucide-react';
import { Packet } from '../types';
import { VideoFeeds } from './VideoFeeds';
import { RfConfig } from './RfConfig';
import { DataStream } from './DataStream';
interface LowerTabsProps {
  packets: Packet[];
  sendCommand?: (cmd: string, data?: any) => void;
  engineStatus?: any;
}
type TabId = 'video' | 'rf' | 'data';
export function LowerTabs({ packets, sendCommand, engineStatus }: LowerTabsProps) {
  const [activeTab, setActiveTab] = useState<TabId>('video');
  return (
    <div className="flex flex-col bg-[rgba(18,20,22,0.6)] overflow-hidden">
      {/* Tab Header */}
      <div className="flex border-b border-white/5 bg-[rgba(18,20,22,0.8)] shrink-0">
        <TabButton
          id="video"
          label="Video Feeds"
          icon={<VideoIcon className="w-4 h-4" />}
          isActive={activeTab === 'video'}
          onClick={() => setActiveTab('video')} />
        
        <TabButton
          id="rf"
          label="RF Config"
          icon={<RadioIcon className="w-4 h-4" />}
          isActive={activeTab === 'rf'}
          onClick={() => setActiveTab('rf')} />
        
        <TabButton
          id="data"
          label="Data Stream"
          icon={<TerminalIcon className="w-4 h-4" />}
          isActive={activeTab === 'data'}
          onClick={() => setActiveTab('data')} />
        
      </div>

      {/* Tab Content */}
      <div className="min-h-[400px] max-h-[600px] overflow-y-auto relative">
        {activeTab === 'video' && <VideoFeeds />}
        {activeTab === 'rf' && <RfConfig sendCommand={sendCommand} engineStatus={engineStatus} />}
        {activeTab === 'data' && <DataStream packets={packets} />}
      </div>
    </div>);

}
function TabButton({
  id,
  label,
  icon,
  isActive,
  onClick






}: {id: string;label: string;icon: React.ReactNode;isActive: boolean;onClick: () => void;}) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-2 px-4 py-3 text-sm font-semibold transition-colors border-b-2 ${isActive ? 'border-sky-500 text-sky-400 bg-[rgba(18,20,22,0.6)]' : 'border-transparent text-slate-500 hover:text-slate-300 hover:bg-white/5'}`}>
      
      {icon}
      {label}
    </button>);

}