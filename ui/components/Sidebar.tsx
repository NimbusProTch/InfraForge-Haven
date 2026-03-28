"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { signOut } from "next-auth/react";
import {
  LayoutDashboard,
  FolderKanban,
  Activity,
  Settings,
  Anchor,
  LogOut,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { href: "/dashboard", label: "Home", icon: LayoutDashboard },
  { href: "/tenants", label: "Projects", icon: FolderKanban },
  { href: "/monitoring", label: "Monitoring", icon: Activity },
  { href: "/settings", label: "Settings", icon: Settings },
];

interface SidebarProps {
  userEmail?: string | null;
}

export function Sidebar({ userEmail }: SidebarProps) {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);

  return (
    <aside
      className={cn(
        "flex flex-col h-screen shrink-0 bg-zinc-950 border-r border-zinc-800 transition-all duration-200",
        collapsed ? "w-14" : "w-64"
      )}
    >
      {/* Logo */}
      <div className="flex items-center justify-between px-4 h-14 border-b border-zinc-800">
        <div className="flex items-center gap-2.5 min-w-0">
          <div className="w-7 h-7 rounded-md bg-emerald-600 flex items-center justify-center shrink-0">
            <Anchor className="w-3.5 h-3.5 text-white" />
          </div>
          {!collapsed && (
            <span className="font-semibold text-sm text-zinc-100 tracking-tight truncate">
              Haven
            </span>
          )}
        </div>
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="text-zinc-600 hover:text-zinc-300 transition-colors shrink-0 ml-1"
        >
          {collapsed ? (
            <ChevronRight className="w-3.5 h-3.5" />
          ) : (
            <ChevronLeft className="w-3.5 h-3.5" />
          )}
        </button>
      </div>

      {/* Nav */}
      <nav className="flex-1 p-2 space-y-0.5 overflow-y-auto">
        {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
          const isActive =
            pathname === href ||
            (href !== "/dashboard" && pathname.startsWith(href));
          return (
            <Link
              key={href}
              href={href}
              title={collapsed ? label : undefined}
              className={cn(
                "flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-colors",
                collapsed ? "justify-center px-2" : "",
                isActive
                  ? "bg-zinc-800 text-zinc-100 font-medium"
                  : "text-zinc-500 hover:text-zinc-200 hover:bg-zinc-800/50"
              )}
            >
              <Icon className="w-4 h-4 shrink-0" />
              {!collapsed && <span>{label}</span>}
            </Link>
          );
        })}
      </nav>

      {/* User + logout */}
      <div className="p-2 border-t border-zinc-800">
        <div
          className={cn(
            "flex items-center gap-2 px-3 py-2",
            collapsed ? "justify-center px-2" : ""
          )}
        >
          <div className="w-6 h-6 rounded-full bg-emerald-700 flex items-center justify-center shrink-0 text-xs text-white font-medium">
            {userEmail?.[0]?.toUpperCase() ?? "?"}
          </div>
          {!collapsed && (
            <>
              <span className="text-xs text-zinc-500 flex-1 truncate">
                {userEmail ?? "—"}
              </span>
              <button
                onClick={() => signOut({ callbackUrl: "/auth/signin" })}
                title="Sign out"
                className="text-zinc-600 hover:text-zinc-200 transition-colors shrink-0"
              >
                <LogOut className="w-3.5 h-3.5" />
              </button>
            </>
          )}
          {collapsed && (
            <button
              onClick={() => signOut({ callbackUrl: "/auth/signin" })}
              title="Sign out"
              className="text-zinc-600 hover:text-zinc-200 transition-colors"
            >
              <LogOut className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>
    </aside>
  );
}
