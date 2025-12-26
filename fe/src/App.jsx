// App.jsx
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import LoginPage from "./pages/LoginPage";
import RegisterPage from "./pages/RegisterPage";
import CameraSection from "./components/CameraSection";

function RequireAuth({ children }) {
  const token = localStorage.getItem("authToken");
  if (!token) {
    return <Navigate to="/login" replace />;
  }
  return children;
}

export default function App() {
  return (
    <BrowserRouter
      future={{
        v7_startTransition: true,
        v7_relativeSplatPath: true,
      }}
    >
      <Routes>
        {/* default redirect ke /camera */}
        <Route path="/" element={<Navigate to="/camera" replace />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route
          path="/camera"
          element={
            <RequireAuth>
              <CameraSection />
            </RequireAuth>
          }
        />
      </Routes>
    </BrowserRouter>
  );
}
