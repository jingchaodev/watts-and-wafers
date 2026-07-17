import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Watts & Wafers",
  description: "AI compute demand, on one tape",
};

export const viewport = {
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
