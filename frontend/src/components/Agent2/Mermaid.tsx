import React, { useEffect, useRef,useState } from 'react';
import mermaid from 'mermaid';

// Initialize mermaid with your UI theme

mermaid.initialize({
  startOnLoad: false,
  theme: "dark",
  securityLevel: "loose",
  themeVariables: {
    background: "#020617",

    primaryColor: "#0f172a",
    primaryBorderColor: "#38bdf8",
    primaryTextColor: "#e5e7eb",

    secondaryColor: "#1e293b",
    secondaryBorderColor: "#22c55e",
    secondaryTextColor: "#e5e7eb",

    lineColor: "#94a3b8",
    edgeLabelBackground: "#020617",

    fontFamily: "JetBrains Mono, monospace",
    fontSize: "14px",

    clusterBkg: "#020617",
    clusterBorder: "#334155"
  }
});


export const Mermaid: React.FC<{ chart: string }> = ({ chart }) => {
  const ref = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [svg, setSvg] = useState<string>("");
  useEffect(() => {
    const renderChart = async () => {
      if (chart) {
        try {
          // Generate a unique ID to prevent conflicts with multiple charts
          const id = `mermaid-${Math.random().toString(36).substring(2, 9)}`;
          const { svg: renderedSvg } = await mermaid.render(id, chart);
          setSvg(renderedSvg);
        } catch (error) {
          console.error("Mermaid render failed:", error);
          setSvg('<div class="text-red-500 p-4">Invalid Diagram Syntax</div>');
        }
      }
    };

    renderChart();
  }, [chart]);

  return (
  <div
    ref={containerRef}
    className="
      mermaid
      w-full
      max-w-full
      overflow-x-auto
      bg-[#020617]
      rounded-lg
      p-6
      border
      border-slate-800
    "
    dangerouslySetInnerHTML={{ __html: svg }}
  />
);

};