// 应用布局组件：侧边导航 + 主内容区
import { Outlet, NavLink, useLocation } from 'react-router-dom'
import {
  LayoutDashboard, Users, FileText, Calendar, Bot, GitBranch, ClipboardList, Menu, X, Sparkles
} from 'lucide-react'
import { useState } from 'react'

const navItems = [
  { path: '/', label: '仪表盘', icon: LayoutDashboard },
  { path: '/candidates', label: '候选人', icon: Users },
  { path: '/questionnaires', label: '问卷管理', icon: FileText },
  { path: '/interviews', label: '面试排期', icon: Calendar },
  { path: '/policy-agent', label: 'AI 问答', icon: Bot },
  { path: '/pipeline', label: '流程管道', icon: GitBranch },
  { path: '/exam-analysis', label: '试卷分析', icon: ClipboardList },
]

export default function Layout() {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const location = useLocation()

  return (
    <div className="flex h-screen bg-gradient-to-br from-indigo-50/50 via-purple-50/30 to-cyan-50/40">
      {/* 移动端遮罩 */}
      {sidebarOpen && (
        <div className="fixed inset-0 z-20 bg-black/30 backdrop-blur-sm lg:hidden"
             onClick={() => setSidebarOpen(false)} />
      )}

      {/* 侧边栏 */}
      <aside className={`
        fixed inset-y-0 left-0 z-30 w-64 flex flex-col
        bg-gradient-to-b from-white via-white to-indigo-50/50
        border-r border-indigo-100/60
        transform transition-transform duration-300 ease-out
        lg:relative lg:translate-x-0
        ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'}
      `}>
        {/* Logo */}
        <div className="flex items-center justify-between h-16 px-5 border-b border-indigo-100/60">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center">
              <Sparkles className="w-4 h-4 text-white" />
            </div>
            <div>
              <h1 className="text-sm font-bold">
                <span className="gradient-text">AI</span>
                <span className="text-gray-700"> 招聘助手</span>
              </h1>
              <p className="text-[10px] text-gray-400 leading-none">智能招聘自动化</p>
            </div>
          </div>
          <button onClick={() => setSidebarOpen(false)} className="lg:hidden p-1 rounded-lg hover:bg-gray-100">
            <X className="w-4 h-4 text-gray-400" />
          </button>
        </div>

        {/* 导航菜单 */}
        <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
          <p className="px-3 mb-2 text-[10px] font-semibold uppercase tracking-wider text-gray-400">主导航</p>
          {navItems.map(item => (
            <NavLink
              key={item.path}
              to={item.path}
              end={item.path === '/'}
              onClick={() => setSidebarOpen(false)}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all duration-200 group ${
                  isActive
                    ? 'bg-indigo-50 text-indigo-700 shadow-sm'
                    : 'text-gray-600 hover:text-gray-900 hover:bg-gray-50'
                }`
              }
            >
              {({ isActive }) => (
                <>
                  <div className={`w-8 h-8 rounded-lg flex items-center justify-center transition-all duration-200 ${
                    isActive
                      ? 'bg-gradient-to-br from-indigo-500 to-purple-600 text-white shadow-lg shadow-indigo-500/25'
                      : 'bg-gray-100 text-gray-500 group-hover:bg-gray-200'
                  }`}>
                    <item.icon className="w-4 h-4" />
                  </div>
                  {item.label}
                  {isActive && (
                    <div className="ml-auto w-1.5 h-1.5 rounded-full bg-indigo-500" />
                  )}
                </>
              )}
            </NavLink>
          ))}
        </nav>

        {/* 底部信息 */}
        <div className="p-4 border-t border-indigo-100/60">
          <div className="flex items-center gap-3 px-2 py-2 rounded-xl bg-gradient-to-r from-indigo-50 to-purple-50">
            <div className="w-8 h-8 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-white text-xs font-bold">
              AI
            </div>
            <div>
              <p className="text-xs font-medium text-gray-700">AI 招聘助手</p>
              <p className="text-[10px] text-gray-400">v1.0.0</p>
            </div>
          </div>
        </div>
      </aside>

      {/* 主内容区 */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* 移动端顶部栏 */}
        <header className="flex items-center justify-between h-14 px-4 bg-white/80 backdrop-blur-xl border-b border-indigo-100/60 lg:hidden">
          <button onClick={() => setSidebarOpen(true)} className="p-2 rounded-lg hover:bg-gray-100">
            <Menu className="w-5 h-5 text-gray-600" />
          </button>
          <span className="text-sm font-medium text-gray-600">
            {navItems.find(i => location.pathname === i.path || (i.path !== '/' && location.pathname.startsWith(i.path)))?.label || 'AI 招聘助手'}
          </span>
          <div className="w-6" />
        </header>

        {/* 桌面端顶部栏 */}
        <header className="hidden lg:flex items-center justify-between h-14 px-6 bg-white/60 backdrop-blur-sm border-b border-indigo-100/60">
          <div className="flex items-center gap-2">
            <p className="text-sm text-gray-400">当前页面</p>
            <span className="text-gray-300">/</span>
            <p className="text-sm font-medium text-gray-700">
              {navItems.find(i => location.pathname === i.path || (i.path !== '/' && location.pathname.startsWith(i.path)))?.label || '仪表盘'}
            </p>
          </div>
          <div className="flex items-center gap-3">
            <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            <span className="text-xs text-gray-400">系统运行中</span>
          </div>
        </header>

        {/* 页面内容 */}
        <main className="flex-1 overflow-auto p-6 lg:p-8">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
