import { useMemo } from 'react';
import { LineChart, Line, ReferenceLine, YAxis } from 'recharts';
import { MetricPoint } from '../types';

interface SparklineGraphProps {
  data: MetricPoint[];
  color: string;
  unitLabel: string;
  metricLabel: string;
  showZeroLine?: boolean;
}

function formatValue(value: number, metricLabel: string): string {
  if (metricLabel === 'ALT') return `${(value / 1000).toFixed(1)}k`;
  if (metricLabel === 'YAW') return value.toFixed(0);
  return value.toFixed(1);
}
export function SparklineGraph({
  data,
  color,
  unitLabel,
  metricLabel,
  showZeroLine = false,
}: SparklineGraphProps) {
  const currentValue = data.length > 0 ? data[data.length - 1].value : 0;

  const yTicks = useMemo(() => {
    if (data.length === 0) return [0, 0, 0];
    const values = data.map((d) => d.value);
    const min = Math.min(...values);
    const max = Math.max(...values);
    if (min === max) return [min, min, min];
    const step = (max - min) / 3;
    return [max, max - step, min];
  }, [data]);

  const domain = useMemo(() => {
    if (data.length === 0) return [0, 1] as [number, number];
    const values = data.map((d) => d.value);
    const min = Math.min(...values);
    const max = Math.max(...values);
    if (min === max) return [min - 1, max + 1] as [number, number];
    const padding = (max - min) * 0.1;
    return [min - padding, max + padding] as [number, number];
  }, [data]);

  if (data.length === 0) {
    return (
      <div>
        <div className="flex justify-between items-baseline mb-0.5">
          <span className="text-[9px] text-outline font-label-caps">{metricLabel}</span>
          <span>
            <span className="text-[11px] font-semibold text-on-surface">--</span>
            <span className="text-[8px] text-outline"> {unitLabel}</span>
          </span>
        </div>
        <div className="bg-surface-container-low rounded-[3px] h-12 flex items-center justify-center">
          <span className="text-[9px] text-outline">No data</span>
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="flex justify-between items-baseline mb-0.5">
        <span className="text-[9px] text-outline font-label-caps">{metricLabel}</span>
        <span>
          <span className="text-[11px] font-semibold text-on-surface">{formatValue(currentValue, metricLabel)}</span>
          <span className="text-[8px] text-outline"> {unitLabel}</span>
        </span>
      </div>
      <div className="bg-surface-container-low rounded-[3px] h-12 relative overflow-hidden">
        <LineChart
          width={9999}
          height={48}
          data={data}
          margin={{ top: 4, right: 36, bottom: 4, left: 0 }}
        >
          {showZeroLine && (
            <ReferenceLine y={0} stroke="#414753" strokeDasharray="3 3" strokeWidth={0.5} />
          )}
          <YAxis
            type="number"
            domain={domain}
            hide
          />
          <Line
            type="monotone"
            dataKey="value"
            stroke={color}
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>

        {/* Y-axis tick labels overlaid on right edge */}
        <div className="absolute right-1 pointer-events-none" style={{ top: 4, bottom: 4, display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
          {yTicks.map((tick, i) => (
            <span key={i} className="text-[6px] text-outline-variant text-right leading-none">
              {formatValue(tick, metricLabel)}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
