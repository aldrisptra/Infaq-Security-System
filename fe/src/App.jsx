import React from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import PrivateRoute from "./auth/PrivateRoute";
import LoginPage from "./pages/LoginPage";
import Dashboard from "./pages/Dashboard";

export default function App() {
  return (
    <Routes>
      {/* Public */}
      <Route path="/login" element={<LoginPage />} />

      {/* Protected */}
      <Route element={<PrivateRoute />}>
        <Route path="/app" element={<Dashboard />} />
      </Route>

      {/* Default redirect */}
      <Route path="*" element={<Navigate to="/app" replace />} />
    </Routes>
  );
}
