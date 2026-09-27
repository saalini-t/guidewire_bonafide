import { Navigate, Route, Routes } from "react-router-dom";
import ClaimsPage from "./pages/ClaimsPage.jsx";
import ClaimDetailPage from "./pages/ClaimDetailPage.jsx";

export default function App() {
  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="app-header__brand">
          <span className="app-header__mark">BF</span>
          <div>
            <div className="app-header__title">Bona Fide</div>
            <div className="app-header__subtitle">Evidence Preservation Intelligence</div>
          </div>
        </div>
      </header>
      <main className="app-main">
        <Routes>
          <Route path="/" element={<Navigate to="/claims" replace />} />
          <Route path="/claims" element={<ClaimsPage />} />
          <Route path="/claims/:claimId" element={<ClaimDetailPage />} />
        </Routes>
      </main>
    </div>
  );
}
