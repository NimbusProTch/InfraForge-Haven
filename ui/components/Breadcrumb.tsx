"use client";

import Link from "next/link";
import { ChevronRight } from "lucide-react";

export interface BreadcrumbItem {
  label: string;
  href?: string;
}

export function Breadcrumb({ items }: { items: BreadcrumbItem[] }) {
  return (
    <nav className="flex items-center gap-2 text-sm text-gray-500 dark:text-zinc-400 mb-6 font-medium">
      {items.map((item, i) => (
        <div key={i} className="flex items-center gap-2">
          {i > 0 && <ChevronRight className="w-3.5 h-3.5 text-gray-400 shrink-0" />}
          {item.href ? (
            <Link
              href={item.href}
              className="hover:text-gray-900 dark:hover:text-white transition-colors"
            >
              {item.label}
            </Link>
          ) : (
            <span className="text-gray-800 dark:text-white font-semibold">{item.label}</span>
          )}
        </div>
      ))}
    </nav>
  );
}
