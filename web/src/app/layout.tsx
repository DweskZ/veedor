import type { Metadata, Viewport } from "next";
import { headers } from "next/headers";
import localFont from "next/font/local";
import { Header, MockBanner } from "@/components/SiteChrome";
import { ScrollReveal } from "@/components/ScrollReveal";
import "./globals.css";
import "./features.css";
import "./data.css";
import "./refine.css";
import { ALLOW_INDEXING } from "@/lib/site";

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
  // Nothing is indexed until the owner opts in (see lib/site.ts).
  robots: ALLOW_INDEXING ? undefined : { index: false, follow: false },
};

export const viewport: Viewport = { themeColor: "#E3EEFF" };

export default async function RootLayout({ children }: LayoutProps<"/">) {
  // The per-request CSP nonce set by src/proxy.ts. Reading it makes every page render per request, which a nonce requires.
  const nonce = (await headers()).get("x-nonce") ?? undefined;
  return (
    <html lang="es-EC" className={`${jakarta.variable} h-full antialiased`} data-scroll-behavior="smooth" suppressHydrationWarning>
      <head>
        <script nonce={nonce} dangerouslySetInnerHTML={{ __html: "document.documentElement.classList.add('js')" }} />
      </head>
      <body className="flex min-h-full flex-col">
        <a href="#contenido" className="skip">
          Saltar al contenido
        </a>
        <MockBanner />
        <Header />
        {/* Each page renders its own <main> and the footer (see PageFrame). */}
        {children}
        <ScrollReveal />
      </body>
    </html>
  );
}
