/** Presentation bands for the 0-100 score. They are display bins, not statistical thresholds. */
export interface RiskLevel {
  index: 0 | 1 | 2 | 3 | 4;
  label: string;
  min: number;
  max: number;
}

export const RISK_LEVELS: readonly RiskLevel[] = [
  { index: 0, label: "Sin señales", min: 0, max: 0 },
  { index: 1, label: "Bajo", min: 1, max: 24 },
  { index: 2, label: "Moderado", min: 25, max: 49 },
  { index: 3, label: "Elevado", min: 50, max: 74 },
  { index: 4, label: "Alto", min: 75, max: 100 },
];

export function riskLevel(score: number): RiskLevel {
  if (score <= 0) return RISK_LEVELS[0];
  if (score < 25) return RISK_LEVELS[1];
  if (score < 50) return RISK_LEVELS[2];
  if (score < 75) return RISK_LEVELS[3];
  return RISK_LEVELS[4];
}
