import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";

import { PortalShell } from "@/components/portal-shell";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: {
    default: "Cadence · Clinical workspace",
    template: "%s · Cadence",
  },
  description:
    "Clinician-guided speech practice assignments, review, and safety operations.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable}`}
    >
      <body>
        <PortalShell>{children}</PortalShell>
      </body>
    </html>
  );
}
