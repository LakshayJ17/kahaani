import type { Metadata, Viewport } from "next";
import { Baloo_2, Hind } from "next/font/google";
import { MotionProvider } from "@/components/ui/MotionProvider";
import { AuthProvider } from "@/lib/auth";
import "./globals.css";

// Baloo 2 and Hind are Indian Type Foundry faces; both cover Devanagari and Latin.
// Baloo 2 is also the heading font inside the printed books.
const baloo = Baloo_2({
  variable: "--font-baloo",
  weight: ["500", "600", "700"],
  subsets: ["latin", "devanagari"],
  display: "swap",
});

const hind = Hind({
  variable: "--font-hind",
  weight: ["400", "500", "600"],
  subsets: ["latin", "devanagari"],
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: "Kahaani · A bedtime story starring your child",
    template: "%s · Kahaani",
  },
  description:
    "Describe your child and get an illustrated, narrated storybook in Hindi or English, as a PDF and a read-along video.",
};

export const viewport: Viewport = {
  themeColor: "#f3e9d6",
  colorScheme: "light",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${baloo.variable} ${hind.variable} antialiased`}
    >
      <body className="min-h-dvh bg-desk text-ink">
        <MotionProvider>
          <AuthProvider>{children}</AuthProvider>
        </MotionProvider>
      </body>
    </html>
  );
}
