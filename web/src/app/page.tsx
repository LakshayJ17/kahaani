import { SiteFooter } from "@/components/layout/SiteFooter";
import { SiteHeader } from "@/components/layout/SiteHeader";
import { BookHero } from "@/components/landing/BookHero";
import { Bookshelf } from "@/components/landing/Bookshelf";
import { HowItWorks } from "@/components/landing/HowItWorks";
import { ParentNote } from "@/components/landing/ParentNote";
import { ReadAlong } from "@/components/landing/ReadAlong";
import { WhatsInside } from "@/components/landing/WhatsInside";

export default function Home() {
  return (
    <div className="flex min-h-dvh flex-col">
      <SiteHeader />
      <main id="top">
        <BookHero />
        <HowItWorks />
        <ReadAlong />
        <Bookshelf />
        <WhatsInside />
        <ParentNote />
      </main>
      <SiteFooter />
    </div>
  );
}
