export function formatPercent(value: number, withSign = false): string {
  const pct = value * 100;
  const sign = withSign && pct > 0 ? "+" : "";
  return `${sign}${pct.toFixed(2)}%`;
}

export function formatSignedPercent(value: number): string {
  return formatPercent(value, true);
}

export function formatPValue(value: number): string {
  return value.toFixed(3);
}

export function formatIC(value: number): string {
  return value.toFixed(4);
}

export function formatSharpe(value: number): string {
  return value.toFixed(2);
}

export function formatScore(value: number): string {
  return value.toFixed(2);
}

export function formatDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}
