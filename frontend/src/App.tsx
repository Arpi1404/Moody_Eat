import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { LoginPage } from './pages/LoginPage'
import { PlanPage } from './pages/PlanPage'
import { ResultsPage } from './pages/ResultsPage'
import './App.css'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<LoginPage />} />
        <Route path="/plan" element={<PlanPage />} />
        <Route path="/results" element={<ResultsPage />} />
        <Route path="/explore" element={<Navigate to="/plan" replace />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
