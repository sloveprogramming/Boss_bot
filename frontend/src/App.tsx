import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import ToastContainer from './components/Toast'
import Dashboard from './pages/Dashboard'
import Candidates from './pages/Candidates'
import CandidateDetail from './pages/CandidateDetail'
import Questionnaires from './pages/Questionnaires'
import Interviews from './pages/Interviews'
import PolicyAgent from './pages/PolicyAgent'
import Pipeline from './pages/Pipeline'
import ExamAnalysis from './pages/ExamAnalysis'

export default function App() {
  return (
    <>
      <ToastContainer />
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/candidates" element={<Candidates />} />
          <Route path="/candidates/:id" element={<CandidateDetail />} />
          <Route path="/questionnaires" element={<Questionnaires />} />
          <Route path="/interviews" element={<Interviews />} />
          <Route path="/policy-agent" element={<PolicyAgent />} />
          <Route path="/pipeline" element={<Pipeline />} />
          <Route path="/exam-analysis" element={<ExamAnalysis />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </>
  )
}
