import type { Metadata } from "next";
import { Sidebar } from "@/components/sidebar";
import { Header } from "@/components/header";
import "./globals.css";

export const metadata: Metadata = {
  title: "Observability KPI — Enterprise Reporting Dashboard",
  description: "Leadership-grade observability KPI reporting across Mimir, Loki, Tempo, Pyroscope, and Grafana",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className="bg-grid min-h-screen antialiased">
        <Sidebar />
        <div className="pl-[72px]">
          <Header />
          <main className="p-6">{children}</main>
        </div>
      </body>
    </html>
  );
}
