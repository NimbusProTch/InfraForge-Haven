"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useSession, signOut } from "next-auth/react";
import { useTheme } from "next-themes";
import {
  LayoutDashboard,
  Building2,
  FolderKanban,
  Activity,
  ListOrdered,
  Settings,
  LogOut,
  Anchor,
  Sun,
  Moon,
} from "lucide-react";
import { cn } from "@/lib/utils";

const NAV_SECTIONS = [
  {
    label: "Platform",
    items: [
      { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
      { href: "/tenants", label: "Projects", icon: FolderKanban },
      { href: "/organizations", label: "Organizations", icon: Building2 },
    ],
  },
  {
    label: "Operations",
    items: [
      { href: "/platform/queue", label: "Build Queue", icon: ListOrdered },
    ],
  },
];

interface AppShellProps {
  children: React.ReactNode;
  userEmail?: string | null;
}

export function AppShell({ children, userEmail }: AppShellProps) {
  const pathname = usePathname();
  const { theme, setTheme } = useTheme();
  const { data: session } = useSession();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const [sessionExpired, setSessionExpired] = useState(false);

  // Auto-logout when Keycloak refresh token expires
  useEffect(() => {
    const s = session as typeof session & { error?: string };
    if (s?.error === "RefreshTokenExpired" || s?.error === "RefreshTokenError") {
      setSessionExpired(true);
      const timer = setTimeout(() => {
        signOut({ callbackUrl: "/auth/signin" });
      }, 3000);
      return () => clearTimeout(timer);
    }
  }, [session]);

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      {/* Session expired toast */}
      {sessionExpired && (
        <div className="fixed top-4 right-4 z-[100] flex items-center gap-3 bg-red-600 text-white px-5 py-3 rounded-lg shadow-xl animate-in slide-in-from-top-2 duration-300">
          <LogOut className="w-4 h-4 shrink-0" />
          <div>
            <p className="text-sm font-semibold">Session expired</p>
            <p className="text-xs text-red-100">Redirecting to login...</p>
          </div>
        </div>
      )}
      {/* Sidebar — Creative Tim Material Dashboard style */}
      <aside className="w-64 flex flex-col shrink-0 bg-gradient-to-b from-gray-900 via-gray-800 to-gray-900 shadow-xl"
        style={{ backgroundImage: "linear-gradient(180deg, rgba(0,0,0,0.8) 0%, rgba(0,0,0,0.9) 100%), url('/sidebar-bg.jpg')", backgroundSize: "cover" }}
      >
        {/* Logo */}
        <div className="flex items-center gap-2.5 px-5 h-16 border-b border-white/10">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-emerald-400 to-emerald-600 shadow-md flex items-center justify-center shrink-0">
            <Anchor className="w-4 h-4 text-white" />
          </div>
          <span className="font-bold text-sm text-white tracking-tight">
            Haven Platform
          </span>
        </div>

        {/* Nav */}
        <nav className="flex-1 px-3 py-4 overflow-y-auto">
          {NAV_SECTIONS.map((section) => (
            <div key={section.label} className="mb-5">
              <p className="px-3 mb-2 text-xs font-bold uppercase tracking-widest text-white/40">
                {section.label}
              </p>
              <div className="space-y-1">
                {section.items.map(({ href, label, icon: Icon }) => {
                  const isActive =
                    pathname === href ||
                    (href !== "/dashboard" && pathname.startsWith(href + "/")) ||
                    (href !== "/dashboard" && pathname === href);
                  return (
                    <Link
                      key={href}
                      href={href}
                      className={cn(
                        "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-all",
                        isActive
                          ? "bg-white/15 text-white font-semibold shadow-sm"
                          : "text-white/60 hover:text-white hover:bg-white/10"
                      )}
                    >
                      <Icon className="w-4 h-4 shrink-0" />
                      {label}
                    </Link>
                  );
                })}
              </div>
            </div>
          ))}
        </nav>

        {/* Bottom: theme toggle + user */}
        <div className="px-3 py-3 border-t border-white/10 space-y-1">
          {/* Theme toggle */}
          <button
            onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
            className="flex items-center gap-3 w-full px-3 py-2.5 rounded-lg text-sm text-white/60 hover:text-white hover:bg-white/10 transition-all"
          >
            {mounted ? (
              theme === "dark" ? <Sun className="w-4 h-4 shrink-0" /> : <Moon className="w-4 h-4 shrink-0" />
            ) : (
              <div className="w-4 h-4 shrink-0" />
            )}
            {mounted ? (theme === "dark" ? "Light mode" : "Dark mode") : "Toggle theme"}
          </button>

          {/* User */}
          <div className="flex items-center gap-2.5 px-3 py-2.5">
            <div className="w-7 h-7 rounded-full bg-gradient-to-br from-blue-400 to-blue-600 flex items-center justify-center shrink-0 text-xs text-white font-bold shadow-sm">
              {userEmail?.[0]?.toUpperCase() ?? "?"}
            </div>
            <span className="text-xs text-white/50 flex-1 truncate">{userEmail ?? "—"}</span>
            <button
              onClick={() => signOut({ callbackUrl: "/auth/signin" })}
              title="Sign out"
              className="text-white/30 hover:text-white transition-colors shrink-0"
            >
              <LogOut className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto bg-[#f4f6f8] dark:bg-[#0a0a0a]">
        {children}
      </main>
    </div>
  );
}
