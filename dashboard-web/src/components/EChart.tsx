import * as echarts from "echarts";
import { useEffect, useRef } from "react";

interface Props {
  option: object;
  ariaLabel: string;
  height?: number;
}

export function EChart({ option, ariaLabel, height = 360 }: Props) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ref.current) return;
    const dark = document.documentElement.dataset.theme === "dark";
    const chart = echarts.init(ref.current, dark ? "dark" : undefined, { renderer: "canvas" });
    chart.setOption({
      backgroundColor: "transparent",
      aria: { enabled: true, decal: { show: true } },
      animation: false,
      ...option,
    } as echarts.EChartsOption);
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(ref.current);
    return () => {
      observer.disconnect();
      chart.dispose();
    };
  }, [option]);

  return <div ref={ref} className="chart" style={{ height }} role="img" aria-label={ariaLabel} />;
}
