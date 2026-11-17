import type { Metadata } from "next";
import { PageFrame } from "@/components/PageFrame";
import { getRegions } from "@/lib/api";
import { RegionExplorer } from "@/components/RegionExplorer";
import { Term } from "@/components/Term";
import { ErrorState, PageHeader } from "@/components/ui";

const TITLE = "Señales por provincia";
const DESCRIPTION =
  "Mapa del Ecuador con el porcentaje de procesos competitivos que tienen señales, por provincia de la entidad que compra. Más señales no significa más problemas ni es un ranking.";
export const metadata: Metadata = {
  title: "Mapa de señales por provincia",
  description: DESCRIPTION,
  openGraph: { title: `${TITLE} · Veedor`, description: DESCRIPTION },
};

export default function MapPage() {
  return (
    <PageFrame>
      <PageHeader
        eyebrow="Mapa"
        title={
          <>
            Señales <em>por provincia.</em>
          </>
        }
        lead={
          <>
            Por provincia, qué parte de los <Term t="proceso competitivo">procesos competitivos</Term> tiene alguna <Term t="señal de riesgo">señal</Term>. Sirve para ubicar
            qué revisar, no para comparar ni juzgar a una provincia.
          </>
        }
      />
      <div className="wrap">
        <MapBody />
        <div className="page-end" />
      </div>
    </PageFrame>
  );
}

async function MapBody() {
  const r = await getRegions().then(
    (v) => ({ ok: true as const, v }),
    (e: unknown) => ({ ok: false as const, e }),
  );
  if (!r.ok || r.v.items.length === 0)
    return (
      <ErrorState
        title="El mapa no está disponible"
        detail="Todavía no podemos mostrar los datos por provincia. Los demás datos del sitio siguen disponibles."
      />
    );
  return <RegionExplorer rows={r.v.items} national={r.v.national} notes={r.v.notes} />;
}
