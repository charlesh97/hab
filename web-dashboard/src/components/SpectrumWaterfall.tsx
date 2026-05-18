import React, { useEffect, useRef } from 'react';

interface SpectrumWaterfallProps {
  spectrumData: { f: number[]; p: number[]; fc: number; span: number } | null;
  height?: number;
}

export function SpectrumWaterfall({ spectrumData, height = 200 }: SpectrumWaterfallProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const waterfallRef = useRef<ImageData[]>([]);
  const maxLines = 200;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !spectrumData) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const { p: power, f: freqs } = spectrumData;
    if (!power || power.length < 2) return;

    const w = canvas.width;
    const h = canvas.height;

    // Create a single row of the waterfall
    const rowData = ctx.createImageData(w, 1);
    const binCount = power.length;

    for (let x = 0; x < w; x++) {
      const idx = Math.floor((x / w) * binCount);
      const dB = power[idx] || -120;

      // Map dB range [-120, -20] to color
      const normalized = Math.max(0, Math.min(1, (dB + 120) / 100));
      
      // Color gradient: dark blue -> blue -> cyan -> green -> yellow -> red
      let r, g, b;
      if (normalized < 0.25) {
        // Dark blue to blue
        const t = normalized / 0.25;
        r = 0; g = Math.floor(t * 60); b = Math.floor(80 + t * 175);
      } else if (normalized < 0.5) {
        // Blue to cyan
        const t = (normalized - 0.25) / 0.25;
        r = 0; g = Math.floor(60 + t * 140); b = 255;
      } else if (normalized < 0.75) {
        // Cyan to yellow
        const t = (normalized - 0.5) / 0.25;
        r = Math.floor(t * 255); g = 200; b = Math.floor(255 * (1 - t));
      } else {
        // Yellow to red
        const t = (normalized - 0.75) / 0.25;
        r = 255; g = Math.floor(200 * (1 - t)); b = 0;
      }

      const px = x * 4;
      rowData.data[px] = r;
      rowData.data[px + 1] = g;
      rowData.data[px + 2] = b;
      rowData.data[px + 3] = 255;
    }

    // Add to waterfall buffer
    waterfallRef.current.push(rowData);
    if (waterfallRef.current > maxLines) {
      waterfallRef.current = waterfallRef.current.slice(-maxLines);
    }

    // Draw waterfall
    ctx.clearRect(0, 0, w, h);
    
    // Fill background
    ctx.fillStyle = '#0a0a0b';
    ctx.fillRect(0, 0, w, h);

    // Draw each row
    const lines = waterfallRef.current.length;
    const start = Math.max(0, lines - h);
    for (let i = start; i < lines; i++) {
      const rowIdx = i - start;
      if (rowIdx < h) {
        ctx.putImageData(waterfallRef.current[i], 0, rowIdx);
      }
    }

    // Center frequency label
    ctx.fillStyle = 'rgba(255,255,255,0.5)';
    ctx.font = '10px JetBrains Mono, monospace';
    ctx.textAlign = 'center';
    const centerFreq = (spectrumData.fc || 915e6) / 1e6;
    ctx.fillText(`${centerFreq.toFixed(3)} MHz`, w / 2, h - 6);

    // Left edge freq
    if (freqs.length > 0) {
      ctx.textAlign = 'left';
      const leftFreq = freqs[0] / 1e6;
      ctx.fillText(`${leftFreq.toFixed(1)}`, 4, h - 6);
      
      ctx.textAlign = 'right';
      const rightFreq = freqs[freqs.length - 1] / 1e6;
      ctx.fillText(`${rightFreq.toFixed(1)}`, w - 4, h - 6);
    }
  }, [spectrumData]);

  return (
    <div className="relative w-full" style={{ height }}>
      <canvas
        ref={canvasRef}
        width={600}
        height={height}
        className="w-full h-full rounded-lg"
        style={{ background: '#0a0a0b' }}
      />
      <div className="absolute top-2 left-3 text-[10px] font-mono text-white/40">
        SPECTRUM
      </div>
      <div className="absolute top-2 right-3 text-[10px] font-mono text-white/30">
        dB
      </div>
    </div>
  );
}
