import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getHealth, getHotSectors } from "@/api/client";
import { SectorHeatmap } from "@/components/SectorHeatmap";

/**
 * 첫 화면: API 상태 + 주도 섹터 미리보기
 */
export function DashboardPage() {
  const [health, setHealth] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const h = await getHealth();
        if (!cancelled) setHealth(h.timestamp);
      } catch (e) {
        if (!cancelled) setErr(e instanceof Error ? e.message : "연결 실패");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const [hotErr, setHotErr] = useState<string | null>(null);
  const [hotLoading, setHotLoading] = useState(true);
  const [hotItems, setHotItems] = useState<Awaited<ReturnType<typeof getHotSectors>>["items"]>(
    []
  );

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setHotLoading(true);
      setHotErr(null);
      try {
        const r = await getHotSectors(12, 6);
        if (!cancelled) setHotItems(r.items);
      } catch (e) {
        if (!cancelled) setHotErr(e instanceof Error ? e.message : "섹터 로드 실패");
      } finally {
        if (!cancelled) setHotLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <>
      <h1 style={{ marginTop: 0 }}>대시보드</h1>
      <div className="card">
        <h2>백엔드 연결</h2>
        {err ? (
          <p className="error">
            {err} — uvicorn을 띄운 뒤 다시 시도하세요. (예:{" "}
            <code style={{ color: "var(--color-accent)" }}>uvicorn backend.main:app --reload</code>)
          </p>
        ) : (
          <p className="muted" style={{ margin: 0 }}>
            정상 · 마지막 health 시각: {health ?? "…"}
          </p>
        )}
      </div>
      <div className="card">
        <h2>주도 섹터 스냅샷</h2>
        <p className="muted">
          자세히는 <Link to="/sectors">주도 섹터</Link> 화면에서 조정 가능합니다.
        </p>
        {hotErr ? <p className="error">{hotErr}</p> : null}
        {hotLoading ? <p className="muted">불러오는 중…</p> : <SectorHeatmap items={hotItems} />}
      </div>
    </>
  );
}
