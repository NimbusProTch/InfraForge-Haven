import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: "Haven Platform",
  description: "Haven-Compliant Self-Service DevOps Platform",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="bg-gray-50 dark:bg-[#0a0a0a] text-gray-900 dark:text-zinc-100 antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
