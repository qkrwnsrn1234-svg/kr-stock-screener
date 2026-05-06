import { NavLink, Outlet } from "react-router-dom";
import "../App.css";

const links = [
  { to: "/", label: "대시보드" },
  { to: "/analyze", label: "종목 분석" },
  { to: "/screen", label: "스크리닝" },
  { to: "/sectors", label: "주도 섹터" },
  { to: "/agents", label: "에이전트 성적표" },
  { to: "/portfolio", label: "포트폴리오" },
];

/**
 * 상단 내비 + 자식 라우트 영역
 */
export function Layout() {
  return (
    <div className="app-shell">
      <nav className="app-nav" aria-label="주 메뉴">
        <h1>KR Stock Screener</h1>
        <ul>
          {links.map(({ to, label }) => (
            <li key={to}>
              <NavLink to={to} end={to === "/"}>
                {label}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
      <div className="app-content">
        <header className="global-header">
          <label className="global-search">
            <span className="muted" style={{ display: "block", marginBottom: "0.35rem", fontSize: "0.8rem" }}>
              종목 검색
            </span>
            <input
              type="search"
              className="global-search-input"
              placeholder="종목명 또는 6자리 코드 · 자동완성 연동 예정"
              autoComplete="off"
              aria-label="종목 검색"
            />
          </label>
        </header>
        <main className="app-main">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
