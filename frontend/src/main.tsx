// React应用入口 — 挂载根组件，配置路由
import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'  // 浏览器路由
import App from './App'                            // 根组件
import './index.css'                               // 全局样式（Tailwind）

// 获取根DOM节点并渲染React应用
ReactDOM.createRoot(document.getElementById('root')!).render(
  // 严格模式：开发环境下检测潜在问题
  <React.StrictMode>
    {/* 路由容器：提供URL同步导航能力 */}
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>,
)
