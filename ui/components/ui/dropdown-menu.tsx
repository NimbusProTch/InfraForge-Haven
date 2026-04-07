"use client";

import { useState, useRef, useEffect } from "react";

interface DropdownMenuProps {
  trigger: React.ReactNode;
  children: React.ReactNode;
  align?: "left" | "right";
}

export function DropdownMenu({ trigger, children, align = "right" }: DropdownMenuProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    if (open) {
      document.addEventListener("mousedown", handleClickOutside);
      return () => document.removeEventListener("mousedown", handleClickOutside);
    }
  }, [open]);

  return (
    <div className="relative" ref={ref}>
      <div onClick={() => setOpen(!open)}>{trigger}</div>
      {open && (
        <div
          className={`absolute top-full mt-1 ${align === "right" ? "right-0" : "left-0"} z-50 min-w-[200px] bg-white dark:bg-zinc-900 border border-gray-200 dark:border-zinc-800 rounded-xl shadow-xl py-1.5 animate-in fade-in-0 zoom-in-95`}
          onClick={() => setOpen(false)}
        >
          {children}
        </div>
      )}
    </div>
  );
}

interface DropdownItemProps {
  onClick?: () => void;
  children: React.ReactNode;
  variant?: "default" | "danger";
  disabled?: boolean;
  href?: string;
}

export function DropdownItem({ onClick, children, variant = "default", disabled, href }: DropdownItemProps) {
  const base = "flex items-center gap-2.5 w-full px-3.5 py-2 text-sm font-medium transition-colors text-left";
  const variants = {
    default: "text-gray-700 dark:text-zinc-300 hover:bg-gray-50 dark:hover:bg-zinc-800",
    danger: "text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-500/10",
  };

  if (href) {
    return (
      <a href={href} target="_blank" rel="noopener noreferrer" className={`${base} ${variants[variant]}`}>
        {children}
      </a>
    );
  }

  return (
    <button onClick={onClick} disabled={disabled} className={`${base} ${variants[variant]} disabled:opacity-50`}>
      {children}
    </button>
  );
}

export function DropdownDivider() {
  return <div className="my-1.5 border-t border-gray-100 dark:border-zinc-800" />;
}
