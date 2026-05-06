import { useEffect, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import { useNavigate } from "react-router-dom";
import { searchSymbols } from "@/api/client";
import type { SearchResultItem } from "@/types/api";

const RECENT_SEARCH_KEY = "kr-stock-screener:recent-searches";
const MAX_RECENT_SEARCHES = 10;
const SEARCH_DEBOUNCE_MS = 300;

function loadRecentSearches(): SearchResultItem[] {
  /** 최근 검색 기록을 LocalStorage에서 안전하게 읽습니다. */
  try {
    const raw = window.localStorage.getItem(RECENT_SEARCH_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as SearchResultItem[];
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((item) => item.ticker && item.name).slice(0, MAX_RECENT_SEARCHES);
  } catch {
    return [];
  }
}

function saveRecentSearches(items: SearchResultItem[]): void {
  /** 최근 검색 기록을 최대 10개까지만 저장합니다. */
  try {
    window.localStorage.setItem(RECENT_SEARCH_KEY, JSON.stringify(items.slice(0, MAX_RECENT_SEARCHES)));
  } catch {
    /* LocalStorage 접근이 막힌 환경에서는 기록만 생략합니다. */
  }
}

/**
 * 전역 종목 검색 자동완성 컴포넌트
 */
export function GlobalSearch() {
  const navigate = useNavigate();
  const boxRef = useRef<HTMLDivElement | null>(null);
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<SearchResultItem[]>([]);
  const [recent, setRecent] = useState<SearchResultItem[]>(() => loadRecentSearches());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);

  const trimmed = query.trim();
  const visibleItems = trimmed ? items : recent;
  const showRecentTitle = !trimmed && recent.length > 0;

  useEffect(() => {
    const onPointerDown = (event: PointerEvent) => {
      if (boxRef.current && !boxRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    window.addEventListener("pointerdown", onPointerDown);
    return () => window.removeEventListener("pointerdown", onPointerDown);
  }, []);

  useEffect(() => {
    if (!trimmed) {
      setItems([]);
      setError(null);
      setLoading(false);
      return;
    }

    let alive = true;
    setLoading(true);
    setError(null);

    const timer = window.setTimeout(() => {
      void searchSymbols(trimmed)
        .then((res) => {
          if (!alive) return;
          setItems(res.items);
        })
        .catch((err: unknown) => {
          if (!alive) return;
          setError(err instanceof Error ? err.message : "검색 실패");
          setItems([]);
        })
        .finally(() => {
          if (alive) setLoading(false);
        });
    }, SEARCH_DEBOUNCE_MS);

    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
  }, [trimmed]);

  const selectItem = (item: SearchResultItem) => {
    const nextRecent = [item, ...recent.filter((r) => r.ticker !== item.ticker)].slice(0, MAX_RECENT_SEARCHES);
    setRecent(nextRecent);
    saveRecentSearches(nextRecent);
    setQuery(`${item.name} ${item.ticker}`);
    setOpen(false);
    navigate(`/analyze/${item.ticker}`);
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Escape") {
      setOpen(false);
      return;
    }
    if (event.key === "Enter" && visibleItems.length > 0) {
      event.preventDefault();
      selectItem(visibleItems[0]);
    }
  };

  return (
    <div ref={boxRef} className="global-search">
      <label htmlFor="global-stock-search" className="muted global-search-label">
        종목 검색
      </label>
      <input
        id="global-stock-search"
        type="search"
        className="global-search-input"
        value={query}
        placeholder="삼성전자 또는 005930"
        autoComplete="off"
        aria-label="종목 검색"
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={handleKeyDown}
      />
      {open ? (
        <div className="global-search-panel" role="listbox" aria-label="종목 검색 결과">
          {showRecentTitle ? <div className="global-search-section-title">최근 검색</div> : null}
          {loading ? <div className="global-search-empty">검색 중...</div> : null}
          {error ? <div className="global-search-empty error">{error}</div> : null}
          {!loading && !error && visibleItems.length === 0 ? (
            <div className="global-search-empty">{trimmed ? "검색 결과가 없습니다." : "최근 검색이 없습니다."}</div>
          ) : null}
          {!loading && !error
            ? visibleItems.map((item) => (
                <button
                  key={item.ticker}
                  type="button"
                  className="global-search-option"
                  role="option"
                  aria-selected="false"
                  onClick={() => selectItem(item)}
                >
                  <span>
                    <strong>{item.name}</strong>
                    <span className="muted"> {item.ticker}</span>
                  </span>
                  <span className="global-search-meta">
                    {[item.market, item.sector].filter(Boolean).join(" · ")}
                  </span>
                </button>
              ))
            : null}
        </div>
      ) : null}
    </div>
  );
}
