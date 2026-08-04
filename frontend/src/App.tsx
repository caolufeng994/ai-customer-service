import { Routes, Route, useNavigate, useLocation } from 'react-router-dom'
import { ConfigProvider, theme, Layout, Menu } from 'antd'
import Login from './pages/Login'
import Sessions from './pages/Sessions'
import KnowledgeBase from './pages/KnowledgeBase'
import Register from './pages/Register'

const { Header, Content } = Layout

function App() {
  const navigate = useNavigate()
  const location = useLocation()
  const current = location.pathname.startsWith('/knowledge')
    ? '/knowledge'
    : '/sessions'

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
      <Layout style={{ minHeight: '100vh' }}>
        <Header style={{ display: 'flex', alignItems: 'center', paddingInline: 24 }}>
          <div style={{ color: '#5b8cff', fontWeight: 700, marginRight: 32 }}>AI 客服</div>
          <Menu
            mode="horizontal"
            selectedKeys={[current]}
            style={{ flex: 1, borderBottom: 'none' }}
            onClick={({ key }) => navigate(key)}
            items={[
              { key: '/sessions', label: '会话' },
              { key: '/knowledge', label: '知识库' },
            ]}
          />
        </Header>
        <Content>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Register />} />
            <Route path="/sessions" element={<Sessions />} />
            <Route path="/knowledge" element={<KnowledgeBase />} />
            <Route path="/" element={<Sessions />} />
          </Routes>
        </Content>
      </Layout>
    </ConfigProvider>
  )
}

export default App
