import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import Landing from './pages/Landing'
import { HomePage } from './pages/HomePage'
import { PlanPage } from './pages/PlanPage'
import { QuestPage } from './pages/QuestPage'
import { ResultsPage } from './pages/ResultsPage'
import { SavedQuestsPage } from './pages/SavedQuestsPage'
import { JournalPage } from './pages/JournalPage'
import { PrivacyPage, TermsPage } from './pages/LegalPage'
import { BottomNav } from './components/BottomNav'
import { Footer } from './components/Footer'
import { TopNav } from './components/TopNav'
import './App.css'

const HIDE_TOPNAV_PREFIXES = ['/landing']
const HIDE_BOTTOMNAV_PREFIXES = ['/quest/', '/landing']
const HIDE_FOOTER_PREFIXES = ['/landing', '/quest/']

function TopNavGate() {
  const { pathname } = useLocation()
  const hide = HIDE_TOPNAV_PREFIXES.some((p) => pathname.startsWith(p))
  if (hide) return null
  return <TopNav />
}

function BottomNavGate() {
  const { pathname } = useLocation()
  const hide = HIDE_BOTTOMNAV_PREFIXES.some((p) => pathname.startsWith(p))
  if (hide) return null
  return <BottomNav />
}

function FooterGate() {
  const { pathname } = useLocation()
  const hide = HIDE_FOOTER_PREFIXES.some((p) => pathname.startsWith(p))
  if (hide) return null
  return <Footer />
}

function App() {
  return (
    <BrowserRouter>
      <TopNavGate />
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
        <Route path="/privacy" element={<PrivacyPage />} />
        <Route path="/terms" element={<TermsPage />} />
        <Route path="/explore" element={<Navigate to="/plan" replace />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      <FooterGate />
      <BottomNavGate />
    </BrowserRouter>
  )
}

export default App
