import { Routes, Route } from 'react-router-dom'
import { ConfigProvider, theme } from 'antd'
import Login from './pages/Login'
import Sessions from './pages/Sessions'
import KnowledgeBase from './pages/KnowledgeBase'

function App() {
  return (
    <ConfigProvider
      theme={{
        algorithm: theme.defaultAlgorithm,
        token: {
          colorPrimary: '#5b8cff',
          colorSuccess: '#52c41a',
          colorWarning: '#faad14',
          colorError: '#ff4d4f',
          colorInfo: '#1890ff',
          borderRadius: 8,
          fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
        },
        components: {
          Layout: {
            siderBg: '#f8fafc',
            headerBg: '#ffffff',
            bodyBg: '#f1f5f9',
          },
          Card: {
            colorBgContainer: '#ffffff',
            borderRadiusLG: 12,
          },
          Button: {
            borderRadius: 8,
          },
          Input: {
            borderRadius: 8,
          },
        },
      }}
    >
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/sessions" element={<Sessions />} />
        <Route path="/knowledge" element={<KnowledgeBase />} />
        <Route path="/" element={<Sessions />} />
      </Routes>
    </ConfigProvider>
  )
}

export default App
