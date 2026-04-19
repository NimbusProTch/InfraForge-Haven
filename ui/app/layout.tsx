import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: "iyziops",
  description: "Self-service DevOps platform — VNG Haven 15/15 compliant",
  icons: {
    icon: "/logo.svg",
    apple: "/logo.svg",
  },
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

