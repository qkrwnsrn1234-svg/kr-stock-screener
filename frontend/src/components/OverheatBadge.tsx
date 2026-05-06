import type { OverheatAlert } from "@/types/api";

interface Props {
  alert?: OverheatAlert | null;
  /** 스크리닝 레거시 플래그 */
  flag?: boolean;
}

/** 과열 등급별 스타일 — index.css 디자인 토큰과 동기화 */
const levelTone: Record<string, { bg: string; color: string; border: string }> = {
  정상: {
    bg: "var(--color-overheat-ok-bg)",
    color: "var(--color-overheat-ok)",
    border: "var(--color-overheat-ok-border)",
  },
  주의: {
    bg: "var(--color-overheat-caution-bg)",
    color: "var(--color-overheat-caution)",
    border: "var(--color-overheat-caution-border)",
  },
  경고: {
    bg: "var(--color-overheat-warn-bg)",
    color: "var(--color-overheat-warn)",
    border: "var(--color-overheat-warn-border)",
  },
  위험: {
    bg: "var(--color-overheat-danger-bg)",
    color: "var(--color-overheat-danger)",
    border: "var(--color-overheat-danger-border)",
  },
};

/**
 * 과열 알럿 등급 배지
 */
export function OverheatBadge({ alert, flag }: Props) {
  const level = alert?.level ?? (flag ? "주의" : "정상");
  const tone = levelTone[level] ?? levelTone["정상"];
  const heat = alert?.heat_score;

  return (
    <div
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "0.5rem",
        padding: "0.35rem 0.75rem",
        borderRadius: "var(--radius-pill)",
        background: tone.bg,
        color: tone.color,
        border: `1px solid ${tone.border}`,
        fontWeight: 600,
        fontSize: "0.85rem",
      }}
    >
      과열: {level}
      {heat !== undefined && heat > 0 ? ` · 강도 ${heat.toFixed(0)}` : null}
    </div>
  );
}
