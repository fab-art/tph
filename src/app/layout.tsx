import type { Metadata, Viewport } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: "TUUZA Quote OCR",
  description: "Local quotation NAME-column extraction",
  manifest: "/manifest.json"
};
export const viewport: Viewport = { themeColor: "#174b3a", width: "device-width", initialScale: 1 };
export default function RootLayout({children}:{children:React.ReactNode}) {
  return <html lang="en"><body>{children}</body></html>;
}
