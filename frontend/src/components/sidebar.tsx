"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  LayoutDashboard,
  Layers,
  DollarSign,
  Shield,
  Settings,
} from "lucide-react";
import { cn } from "@/lib/utils";

const navItems = [
  { label: "Dashboard", path: "/", icon: LayoutDashboard },
  { label: "Pillar Drilldown", path: "/pillar-drilldown", icon: Layers },
  { label: "Cost & Efficiency", path: "/cost-efficiency", icon: DollarSign },
  { label: "Availability", path: "/availability", icon: Shield },
  { label: "Settings", path: "/settings", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();
  const [expanded, setExpanded] = useState(false);

  return (
    <aside
      onMouseEnter={() => setExpanded(true)}
      onMouseLeave={() => setExpanded(false)}
      className={cn(
        "fixed left-0 top-0 z-50 flex h-screen flex-col border-r border-white/[0.06] bg-[#0a0b10]/80 backdrop-blur-xl transition-all duration-300 ease-in-out",
        expanded ? "w-[220px]" : "w-[72px]"
      )}
    >
      {/* Logo */}
      <div className="flex h-16 items-center gap-3 border-b border-white/[0.06] px-5">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-cyan-400 shadow-lg shadow-indigo-500/20">
          <Activity className="h-5 w-5 text-white" />
        </div>
        <span
          className={cn(
            "whitespace-nowrap text-sm font-semibold tracking-wide text-slate-100 transition-opacity duration-200",
            expanded ? "opacity-100" : "opacity-0"
          )}
        >
          Obs KPI
        </span>
      </div>

      {/* Navigation */}
      <nav className="mt-4 flex flex-1 flex-col gap-1 px-3">
        {navItems.map((item) => {
          const isActive =
            item.path === "/"
              ? pathname === "/"
              : pathname.startsWith(item.path);
          const Icon = item.icon;

          return (
            <Link
              key={item.path}
              href={item.path}
              className={cn(
                "group relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-all duration-200",
                isActive
                  ? "bg-indigo-500/10 text-indigo-300 shadow-[0_0_20px_rgba(99,102,241,0.15)]"
                  : "text-slate-400 hover:bg-white/[0.04] hover:text-slate-200"
              )}
            >
              {/* Active accent bar */}
              {isActive && (
                <div className="absolute -left-3 top-1/2 h-5 w-[3px] -translate-y-1/2 rounded-r-full bg-indigo-400 shadow-[0_0_8px_rgba(129,140,248,0.6)]" />
              )}

              <Icon
                className={cn(
                  "h-[18px] w-[18px] shrink-0 transition-colors",
                  isActive ? "text-indigo-400" : "text-slate-500 group-hover:text-slate-300"
                )}
              />

              <span
                className={cn(
                  "whitespace-nowrap transition-opacity duration-200",
                  expanded ? "opacity-100" : "opacity-0"
                )}
              >
                {item.label}
              </span>
            </Link>
          );
        })}
      </nav>

      {/* Status indicator */}
      <div className="border-t border-white/[0.06] px-4 py-3">
        <div className="flex items-center gap-2.5">
          <span className="relative flex h-2 w-2 shrink-0">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
          </span>
          <span
            className={cn(
              "whitespace-nowrap text-xs text-slate-500 transition-opacity duration-200",
              expanded ? "opacity-100" : "opacity-0"
            )}
          >
            Platform Online
          </span>
        </div>
      </div>
    </aside>
  );
}
