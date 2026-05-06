import { useEffect, useState } from "react";
import { getHotSectors } from "@/api/client";
import { SectorHeatmap } from "@/components/SectorHeatmap";
import type { HotSectorsReport } from "@/types/api";

/**
 * 주도 섹터 조회(표본 수·상위 개수 조절)
 */
export function HotSectorsPage() {
  const [pool, setPool] = useState(12);
  const [top, setTop] = useState(5);
  const [data, setData] = useState<HotSectorsReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setErr(null);
    try {
      const r = await getHotSectors(pool, top);
      setData(r);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "로드 실패");
      setData(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 초기·pool/top 버튼으로만 갱신
  }, []);

  return (
    <>
      <h1 style={{ marginTop: 0 }}>주도 섹터</h1>
      <div className="card">
        <div className="row" style={{ alignItems: "center" }}>
          <label className="muted">
            표본 업종 수
            <input
              type="number"
              className="input"
              style={{ marginLeft: 8, width: 80 }}
              min={4}
              max={30}
              value={pool}
              onChange={(e) => setPool(parseInt(e.target.value, 10) || 12)}
            />
          </label>
          <label className="muted">
            상위 개수
            <input
              type="number"
              className="input"
              style={{ marginLeft: 8, width: 80 }}
              min={1}
              max={15}
              value={top}
              onChange={(e) => setTop(parseInt(e.target.value, 10) || 5)}
            />
          </label>
          <button type="button" className="btn btn-secondary" disabled={loading} onClick={() => void load()}>
            {loading ? "로드 중…" : "다시 조회"}
          </button>
        </div>
        {err ? <p className="error">{err}</p> : null}
        {data ? (
          <p className="muted" style={{ marginBottom: 0 }}>
            산출 시각: {data.timestamp}
          </p>
        ) : null}
      </div>
      {data ? <SectorHeatmap items={data.items} /> : null}
      {data?.items.some((i) => i.earnings_revision_note) ? (
        <div className="card muted" style={{ fontSize: "0.85rem" }}>
          일부 항목에 어닝 리비전 연동 안내가 포함될 수 있습니다.
        </div>
      ) : null}
    </>
  );
}
