import { NavLink, Outlet } from "react-router-dom";
import { GlobalSearch } from "@/components/GlobalSearch";
import "../App.css";

const links = [
  { to: "/", label: "대시보드" },
  { to: "/analyze", label: "종목 분석" },
  { to: "/screen", label: "스크리닝" },
  { to: "/watchlist", label: "관심 종목" },
  { to: "/sectors", label: "주도 섹터" },
  { to: "/agents", label: "에이전트 성적표" },
  { to: "/backtest", label: "백테스트" },
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
          <GlobalSearch />
        </header>
        <main className="app-main">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
