import type { Metadata } from "next";
import { Fraunces, Hind } from "next/font/google";
import { AuthProvider } from "@/lib/auth";
import "./globals.css";

const fraunces = Fraunces({
  variable: "--font-fraunces",
  subsets: ["latin"],
  axes: ["opsz", "SOFT"],
});

// Hind (Indian Type Foundry) covers both Devanagari and Latin.
const hind = Hind({
  variable: "--font-hind",
  subsets: ["latin", "devanagari"],
  weight: ["400", "500", "600"],
});

export const metadata: Metadata = {
  title: "Kahaani: a bedtime story starring your child",
  description:
    "Describe your child and get an illustrated, narrated storybook in Hindi or English, as a PDF and a read-along video. Free.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${fraunces.variable} ${hind.variable}`}>
      <body className="min-h-screen">
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
