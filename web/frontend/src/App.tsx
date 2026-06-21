import React, { useState, useEffect } from 'react'
import GenerateForm from './components/GenerateForm'
import StatusTracker from './components/StatusTracker'
import ArticlePreview from './components/ArticlePreview'
import ArticleList from './components/ArticleList'
import Settings from './components/Settings'
import LogPanel from './components/LogPanel'
import { getModels, getArticle } from './api'
import type { ModelInfo, ArticleDetail } from './api'

type Nav = 'generate' | 'articles' | 'settings'
type ToastItem = { id: number; type: 'success' | 'error' | 'info'; text: string }

const NAV_META: Record<Nav, { title: string; sub: string; ico: string; label: string }> = {
  generate: { title: '生成文章', sub: '从 GitHub 仓库、文章链接或本地文件生成', ico: '✎', label: '生成' },
  articles: { title: '文章', sub: '查看与管理已生成的文章', ico: '☰', label: '文章' },
  settings: { title: '设置', sub: '模型、公众号与内容参数', ico: '⚙', label: '设置' },
}

export default function App() {
  const [models, setModels] = useState<ModelInfo[]>([])
  const [nav, setNav] = useState<Nav>('generate')
  const [taskId, setTaskId] = useState<string | null>(null)
  const [activeArticle, setActiveArticle] = useState<ArticleDetail | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)
  const [toasts, setToasts] = useState<ToastItem[]>([])

  useEffect(() => {
    getModels().then(setModels).catch(() => {})
  }, [])

  const addToast = (type: ToastItem['type'], text: string) => {
    const id = Date.now()
    setToasts(prev => [...prev, { id, type, text }])
    setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), 3200)
  }

  const handleGenerated = (tid: string) => {
    setTaskId(tid)
    setActiveArticle(null)
    setNav('generate')
  }

  const handleTaskDone = (articleId: number) => {
    setTaskId(null)
    getArticle(articleId).then(article => {
      setActiveArticle(article)
      setRefreshKey(k => k + 1)
    }).catch(() => addToast('error', '加载文章失败'))
  }

  const handlePublished = () => {
    addToast('success', '草稿创建成功')
    setRefreshKey(k => k + 1)
    if (activeArticle) {
      getArticle(activeArticle.id).then(setActiveArticle).catch(() => {})
    }
  }

  const availableModels = models.filter(m => m.has_key).length

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <div className="brand-mark">A</div>
          <div className="brand-text">
            <span className="brand-title">Auto WeChat</span>
            <span className="brand-sub">公众号自动化</span>
          </div>
        </div>

        <nav className="nav">
          {(Object.keys(NAV_META) as Nav[]).map(n => (
            <button
              key={n}
              className={`nav-item ${nav === n ? 'active' : ''}`}
              onClick={() => setNav(n)}
            >
              <span className="nav-ico">{NAV_META[n].ico}</span>
              {NAV_META[n].label}
            </button>
          ))}
        </nav>

        <div className="sidebar-footer">
          <span>
            <span className={`dot ${availableModels > 0 ? '' : 'off'}`} />
            {availableModels} 个模型可用
          </span>
          <span>本地服务 · 仅草稿</span>
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <div>
            <div className="topbar-title">{NAV_META[nav].title}</div>
            <div className="topbar-sub">{NAV_META[nav].sub}</div>
          </div>
        </header>

        <div className="content">
          {nav === 'generate' && (
            <div className="split">
              <GenerateForm
                models={models}
                onGenerated={handleGenerated}
                onError={msg => addToast('error', msg)}
              />
              <div>
                {taskId && (
                  <StatusTracker
                    taskId={taskId}
                    onDone={handleTaskDone}
                    onError={msg => addToast('error', msg)}
                  />
                )}
                {!taskId && activeArticle && (
                  <div className="card">
                    <ArticlePreview
                      article={activeArticle}
                      onBack={() => setActiveArticle(null)}
                      onPublished={handlePublished}
                    />
                  </div>
                )}
                {!taskId && !activeArticle && (
                  <div className="card">
                    <div className="empty-state">
                      <div className="empty-icon" />
                      <div className="empty-text">生成完成后，文章会在这里预览</div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {nav === 'articles' && (
            activeArticle ? (
              <div className="card">
                <ArticlePreview
                  article={activeArticle}
                  onBack={() => setActiveArticle(null)}
                  onPublished={handlePublished}
                />
              </div>
            ) : (
              <div className="card">
                <div className="card-title">
                  文章列表
                  <span className="sub">最近 50 篇</span>
                </div>
                <ArticleList onView={a => setActiveArticle(a)} refreshKey={refreshKey} />
              </div>
            )
          )}

          {nav === 'settings' && (
            <Settings
              onBack={() => setNav('generate')}
              onSaved={() => {
                addToast('success', '配置已保存')
                getModels().then(setModels).catch(() => {})
              }}
              onError={msg => addToast('error', msg)}
            />
          )}
        </div>

        <LogPanel />
      </main>

      <div className="toast-container">
        {toasts.map(t => (
          <div key={t.id} className={`toast ${t.type}`}>{t.text}</div>
        ))}
      </div>
    </div>
  )
}
