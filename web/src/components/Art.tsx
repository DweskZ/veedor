/** Isometric line-art models (Codex, see docs/BRAND.md). Same-origin WebP at two widths, explicit size, lazy by default. */
export type ArtName = "hero" | "datos" | "investigacion" | "verificacion" | "vacio";

export const ART_ALT: Record<ArtName, string> = {
  hero: "Dibujo isométrico de una plaza pública con un edificio municipal, una obra con grúa y un camión de reparto: lo que compra el Estado.",
  datos: "Dibujo isométrico de un archivo con estantes de carpetas y cajas: los datos abiertos de contratación.",
  investigacion: "Dibujo isométrico de una oficina con una mesa central y varios puestos de trabajo, sin personas: los especialistas que consultan las fuentes.",
  verificacion: "Dibujo isométrico de una oficina de registro público con un mostrador, un sello y filas de archivadores: la fuente oficial.",
  vacio: "Dibujo isométrico de un terreno vacío con una cerca y un letrero en blanco.",
};

export function Art({
  name,
  alt,
  sizes = "(min-width: 900px) 40vw, 90vw",
  priority = false,
  className,
}: {
  name: ArtName;
  alt?: string;
  sizes?: string;
  priority?: boolean;
  className?: string;
}) {
  return (
    // eslint-disable-next-line @next/next/no-img-element -- static, pre-optimised same-origin WebP with explicit size
    <img
      src={`/art/${name}-960.webp`}
      srcSet={`/art/${name}-480.webp 480w, /art/${name}-960.webp 960w`}
      sizes={sizes}
      width={960}
      height={669}
      alt={alt ?? ART_ALT[name]}
      loading={priority ? "eager" : "lazy"}
      fetchPriority={priority ? "high" : undefined}
      decoding="async"
      className={className}
    />
  );
}
