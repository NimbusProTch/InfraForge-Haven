"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { signOut } from "next-auth/react";
import { useTheme } from "next-themes";
import {
  LayoutDashboard,
  Building2,
  LogOut,
  Anchor,
  Sun,
  Moon,
} from "lucide-react";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/tenants", label: "Tenants", icon: Building2 },
];

interface AppShellProps {
  children: React.ReactNode;
  userEmail?: string | null;
}

export function AppShell({ children, userEmail }: AppShellProps) {
  const pathname = usePathname();
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      {/* Sidebar */}
      <aside className="w-56 flex flex-col shrink-0 bg-white dark:bg-[#111] border-r border-gray-200 dark:border-[#222]">
        {/* Logo */}
        <div className="flex items-center gap-2.5 px-4 h-14 border-b border-gray-200 dark:border-[#222]">
          <div className="w-7 h-7 rounded-md bg-blue-600 flex items-center justify-center shrink-0">
            <Anchor className="w-3.5 h-3.5 text-white" />
          </div>
          <span className="font-semibold text-sm text-gray-900 dark:text-white tracking-tight">
            Haven
          </span>
        </div>

        {/* Nav */}
        <nav className="flex-1 p-2 space-y-0.5 overflow-y-auto">
          {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
            const isActive =
              pathname === href ||
              (href !== "/dashboard" && pathname.startsWith(href + "/")) ||
              (href !== "/dashboard" && pathname === href);
            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  "flex items-center gap-2.5 px-3 py-2 rounded-md text-sm transition-colors",
                  isActive
                    ? "bg-blue-50 dark:bg-[#1e293b] text-blue-700 dark:text-white font-medium"
                    : "text-gray-500 dark:text-[#888] hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-[#1a1a1a]"
                )}
              >
                <Icon className="w-4 h-4 shrink-0" />
                {label}
              </Link>
            );
          })}
        </nav>

        {/* Bottom: theme toggle + user */}
        <div className="p-2 border-t border-gray-200 dark:border-[#222] space-y-1">
          {/* Theme toggle */}
          <button
            onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
            className="flex items-center gap-2.5 w-full px-3 py-2 rounded-md text-sm text-gray-500 dark:text-[#888] hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-[#1a1a1a] transition-colors"
          >
            {mounted ? (
              theme === "dark" ? (
                <Sun className="w-4 h-4 shrink-0" />
              ) : (
                <Moon className="w-4 h-4 shrink-0" />
              )
            ) : (
              <div className="w-4 h-4 shrink-0" />
            )}
            {mounted ? (theme === "dark" ? "Light mode" : "Dark mode") : "Toggle theme"}
          </button>

          {/* User */}
          <div className="flex items-center gap-2 px-3 py-2">
            <div className="w-6 h-6 rounded-full bg-blue-600 flex items-center justify-center shrink-0 text-xs text-white font-medium">
              {userEmail?.[0]?.toUpperCase() ?? "?"}
            </div>
            <span className="text-xs text-gray-500 dark:text-[#888] flex-1 truncate">
              {userEmail ?? "—"}
            </span>
            <button
              onClick={() => signOut({ callbackUrl: "/auth/signin" })}
              title="Sign out"
              className="text-gray-400 dark:text-[#555] hover:text-gray-900 dark:hover:text-white transition-colors shrink-0"
            >
              <LogOut className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto bg-gray-50 dark:bg-[#0a0a0a]">
        {children}
      </main>
    </div>
  );
}
