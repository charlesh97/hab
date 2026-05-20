import { MotionData } from '../types';

interface MotionCardProps {
  motion: MotionData;
}

export function MotionCard({ motion }: MotionCardProps) {
  return (
    <div className="card-border bg-surface-container-low rounded-[20px] border border-outline-variant p-3 flex flex-col gap-3">
      <span className="data-label block text-label-caps text-outline">MOTION</span>
      <div className="grid grid-cols-2 gap-x-4 gap-y-2">
        <div className="flex flex-col">
          <span className="text-[10px] text-outline font-label-caps">GROUND SPEED</span>
          <span className="font-mono text-lg text-on-surface">
            {motion.gs_mps.toFixed(1)} <span className="text-[10px] opacity-50">m/s</span>
          </span>
        </div>
        <div className="flex flex-col">
          <span className="text-[10px] text-outline font-label-caps">VERT SPEED</span>
          <span className={`font-mono text-lg ${motion.vs_mps >= 0 ? 'text-secondary' : 'text-tertiary'}`}>
            {motion.vs_mps.toFixed(1)} <span className="text-[10px]">{motion.vs_mps >= 0 ? '\u25B2' : '\u25BC'} m/s</span>
          </span>
        </div>
        <div className="flex flex-col">
          <span className="text-[10px] text-outline font-label-caps">HEADING</span>
          <span className="font-mono text-lg text-on-surface">{motion.heading_deg.toFixed(1)}\u00B0</span>
        </div>
        <div className="flex flex-col">
          <span className="text-[10px] text-outline font-label-caps">COURSE</span>
          <span className="font-mono text-lg text-on-surface">{motion.cog_deg.toFixed(1)}\u00B0</span>
        </div>
      </div>

      <div className="border-t border-outline-variant/50 pt-2">
        <div className="text-[10px] text-outline font-label-caps mb-1">ACCELEROMETER</div>
        <div className="font-mono text-xs text-on-surface-variant">
          x:{motion.accel.x.toFixed(2)} y:{motion.accel.y.toFixed(2)} z:{motion.accel.z.toFixed(2)}
        </div>
      </div>

      <div>
        <div className="text-[10px] text-outline font-label-caps mb-1">GYROSCOPE</div>
        <div className="font-mono text-xs text-on-surface-variant">
          r:{motion.gyro_dps.r.toFixed(1)} p:{motion.gyro_dps.p.toFixed(1)} y:{motion.gyro_dps.y.toFixed(1)}
        </div>
      </div>

      <div>
        <div className="text-[10px] text-outline font-label-caps mb-1">ATTITUDE</div>
        <div className="font-mono text-xs text-on-surface-variant">
          roll {motion.att_deg.roll.toFixed(1)}\u00B0 pitch {motion.att_deg.pitch.toFixed(1)}\u00B0 yaw {motion.att_deg.yaw.toFixed(1)}\u00B0
        </div>
      </div>
    </div>
  );
}
