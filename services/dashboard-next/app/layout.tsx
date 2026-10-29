import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Hyper-Local Disaster Early Warning",
  description: "Live municipal sensor monitoring & anomaly alerts",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-slate-950 text-slate-100 min-h-screen antialiased">
        {children}
      </body>
    </html>
  );
}
