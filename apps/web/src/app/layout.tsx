import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "umapro",
  description: "期待値ベースの競馬分析・意思決定支援",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ja">
      <body>{children}</body>
    </html>
  );
}
