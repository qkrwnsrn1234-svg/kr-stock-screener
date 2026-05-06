import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "@/components/Layout";
import { AgentStatsPage } from "@/pages/AgentStatsPage";
import { AnalyzePage } from "@/pages/AnalyzePage";
import { BacktestPage } from "@/pages/BacktestPage";
import { DashboardPage } from "@/pages/DashboardPage";
import { HotSectorsPage } from "@/pages/HotSectorsPage";
import { PortfolioPage } from "@/pages/PortfolioPage";
import { ScreenPage } from "@/pages/ScreenPage";
import { WatchlistPage } from "@/pages/WatchlistPage";

/**
 * 앱 라우팅
 */
function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<DashboardPage />} />
        <Route path="analyze" element={<AnalyzePage />} />
        <Route path="analyze/:ticker" element={<AnalyzePage />} />
        <Route path="screen" element={<ScreenPage />} />
        <Route path="watchlist" element={<WatchlistPage />} />
        <Route path="sectors" element={<HotSectorsPage />} />
        <Route path="agents" element={<AgentStatsPage />} />
        <Route path="backtest" element={<BacktestPage />} />
        <Route path="portfolio" element={<PortfolioPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}

export default App;
