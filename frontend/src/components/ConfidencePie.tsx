import { Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import type { CEOReport } from "@/types/api";

interface Props {
  report: CEOReport;
}

const COLORS = ["#3fb950", "#d29922", "#f85149"];

/**
 * CEO 매수/중립/매도 비중 파이 차트
 */
export function ConfidencePie({ report }: Props) {
  const data = [
    { name: "매수", value: report.buy_pct },
    { name: "중립", value: report.neutral_pct },
    { name: "매도", value: report.sell_pct },
  ].filter((d) => d.value > 0);

  if (data.length === 0) {
    return <p className="muted">집계할 비중 데이터가 없습니다.</p>;
  }

  return (
    <div style={{ width: "100%", height: 260 }}>
      <ResponsiveContainer>
        <PieChart>
          <Pie
            data={data}
            dataKey="value"
            nameKey="name"
            cx="50%"
            cy="50%"
            outerRadius={88}
            label={({ name, value }) => `${name} ${Number(value).toFixed(0)}%`}
          >
            {data.map((entry, i) => (
              <Cell key={entry.name} fill={COLORS[i % COLORS.length]} />
            ))}
          </Pie>
          <Tooltip formatter={(v: number) => `${v.toFixed(1)}%`} />
          <Legend />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}
