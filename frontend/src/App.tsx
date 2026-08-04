import { Routes, Route, useNavigate, useLocation, Navigate } from 'react-router-dom'
import { ConfigProvider, theme, Layout, Menu } from 'antd'
import Login from './pages/Login'
import Sessions from './pages/Sessions'
import KnowledgeBase from './pages/KnowledgeBase'
import Register from './pages/Register'
import AdminDashboard from './pages/AdminDashboard'

const { Header, Content } = Layout

// 读取本地存储的当前用户角色, 决定菜单项与可访问路由。
// 普通用户(role != 'admin')只能看到"会话"页; 管理员还能看到"知识库"与"管理后台"。
function readCurrentUser(): { role?: string } | null {
  try {
    const raw = localStorage.getItem('user')
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

function isAdmin(): boolean {
  return readCurrentUser()?.role === 'admin'
}

function isAuthed(): boolean {
  return !!localStorage.getItem('token')
}

// 路由守卫: 仅管理员可进入知识库管理 / 管理后台。
// 未登录 -> /login; 已登录但非管理员 -> /sessions(会话页)。
function RequireAdmin({ children }: { children: React.ReactNode }) {
  if (!isAuthed()) return <Navigate to="/login" replace />
  if (!isAdmin()) return <Navigate to="/sessions" replace />
  return <>{children}</>
}

function App() {
  const navigate = useNavigate()
  const location = useLocation()
  const current = location.pathname.startsWith('/knowledge')
    ? '/knowledge'
    : location.pathname.startsWith('/admin')
    ? '/admin'
    : '/sessions'

  // 普通用户只能看到"会话"; 管理员额外显示"知识库"与"管理后台"。
  const menuItems = [
    { key: '/sessions', label: '会话' },
    ...(isAdmin()
      ? [
          { key: '/knowledge', label: '知识库' },
          { key: '/admin', label: '管理后台' },
        ]
      : []),
  ]

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
            items={menuItems}
          />
        </Header>
        <Content>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Register />} />
            <Route path="/sessions" element={<Sessions />} />
            <Route path="/knowledge" element={<RequireAdmin><KnowledgeBase /></RequireAdmin>} />
            <Route path="/admin" element={<RequireAdmin><AdminDashboard /></RequireAdmin>} />
            <Route path="/" element={<Sessions />} />
          </Routes>
        </Content>
      </Layout>
    </ConfigProvider>
  )
}

export default App
