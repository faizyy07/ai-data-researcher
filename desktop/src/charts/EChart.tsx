import { memo, useEffect, useRef } from "react"; import * as echarts from "echarts";
function EChartBase({ option, dark, height = 260 }: { option: Record<string, unknown>; dark: boolean; height?: number }) {
  const el = useRef<HTMLDivElement>(null); const chart = useRef<echarts.ECharts | null>(null);
  useEffect(() => { if (!el.current) return; const c = echarts.init(el.current, dark ? "dark" : undefined, { renderer: "canvas" }); chart.current = c;
    c.setOption({ backgroundColor: "transparent", grid: { left: 48, right: 16, top: 44, bottom: 40 }, ...option }, true);
    const ro = new ResizeObserver(() => c.resize()); ro.observe(el.current); return () => { ro.disconnect(); c.dispose(); }; }, [dark, option]);
  return <div ref={el} style={{ height }} role="img" aria-label="chart" />;
}
export const EChart = memo(EChartBase);
