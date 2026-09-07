import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider } from "./contexts/AuthContext";
import { ToastProvider } from "./components/ui";
import ProtectedRoute from "./components/ProtectedRoute";
import Layout from "./components/Layout";
import Login from "./pages/Login";
import Register from "./pages/Register";
import Dashboard from "./pages/Dashboard";
import Candidates from "./pages/Candidates";
import CandidateDetail from "./pages/CandidateDetail";
import Pipeline from "./pages/Pipeline";
import Interviews from "./pages/Interviews";
import Questionnaires from "./pages/Questionnaires";
import PolicyAgent from "./pages/PolicyAgent";
import ExamAnalysis from "./pages/ExamAnalysis";
import ScoringInsights from "./pages/ScoringInsights";
import JdGenerator from "./pages/JdGenerator";

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <ToastProvider>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Register />} />
            <Route element={<ProtectedRoute><Layout /></ProtectedRoute>}>
              <Route path="/" element={<Dashboard />} />
              <Route path="/candidates" element={<Candidates />} />
              <Route path="/candidates/:id" element={<CandidateDetail />} />
              <Route path="/pipeline" element={<Pipeline />} />
              <Route path="/interviews" element={<Interviews />} />
              <Route path="/questionnaires" element={<Questionnaires />} />
              <Route path="/policy-agent" element={<PolicyAgent />} />
              <Route path="/exam-analysis" element={<ExamAnalysis />} />
              <Route path="/scoring" element={<ScoringInsights />} />
              <Route path="/jd-generator" element={<JdGenerator />} />
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </ToastProvider>
      </AuthProvider>
    </BrowserRouter>
  );
}
