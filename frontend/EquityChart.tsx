'use client';

import { useEffect, useRef, useState } from 'react';
import { money, signedPercent } from './algoData';
import { tone } from './algoUi';
import styles from './algos.module.css';

/** One trading day on the curve. `pnl` is set only on days a trade closed. */
export type EquityPoint = { day: string; value: number; pnl?: number };
type Tip = { left: number; top: number; flip: boolean; point: EquityPoint };

const longDate = (day: string) => new Date(`${day}T00:00:00Z`).toLocaleDateString('en-IN', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' });
const lakh = (value: number) => `₹${(value / 100_000).toFixed(2)}L`;

/** A theme colour as rgba(), whatever notation the stylesheet uses (the chart's canvas needs plain rgb). */
function themeColor(host: HTMLElement, name: string, alpha = 1) {
  const probe = document.createElement('span');
  probe.style.color = `var(${name})`;
  host.appendChild(probe);
  const value = getComputedStyle(probe).color;
  probe.remove();
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = 1;
  const context = canvas.getContext('2d');
  if (!context) return `rgba(128, 128, 128, ${alpha})`;
  context.fillStyle = value;
  context.fillRect(0, 0, 1, 1);
  const [red, green, blue] = context.getImageData(0, 0, 1, 1).data;
  return `rgba(${red}, ${green}, ${blue}, ${alpha})`;
}

/** Backtest equity by trading day: green above the starting capital, red below it. Drag to pan, pinch or drag
 *  the date axis to zoom, double-click the axis to reset. */
export default function EquityChart({ points, base }: { points: EquityPoint[]; base: number }) {
  const host = useRef<HTMLDivElement>(null);
  const [tip, setTip] = useState<Tip | null>(null);
  const [theme, setTheme] = useState(0);

  useEffect(() => {                                   // redraw in the new colours when the app theme flips
    const watcher = new MutationObserver(() => setTheme(value => value + 1));
    watcher.observe(document.documentElement, { attributes: true, attributeFilter: ['class', 'data-theme'] });
    return () => watcher.disconnect();
  }, []);

  useEffect(() => {
    const element = host.current;
    if (!element || points.length < 2) return;
    let live = true, dispose = () => {};
    import('lightweight-charts').then(({ BaselineSeries, ColorType, CrosshairMode, LineStyle, LineType, createChart }) => {
      if (!live) return;
      const up = (alpha = 1) => themeColor(element, '--up', alpha), down = (alpha = 1) => themeColor(element, '--down', alpha);
      const muted = themeColor(element, '--muted-foreground'), border = themeColor(element, '--border');
      const chart = createChart(element, {
        autoSize: true,
        layout: { background: { type: ColorType.Solid, color: 'transparent' }, textColor: muted, fontSize: 11, fontFamily: getComputedStyle(element).fontFamily, attributionLogo: true },
        grid: { vertLines: { visible: false }, horzLines: { color: border } },
        rightPriceScale: { borderVisible: false, scaleMargins: { top: 0.14, bottom: 0.1 } },
        timeScale: { borderVisible: false, fixLeftEdge: true, fixRightEdge: true, minBarSpacing: 0.05 },
        crosshair: { mode: CrosshairMode.Magnet, vertLine: { color: muted, style: LineStyle.Dashed, width: 1, labelVisible: false }, horzLine: { color: muted, style: LineStyle.Dashed, width: 1, labelBackgroundColor: themeColor(element, '--foreground') } },
        handleScroll: { mouseWheel: false, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: false },
        handleScale: { mouseWheel: false, pinch: true, axisPressedMouseMove: { time: true, price: false }, axisDoubleClickReset: { time: true, price: true } },
        localization: { locale: 'en-IN', priceFormatter: lakh },
      });
      const series = chart.addSeries(BaselineSeries, {
        baseValue: { type: 'price', price: base }, lineWidth: 2, lineType: LineType.WithSteps,
        topLineColor: up(), topFillColor1: up(0.24), topFillColor2: up(0.02),
        bottomLineColor: down(), bottomFillColor1: down(0.02), bottomFillColor2: down(0.24),
        priceLineVisible: false, lastValueVisible: true, crosshairMarkerRadius: 4, crosshairMarkerBorderWidth: 2,
      });
      series.createPriceLine({ price: base, color: muted, lineStyle: LineStyle.Dotted, lineWidth: 1, axisLabelVisible: false, title: 'Start' });
      series.setData(points.map(point => ({ time: point.day, value: point.value })));
      chart.timeScale().fitContent();
      const byDay = new Map(points.map(point => [point.day, point]));
      chart.subscribeCrosshairMove(event => {
        const day = typeof event.time === 'string' ? event.time : null;
        const point = day ? byDay.get(day) : undefined;
        if (!event.point || !point || event.point.x < 0 || event.point.y < 0) { setTip(null); return; }
        const y = series.priceToCoordinate(point.value) ?? event.point.y;
        setTip({ left: event.point.x, top: Math.max(8, y - 12), flip: event.point.x > element.clientWidth - 250, point });
      });
      dispose = () => chart.remove();
    });
    return () => { live = false; setTip(null); dispose(); };
  }, [points, base, theme]);

  const first = points[0], last = points[points.length - 1];
  const change = tip ? tip.point.value - base : 0;
  return <div className={styles.equityBox}>
    <div ref={host} className={styles.equityCanvas} role="img" aria-label={`Backtest equity from ${longDate(first.day)} to ${longDate(last.day)}: ${money(first.value)} to ${money(last.value)}.`} />
    {tip && <div className={`${styles.equityTip} ${tip.flip ? styles.equityTipFlip : ''}`} style={{ left: tip.left, top: tip.top }}>
      <span>{longDate(tip.point.day)}</span>
      <b>{money(tip.point.value)}</b>
      <span>Since start <i className={tone(change)}>{change > 0 ? '+' : ''}{money(change)} · {signedPercent(change / base * 100)}</i></span>
      {tip.point.pnl != null && <span>Closed that day <i className={tone(tip.point.pnl)}>{tip.point.pnl > 0 ? '+' : ''}{money(tip.point.pnl)}</i></span>}
    </div>}
  </div>;
}
