import { Navigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import type { ReactNode } from "react";

export default function ProtectedRoute({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();

  if (loading) return <div className="container" style={{ padding: "3rem 0" }}>Loading…</div>;
  if (!user) return <Navigate to="/login" replace />;
  return <>{children}</>;
}
