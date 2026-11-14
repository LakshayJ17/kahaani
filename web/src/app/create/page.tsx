import type { Metadata } from "next";
import { SiteFooter } from "@/components/layout/SiteFooter";
import { SiteHeader } from "@/components/layout/SiteHeader";
import Studio from "@/components/Studio";

export const metadata: Metadata = { title: "Make a book" };

export default function CreatePage() {
  return (
    <>
      <SiteHeader />
      <main className="page-x mx-auto w-full max-w-7xl pb-24">
        <Studio />
      </main>
      <SiteFooter />
    </>
  );
}
