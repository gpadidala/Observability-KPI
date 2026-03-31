"use client";

import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

interface GlassCardProps {
  children: React.ReactNode;
  className?: string;
  glow?: "cyan" | "purple" | "green" | "red" | "none";
  animate?: boolean;
  delay?: number;
}

export function GlassCard({
  children,
  className,
  glow = "none",
  animate = true,
  delay = 0,
}: GlassCardProps) {
  const glowClass = {
    cyan: "glow-cyan",
    purple: "glow-purple",
    green: "glow-green",
    red: "glow-red",
    none: "",
  }[glow];

  const classes = cn("glass rounded-2xl p-5", glowClass, className);

  if (!animate) {
    return <div className={classes}>{children}</div>;
  }

  return (
    <motion.div
      className={classes}
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay, ease: [0.25, 0.46, 0.45, 0.94] }}
    >
      {children}
    </motion.div>
  );
}
