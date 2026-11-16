import type { Metadata, Viewport } from "next";
import { IBM_Plex_Mono, Schibsted_Grotesk } from "next/font/google";
import { Footer, Header, MockBanner } from "@/components/SiteChrome";
import "./globals.css";

const grotesk = Schibsted_Grotesk({ variable: "--font-grotesk", subsets: ["latin"], display: "swap" });
const plexMono = IBM_Plex_Mono({ variable: "--font-plex-mono", subsets: ["latin"], weight: ["400", "500"], display: "swap" });

export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000"),
  title: { default: "Veedor · Radar abierto de riesgo en contratación pública", template: "%s · Veedor" },
  description:
    "Indicadores de riesgo con su evidencia sobre la contratación pública del Ecuador, calculados con datos abiertos. No constituyen acusaciones.",
  openGraph: { siteName: "Veedor", locale: "es_EC", type: "website" },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f4f0e6" },
    { media: "(prefers-color-scheme: dark)", color: "#161412" },
  ],
};

const THEME_SCRIPT = `try{var t=localStorage.getItem("veedor-theme");if(t!=="light"&&t!=="dark"){t=matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light"}document.documentElement.dataset.theme=t}catch(e){}`;

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="es-EC" className={`${grotesk.variable} ${plexMono.variable} h-full antialiased`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body className="flex min-h-full flex-col">
        <a
          href="#contenido"
          className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-accent focus:px-3 focus:py-2 focus:text-accent-ink"
        >
          Saltar al contenido
        </a>
        <MockBanner />
        <Header />
        <main id="contenido" className="mx-auto w-full max-w-6xl flex-1 px-4 pb-8 sm:px-6">
          {children}
        </main>
        <Footer />
      </body>
    </html>
  );
}
