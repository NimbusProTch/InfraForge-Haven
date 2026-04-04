"use client";

import { useMemo } from "react";

interface Span {
  text: string;
  style: React.CSSProperties;
}

// Muted enterprise color palette (VS Code inspired)
const ANSI_COLORS: Record<number, string> = {
  30: "#6b7280", // gray
  31: "#f87171", // red (muted)
  32: "#86efac", // green (muted)
  33: "#fcd34d", // yellow (muted)
  34: "#93c5fd", // blue (muted)
  35: "#c4b5fd", // purple (muted)
  36: "#67e8f9", // cyan (muted)
  37: "#d1d5db", // light gray
  90: "#9ca3af", // bright gray
  91: "#fca5a5", // bright red
  92: "#a7f3d0", // bright green
  93: "#fde68a", // bright yellow
  94: "#bfdbfe", // bright blue
  95: "#ddd6fe", // bright purple
  96: "#a5f3fc", // bright cyan
  97: "#f3f4f6", // white
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
      className={`text-[13px] font-mono text-zinc-300 overflow-auto whitespace-pre-wrap break-all leading-relaxed ${className}`}
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
