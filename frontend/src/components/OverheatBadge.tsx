import type { OverheatAlert } from "@/types/api";

interface Props {
  alert?: OverheatAlert | null;
  /** 스크리닝 레거시 플래그 */
  flag?: boolean;
}

const levelTone: Record<string, { bg: string; color: string; border: string }> = {
  정상: { bg: "#23863622", color: "#3fb950", border: "#23863655" },
  주의: { bg: "#d2992222", color: "#e3b341", border: "#d2992255" },
  경고: { bg: "#db6d2822", color: "#ffa657ff", border: "#db6d2855" },
  위험: { bg: "#f8514922", color: "#ff7b72", border: "#f8514955" },
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
        borderRadius: 999,
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
