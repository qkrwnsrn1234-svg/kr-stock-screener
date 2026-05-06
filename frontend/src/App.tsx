import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "@/components/Layout";
import { AgentStatsPage } from "@/pages/AgentStatsPage";
import { AnalyzePage } from "@/pages/AnalyzePage";
import { DashboardPage } from "@/pages/DashboardPage";
import { HotSectorsPage } from "@/pages/HotSectorsPage";
import { PortfolioPage } from "@/pages/PortfolioPage";
import { ScreenPage } from "@/pages/ScreenPage";

/**
 * 앱 라우팅
 */
function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<DashboardPage />} />
        <Route path="analyze" element={<AnalyzePage />} />
        <Route path="screen" element={<ScreenPage />} />
        <Route path="sectors" element={<HotSectorsPage />} />
        <Route path="agents" element={<AgentStatsPage />} />
        <Route path="portfolio" element={<PortfolioPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}

export default App;
