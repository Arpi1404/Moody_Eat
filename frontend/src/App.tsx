import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import Landing from './pages/Landing'
import { HomePage } from './pages/HomePage'
import { PlanPage } from './pages/PlanPage'
import { QuestPage } from './pages/QuestPage'
import { ResultsPage } from './pages/ResultsPage'
import { SavedQuestsPage } from './pages/SavedQuestsPage'
import { JournalPage } from './pages/JournalPage'
import { BottomNav } from './components/BottomNav'
import './App.css'

const HIDE_NAV_PREFIXES = ['/quest/', '/landing']

function NavGate() {
  const { pathname } = useLocation()
  const hide = HIDE_NAV_PREFIXES.some((p) => pathname.startsWith(p))
  if (hide) return null
  return <BottomNav />
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/landing" element={<Landing />} />
        <Route path="/login" element={<HomePage />} />
        <Route path="/plan" element={<PlanPage />} />
        <Route path="/results" element={<ResultsPage />} />
        <Route path="/saved" element={<SavedQuestsPage />} />
        <Route path="/journal" element={<JournalPage />} />
        <Route path="/quest/preview/:id" element={<QuestPage preview />} />
        <Route path="/quest/:id" element={<QuestPage />} />
        <Route path="/explore" element={<Navigate to="/plan" replace />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      <NavGate />
    </BrowserRouter>
  )
}

export default App
