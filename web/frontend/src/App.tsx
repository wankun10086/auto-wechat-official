import React, { useState, useEffect } from 'react'
import GenerateForm from './components/GenerateForm'
import StatusTracker from './components/StatusTracker'
import ArticlePreview from './components/ArticlePreview'
import ArticleList from './components/ArticleList'
import Settings from './components/Settings'
import LogPanel from './components/LogPanel'
import { getModels, getArticle } from './api'
import type { ModelInfo, ArticleDetail } from './api'

type Page = 'home' | 'settings'
type ToastItem = { id: number; type: 'success' | 'error' | 'info'; text: string }

export default function App() {
  const [models, setModels] = useState<ModelInfo[]>([])
  const [taskId, setTaskId] = useState<string | null>(null)
  const [activeArticle, setActiveArticle] = useState<ArticleDetail | null>(null)
  const [rightTab, setRightTab] = useState<'preview' | 'list'>('list')
  const [toasts, setToasts] = useState<ToastItem[]>([])
  const [refreshKey, setRefreshKey] = useState(0)
  const [page, setPage] = useState<Page>('home')

  useEffect(() => {
    getModels().then(setModels).catch(() => {})
  }, [])

  const addToast = (type: ToastItem['type'], text: string) => {
    const id = Date.now()
    setToasts(prev => [...prev, { id, type, text }])
    setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), 3000)
  }

  const handleGenerated = (tid: string) => {
    setTaskId(tid)
    setRightTab('preview')
    setActiveArticle(null)
  }

  const handleTaskDone = (articleId: number) => {
    setTaskId(null)
    getArticle(articleId).then(article => {
      setActiveArticle(article)
      setRefreshKey(k => k + 1)
    }).catch(() => addToast('error', '加载文章失败'))
  }

  const handleViewArticle = (article: ArticleDetail) => {
    setActiveArticle(article)
    setRightTab('preview')
  }

  const handleBack = () => {
    setActiveArticle(null)
    setRightTab('list')
  }

  const handlePublished = () => {
    addToast('success', '发布成功')
    setRefreshKey(k => k + 1)
  }

  const handleSettingsSaved = () => {
    addToast('success', '配置已保存')
    getModels().then(setModels).catch(() => {})
  }

  return (
    <div className="app-container">
      <header className="header">
        <h1>
          Auto WeChat
          <span>公众号自动化发布</span>
        </h1>
        <div className="header-right">
          {models.length > 0 && (
            <span style={{ fontSize: 13, color: '#999' }}>
              {models.filter(m => m.has_key).length} 个模型可用
            </span>
          )}
          <button
            className={`header-btn ${page === 'settings' ? 'active' : ''}`}
            onClick={() => setPage(page === 'settings' ? 'home' : 'settings')}
          >
            {page === 'settings' ? '✕ 关闭' : '⚙ 设置'}
          </button>
        </div>
      </header>

      {page === 'settings' ? (
        <Settings
          onBack={() => setPage('home')}
          onSaved={handleSettingsSaved}
          onError={msg => addToast('error', msg)}
        />
      ) : (
        <div className="main-content">
          <div className="panel-left">
            <GenerateForm
              models={models}
              onGenerated={handleGenerated}
              onError={msg => addToast('error', msg)}
            />
          </div>

          <div className="panel-right">
            {taskId && !activeArticle && (
              <StatusTracker
                taskId={taskId}
                onDone={handleTaskDone}
                onError={msg => addToast('error', msg)}
              />
            )}

            <div className="card">
              <div className="tab-bar">
                <button
                  className={`tab-item ${rightTab === 'list' ? 'active' : ''}`}
                  onClick={() => { setRightTab('list'); setActiveArticle(null) }}
                >
                  文章列表
                </button>
                <button
                  className={`tab-item ${rightTab === 'preview' ? 'active' : ''}`}
                  onClick={() => setRightTab('preview')}
                  disabled={!activeArticle}
                >
                  文章预览
                </button>
              </div>

              {rightTab === 'preview' && activeArticle ? (
                <ArticlePreview
                  article={activeArticle}
                  onBack={handleBack}
                  onPublished={handlePublished}
                />
              ) : rightTab === 'preview' && !activeArticle ? (
                <div className="empty-state">
                  <div className="empty-icon">📄</div>
                  <div className="empty-text">选择一篇文章进行预览</div>
                </div>
              ) : null}

              {rightTab === 'list' && (
                <ArticleList
                  onView={handleViewArticle}
                  refreshKey={refreshKey}
                />
              )}
            </div>
          </div>
        </div>
      )}

      {page === 'home' && <LogPanel />}

      <div className="toast-container">
        {toasts.map(t => (
          <div key={t.id} className={`toast ${t.type}`}>{t.text}</div>
        ))}
      </div>
    </div>
  )
}
