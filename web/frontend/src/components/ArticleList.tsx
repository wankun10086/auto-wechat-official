import React, { useState, useEffect } from 'react'
import { getArticles, getArticle } from '../api'
import type { ArticleItem, ArticleDetail } from '../api'

interface Props {
  onView: (article: ArticleDetail) => void
  refreshKey: number
}

export default function ArticleList({ onView, refreshKey }: Props) {
  const [articles, setArticles] = useState<ArticleItem[]>([])
  const [loading, setLoading] = useState(true)

  const load = async () => {
    setLoading(true)
    try {
      const data = await getArticles()
      setArticles(data)
    } catch {} finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [refreshKey])

  const handleClick = async (item: ArticleItem) => {
    try {
      const detail = await getArticle(item.id)
      onView(detail)
    } catch {}
  }

  const formatDate = (s: string) => {
    if (!s) return ''
    try {
      return new Date(s).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
    } catch { return s }
  }

  const scoreClass = (score: number) => {
    if (score <= 30) return 'good'
    if (score <= 60) return 'medium'
    return 'bad'
  }

  const statusLabel: Record<string, string> = {
    draft: '草稿',
    draft_created: '已创建',
    published: '已发布',
    failed: '失败',
    processing: '处理中',
  }

  if (loading) {
    return (
      <div className="empty-state">
        <span className="loading-spinner large" />
      </div>
    )
  }

  if (articles.length === 0) {
    return (
      <div className="empty-state">
        <div className="empty-icon" />
        <div className="empty-text">还没有文章</div>
        <div className="empty-sub">去「生成」创建你的第一篇</div>
      </div>
    )
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 12 }}>
        <button className="btn btn-sm" onClick={load}>刷新</button>
      </div>
      <table className="article-list-table">
        <thead>
          <tr>
            <th>标题</th>
            <th>状态</th>
            <th>AI味</th>
            <th>时间</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          {articles.map(item => (
            <tr key={item.id}>
              <td className="col-title">
                <a onClick={() => handleClick(item)}>{item.title || '无标题'}</a>
              </td>
              <td>
                <span className={`status-badge ${item.status}`}>
                  {statusLabel[item.status] || item.status}
                </span>
              </td>
              <td className={`col-score ${scoreClass(item.ai_score)}`}>
                {item.ai_score != null ? `${item.ai_score}分` : '-'}
              </td>
              <td className="col-time">{formatDate(item.created_at)}</td>
              <td>
                <button className="btn btn-sm" onClick={() => handleClick(item)}>
                  查看
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
