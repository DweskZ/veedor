import type { Metadata, Viewport } from "next";
import localFont from "next/font/local";
import { Suspense } from "react";
import { Footer, Header, MockBanner } from "@/components/SiteChrome";
import { ScrollReveal } from "@/components/ScrollReveal";
import "./globals.css";
import "./features.css";
import "./data.css";

// Plus Jakarta Sans, the Ruray typeface, self-hosted (no request to Google).
const jakarta = localFont({
  variable: "--font-jakarta",
  display: "swap",
  src: [
    { path: "../../public/fonts/plus-jakarta-sans-latin-500.woff2", weight: "500", style: "normal" },
    { path: "../../public/fonts/plus-jakarta-sans-latin-600.woff2", weight: "600", style: "normal" },
    { path: "../../public/fonts/plus-jakarta-sans-latin-700.woff2", weight: "700", style: "normal" },
    { path: "../../public/fonts/plus-jakarta-sans-latin-800.woff2", weight: "800", style: "normal" },
  ],
});

export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000"),
  title: { default: "Veedor · Mira cómo compra el Estado", template: "%s · Veedor" },
  description:
    "Veedor lee los datos abiertos de la contratación pública del Ecuador y marca los procesos con señales atípicas, con su evidencia. Una señal no es una acusación. Un producto de Ruray.",
  openGraph: { siteName: "Veedor", locale: "es_EC", type: "website" },
};

export const viewport: Viewport = { themeColor: "#E3EEFF" };

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="es-EC" className={`${jakarta.variable} h-full antialiased`} data-scroll-behavior="smooth" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: "document.documentElement.classList.add('js')" }} />
        {/* Without JavaScript React cannot move streamed content out of its hidden holding boxes: show them, and drop the loading skeletons. Inside the base layer because Tailwind's important [hidden] rule lives there and layered important rules beat unlayered ones. */}
        <noscript>
          <style>{'@layer base{div[hidden][id^="S:"]{display:block!important}.skeleton,[aria-label="Cargando"]{display:none!important}}'}</style>
        </noscript>
      </head>
      <body className="flex min-h-full flex-col">
        <a href="#contenido" className="skip">
          Saltar al contenido
        </a>
        <MockBanner />
        <Header />
        <main id="contenido" className="flex-1">
          {children}
        </main>
        <Footer />
        <Suspense fallback={null}>
          <ScrollReveal />
        </Suspense>
      </body>
    </html>
  );
}
