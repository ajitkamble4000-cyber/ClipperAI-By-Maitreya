import type { Metadata, Viewport } from "next";
import { Toaster } from "sonner";
import "./globals.css";
import "./caption-fonts.css";

export const metadata: Metadata = {
  title: "Shorts Studio",
  description: "Make YouTube Shorts: clip long videos and create AI stories.",
};

export const viewport: Viewport = { themeColor: "#14121c", width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body>
        {children}
        <Toaster theme="dark" position="top-center" richColors />
      </body>
    </html>
  );
}
