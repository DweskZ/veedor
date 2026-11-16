import type { ReviewStatus } from "./types";

export const REVIEW_LABELS: Record<ReviewStatus, string> = {
  pending: "Pendiente de revisión",
  confirmed_signal: "Señal confirmada por revisión humana",
  dismissed: "Descartada tras revisión",
};
