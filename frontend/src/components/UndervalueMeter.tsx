import type { UndervalueBreakdown } from "@/types/api";

interface Props {
  score: number;
  breakdown?: UndervalueBreakdown | null;
}

/**
 * 언더밸류 점수(0~100) 게이지 + 구성 요소 바
 */
export function UndervalueMeter({ score, breakdown }: Props) {
  const clamped = Math.min(100, Math.max(0, score));

  return (
    <div>
      <div
        style={{
          position: "relative",
          height: 28,
          background: "var(--color-bg-elevated)",
          borderRadius: "var(--radius-card)",
          overflow: "hidden",
          border: "1px solid var(--color-border)",
        }}
      >
        <div
          style={{
            width: `${clamped}%`,
            height: "100%",
            background:
              clamped >= 70
                ? "linear-gradient(90deg, color-mix(in srgb, var(--color-buy) 75%, black), var(--color-buy))"
                : clamped >= 40
                  ? "linear-gradient(90deg, color-mix(in srgb, var(--color-hold) 55%, black), var(--color-hold))"
                  : "linear-gradient(90deg, var(--color-text-secondary), var(--color-text-nav))",
            transition: "width 0.4s ease",
          }}
        />
        <span
          style={{
            position: "absolute",
            inset: 0,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontWeight: 700,
            fontSize: "0.9rem",
            textShadow: "0 1px 2px #000",
          }}
        >
          {clamped.toFixed(1)} / 100
        </span>
      </div>
      {breakdown ? (
        <div style={{ marginTop: "0.75rem" }}>
          <p className="muted" style={{ margin: "0 0 0.5rem" }}>
            구성: PER {breakdown.per_score.toFixed(0)} · PBR {breakdown.pbr_score.toFixed(0)} · FCF{" "}
            {breakdown.fcf_yield_score.toFixed(0)} · F-Score {breakdown.fscore_score.toFixed(0)} → 종합{" "}
            {breakdown.combined.toFixed(1)}
          </p>
          {breakdown.sector_label ? (
            <p className="muted" style={{ margin: 0 }}>
              업종: {breakdown.sector_label} (동종 {breakdown.peer_count}곳)
            </p>
          ) : null}
          {breakdown.fcf_note ? (
            <p className="muted" style={{ margin: "0.35rem 0 0" }}>
              {breakdown.fcf_note}
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
