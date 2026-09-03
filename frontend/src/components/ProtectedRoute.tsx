import { Navigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import { Spinner } from "./ui";

export default function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <Spinner text="正在验证身份…" />;
  if (!user) return <Navigate to="/login" replace />;
  return <>{children}</>;
}
