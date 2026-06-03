import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Cloven — adviser co-pilot",
  description:
    "Structured adviser briefs with a deterministic FCA-style compliance guardrail.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen">{children}</body>
    </html>
  );
}
