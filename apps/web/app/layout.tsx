import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: "RansomWatch | Threat intelligence",
  description: "Sourced cyber threat monitoring for Thailand.",
  manifest: "/manifest.webmanifest",
};
export default function Layout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
