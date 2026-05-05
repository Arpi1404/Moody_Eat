import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import Landing from './pages/Landing'
import { HomePage } from './pages/HomePage'
import { PlanPage } from './pages/PlanPage'
import { QuestPage } from './pages/QuestPage'
import { ResultsPage } from './pages/ResultsPage'
import './App.css'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/login" element={<HomePage />} />
        <Route path="/plan" element={<PlanPage />} />
        <Route path="/results" element={<ResultsPage />} />
        <Route path="/quest/preview/:id" element={<QuestPage preview />} />
        <Route path="/quest/:id" element={<QuestPage />} />
        <Route path="/explore" element={<Navigate to="/plan" replace />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
