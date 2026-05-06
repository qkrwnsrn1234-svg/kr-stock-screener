import type { HotSectorItem } from "@/types/api";

interface Props {
  items: HotSectorItem[];
}

/**
 * 섹터 상대강도 기반 간이 히트맵(타일)
 */
export function SectorHeatmap({ items }: Props) {
  if (!items.length) {
    return <p className="muted">표시할 섹터가 없습니다.</p>;
  }

  const maxS = Math.max(...items.map((i) => i.strength_score), 1);

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))",
        gap: "0.65rem",
      }}
    >
      {items.map((item) => {
        const intensity = item.strength_score / maxS;
        const bg = `color-mix(in srgb, var(--color-buy) ${20 + intensity * 55}%, var(--color-bg-surface))`;
        return (
          <div
            key={item.sector_name + item.representative_ticker}
            style={{
              background: bg,
              border: "1px solid var(--color-border)",
              borderRadius: "var(--radius-card)",
              padding: "0.65rem 0.75rem",
              minHeight: 88,
            }}
          >
            <div style={{ fontWeight: 700, fontSize: "0.9rem", marginBottom: 4 }}>
              {item.sector_name}
            </div>
            <div className="muted" style={{ fontSize: "0.78rem", lineHeight: 1.35 }}>
              강도 {item.strength_score.toFixed(0)}
              {item.relative_outperformance_60d != null
                ? ` · 60일 초과수익 ${(item.relative_outperformance_60d * 100).toFixed(1)}%p`
                : null}
            </div>
            {item.etf_flow_summary ? (
              <div className="muted" style={{ fontSize: "0.72rem", marginTop: 6 }}>
                {item.etf_flow_summary}
              </div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}
