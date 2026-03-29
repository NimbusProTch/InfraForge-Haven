"use client";

import { useMemo } from "react";

interface Span {
  text: string;
  style: React.CSSProperties;
}

const ANSI_COLORS: Record<number, string> = {
  30: "#4d4d4d",
  31: "#ff6b6b",
  32: "#69ff94",
  33: "#ffe66d",
  34: "#4fc3f7",
  35: "#e040fb",
  36: "#18ffff",
  37: "#e0e0e0",
  90: "#686868",
  91: "#ff5555",
  92: "#50fa7b",
  93: "#f1fa8c",
  94: "#bd93f9",
  95: "#ff79c6",
  96: "#8be9fd",
  97: "#f8f8f2",
};

function parseAnsi(text: string): Span[] {
  const spans: Span[] = [];
  let currentStyle: React.CSSProperties = {};
  // eslint-disable-next-line no-control-regex
  const parts = text.split(/(\x1b\[[0-9;]*m)/);

  for (const part of parts) {
    if (!part) continue;
    // eslint-disable-next-line no-control-regex
    if (/^\x1b\[/.test(part)) {
      const codes = part.slice(2, -1).split(";").map(Number);
      const newStyle: React.CSSProperties = { ...currentStyle };
      for (const code of codes) {
        if (code === 0) {
          Object.keys(newStyle).forEach((k) => delete (newStyle as Record<string, unknown>)[k]);
        } else if (code === 1) {
          newStyle.fontWeight = "bold";
        } else if (code === 2) {
          newStyle.opacity = 0.6;
        } else if (ANSI_COLORS[code]) {
          newStyle.color = ANSI_COLORS[code];
        }
      }
      currentStyle = newStyle;
    } else {
      spans.push({ text: part, style: { ...currentStyle } });
    }
  }
  return spans;
}

interface AnsiTerminalProps {
  content: string;
  className?: string;
  endRef?: React.RefObject<HTMLDivElement>;
}

export function AnsiTerminal({ content, className = "", endRef }: AnsiTerminalProps) {
  const spans = useMemo(() => parseAnsi(content), [content]);

  return (
    <pre
      className={`text-xs font-mono text-emerald-400/90 overflow-auto whitespace-pre-wrap break-all leading-relaxed ${className}`}
    >
      {spans.map((span, i) => (
        <span key={i} style={span.style}>
          {span.text}
        </span>
      ))}
      {endRef && <div ref={endRef} />}
    </pre>
  );
}
