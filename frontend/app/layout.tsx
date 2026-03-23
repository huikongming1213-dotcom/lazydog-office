import type { Metadata } from "next";
import "../styles/pixel.css";
import "./globals.css";

export const metadata: Metadata = {
  title: "Lazydog.ai Virtual Office",
  description: "Multi-agent social media management system",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        {/* CRT scanline overlay */}
        <div className="crt-overlay" aria-hidden="true" />
        {children}
      </body>
    </html>
  );
}
