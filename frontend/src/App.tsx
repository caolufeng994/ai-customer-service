import { Routes, Route } from 'react-router-dom'
import Login from './pages/Login'
import Sessions from './pages/Sessions'
import KnowledgeBase from './pages/KnowledgeBase'

function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/sessions" element={<Sessions />} />
      <Route path="/knowledge" element={<KnowledgeBase />} />
      <Route path="/" element={<Sessions />} />
    </Routes>
  )
}

export default App
