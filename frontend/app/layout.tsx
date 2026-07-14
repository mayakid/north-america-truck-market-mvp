import type { Metadata } from "next";
import { headers } from "next/headers";
import "./globals.css";

const title = "DrayEasy Market Radar｜加拿大卡车市场机会推荐 MVP";
const description =
  "产品经理作品集 MVP：基于真实 BTS 数据，为美国出口加拿大的卡车运输生成省级 Top 5、历史趋势与可解释依据。";

export async function generateMetadata(): Promise<Metadata> {
  const requestHeaders = await headers();
  const host =
    requestHeaders.get("x-forwarded-host") ?? requestHeaders.get("host") ?? "localhost:3000";
  const protocol =
    requestHeaders.get("x-forwarded-proto") ?? (host.startsWith("localhost") ? "http" : "https");
  const origin = `${protocol}://${host}`;
  const imageUrl = `${origin}/og-drayeasy.png`;

  return {
    metadataBase: new URL(origin),
    title,
    description,
    openGraph: {
      title,
      description,
      type: "website",
      locale: "zh_CN",
      images: [{ url: imageUrl, width: 1731, height: 909, alt: "DrayEasy Market Radar 产品经理作品集 MVP" }],
    },
    twitter: {
      card: "summary_large_image",
      title,
      description,
      images: [imageUrl],
    },
  };
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
