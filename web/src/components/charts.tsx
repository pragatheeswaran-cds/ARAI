// Small SVG charts for the dashboard and the product screen. Each one states its numbers as text too (labels or a legend),
// so nothing is readable from colour alone.
import type { ReactNode } from "react";

export const SLATE = ["#374151", "#6b7280", "#9ca3af", "#d1d5db", "#e5e7eb"];
export const BLUE = ["#1d5fd0", "#4a90f0", "#9cc5fb", "#c9d6e6", "#e2e8f0"];

type Point = { x: string; y: number };
export type Series = { name: string; color: string; dashed?: boolean; points: Point[] };

const W = 720;
const H = 220;
const PAD = { left: 56, right: 12, top: 12, bottom: 28 };

function niceMax(value: number): number {
  if (value <= 0) return 1;
  const power = 10 ** Math.floor(Math.log10(value));
  const lead = value / power;
  return (lead <= 1 ? 1 : lead <= 2 ? 2 : lead <= 5 ? 5 : 10) * power;
}

/** Lines over a shared x axis; the first series gives the x labels. `format` writes the y ticks. */
export function LineChart({ series, format, label }: { series: Series[]; format: (value: number) => string; label: string }) {
  const length = Math.max(0, ...series.map((s) => s.points.length));
  if (length < 2) return <p className="muted">Not enough days in this range to draw a trend.</p>;
  const top = niceMax(Math.max(...series.flatMap((s) => s.points.map((p) => p.y))));
  const x = (index: number) => PAD.left + (index / (length - 1)) * (W - PAD.left - PAD.right);
  const y = (value: number) => PAD.top + (1 - value / top) * (H - PAD.top - PAD.bottom);
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((share) => share * top);
  const labels = series[0].points;
  const step = Math.max(1, Math.ceil(labels.length / 8));
  return (
    <figure className="plot">
      <div className="legend">
        {series.map((s) => (
          <span key={s.name}>
            <i style={{ background: s.color, opacity: s.dashed ? 0.6 : 1 }} />
            {s.name}
          </span>
        ))}
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label} className="curve">
        {ticks.map((tick) => (
          <g key={tick}>
            <line x1={PAD.left} x2={W - PAD.right} y1={y(tick)} y2={y(tick)} stroke="#e5e7eb" />
            <text x={PAD.left - 8} y={y(tick) + 4} textAnchor="end" fontSize="11" fill="#6b7280">
              {format(tick)}
            </text>
          </g>
        ))}
        {labels.map((point, index) =>
          index % step === 0 ? (
            <text key={point.x + index} x={x(index)} y={H - 8} textAnchor="middle" fontSize="11" fill="#6b7280">
              {point.x}
            </text>
          ) : null,
        )}
        {series.map((s) => (
          <polyline
            key={s.name}
            fill="none"
            stroke={s.color}
            strokeWidth={s.dashed ? 1.5 : 2}
            strokeDasharray={s.dashed ? "5 4" : undefined}
            points={s.points.map((p, index) => `${x(index).toFixed(1)},${y(p.y).toFixed(1)}`).join(" ")}
          />
        ))}
      </svg>
    </figure>
  );
}

export type Slice = { name: string; value: number; color: string };

/** A ring with the total in the middle and a legend that carries every number. */
export function Donut({ slices, center, sub, format }: { slices: Slice[]; center: string; sub: string; format: (value: number) => string }) {
  const total = slices.reduce((sum, s) => sum + s.value, 0);
  const R = 52;
  const C = 2 * Math.PI * R;
  let offset = 0;
  return (
    <div className="donut">
      <svg viewBox="0 0 140 140" width="140" height="140" role="img" aria-label={`${center} ${sub}`}>
        <circle cx="70" cy="70" r={R} fill="none" stroke="#eef0f3" strokeWidth="22" />
        {total > 0 &&
          slices.map((s) => {
            const length = (s.value / total) * C;
            const circle = (
              <circle
                key={s.name}
                cx="70"
                cy="70"
                r={R}
                fill="none"
                stroke={s.color}
                strokeWidth="22"
                strokeDasharray={`${length} ${C - length}`}
                strokeDashoffset={-offset}
                transform="rotate(-90 70 70)"
              />
            );
            offset += length;
            return circle;
          })}
        <text x="70" y="68" textAnchor="middle" fontSize="18" fontWeight="600" fill="#1f2937">
          {center}
        </text>
        <text x="70" y="84" textAnchor="middle" fontSize="10" fill="#6b7280">
          {sub}
        </text>
      </svg>
      <ul className="donut-legend">
        {slices.map((s) => (
          <li key={s.name}>
            <i style={{ background: s.color }} />
            <span>{s.name}</span>
            <span className="muted">{total > 0 ? Math.round((s.value / total) * 100) + "%" : "n/a"}</span>
            <strong>{format(s.value)}</strong>
          </li>
        ))}
      </ul>
    </div>
  );
}

export type Bar = { name: string; value: number; note?: ReactNode };

/** Vertical bars with the value written above each one. */
export function VBars({ bars, format, label }: { bars: Bar[]; format: (value: number) => string; label: string }) {
  const top = Math.max(0, ...bars.map((b) => b.value)) || 1;
  return (
    <div className="vbars" role="img" aria-label={label}>
      {bars.map((bar) => (
        <div key={bar.name} className="vbar">
          <span className="vbar-value">{format(bar.value)}</span>
          <span className="vbar-fill" style={{ height: `${Math.max(2, (bar.value / top) * 100)}%` }} />
          <span className="vbar-name">{bar.name}</span>
        </div>
      ))}
    </div>
  );
}

/** Horizontal bars, one row each, with the value at the end of the row. */
export function HBars({ bars, format, max }: { bars: Bar[]; format: (value: number) => string; max?: number }) {
  const top = max ?? (Math.max(0, ...bars.map((b) => b.value)) || 1);
  return (
    <div className="hbars">
      {bars.map((bar) => (
        <div key={bar.name} className="hbar">
          <span className="hbar-name">{bar.name}</span>
          <span className="hbar-track">
            <span className="hbar-fill" style={{ width: `${Math.min(100, (bar.value / top) * 100)}%` }} />
          </span>
          <span className="hbar-value">
            {format(bar.value)}
            {bar.note}
          </span>
        </div>
      ))}
    </div>
  );
}
