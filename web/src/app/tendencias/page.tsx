import type { Metadata } from "next";
import { PageFrame } from "@/components/PageFrame";
import { getYears } from "@/lib/api";
import { TrendCharts } from "@/components/TrendCharts";
import { Term } from "@/components/Term";
import { ErrorState, PageHeader } from "@/components/ui";

const DESCRIPTION =
  "Cómo cambió con los años la parte de subastas con un solo oferente y la forma en que el Estado compra, con las advertencias sobre los datos.";
export const metadata: Metadata = {
  title: "Tendencias por año",
  description: DESCRIPTION,
  openGraph: { title: "Tendencias por año · Veedor", description: DESCRIPTION },
};

export default function TrendsPage() {
  return (
    <PageFrame>
      <PageHeader
        eyebrow="Tendencias"
        title={
          <>
            Cómo cambió <em>con los años.</em>
          </>
        }
        lead={
          <>
            Tres gráficos para ver cómo compra el Estado año a año. Muestran cambios, no causas. Las advertencias que valen para todos están aquí abajo, una sola vez; las de un gráfico, a su lado. Un{" "}
            <Term t="oferente">oferente</Term> es quien presenta una oferta.
          </>
        }
      />
      <div className="wrap">
        <TrendsBody />
        <div className="page-end" />
      </div>
    </PageFrame>
  );
}

async function TrendsBody() {
  const r = await getYears().then(
    (v) => ({ ok: true as const, v }),
    (e: unknown) => ({ ok: false as const, e }),
  );
  if (!r.ok || r.v.items.length === 0)
    return <ErrorState title="Las tendencias no están disponibles" detail="Todavía no podemos mostrar los datos por año. Los demás datos del sitio siguen disponibles." />;
  return <TrendCharts years={r.v.items} notes={r.v.notes} />;
}
