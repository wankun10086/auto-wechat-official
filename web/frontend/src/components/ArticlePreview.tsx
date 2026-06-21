import React, { useState } from 'react'
import { publishArticle } from '../api'
import type { ArticleDetail, MediaItem } from '../api'

interface Props {
  article: ArticleDetail
  onBack: () => void
  onPublished: () => void
}

export default function ArticlePreview({ article, onBack, onPublished }: Props) {
  const [publishing, setPublishing] = useState(false)

  const handlePublish = async () => {
    setPublishing(true)
    try {
      const result = await publishArticle(article.id)
      if (result.success) {
        onPublished()
      } else {
        alert(result.message || '发布失败')
      }
    } catch {
      alert('发布请求失败')
    } finally {
      setPublishing(false)
    }
  }

  const formatDate = (s: string) => {
    if (!s) return ''
    try { return new Date(s).toLocaleString('zh-CN') } catch { return s }
  }

  const mediaItems = [
    ...((article.material_images || []).map(item => ({ ...item, group: '素材图' }))),
    ...((article.ai_images || []).map(item => ({ ...item, group: 'AI配图' }))),
    ...((article.screenshots || []).map(item => ({ ...item, group: '截图' }))),
  ]

  return (
    <div className="article-preview">
      <button className="back-btn" onClick={onBack}>
        ← 返回列表
      </button>

      <div className="preview-header">
        <h2 className="preview-title">{article.title}</h2>
        <div className="preview-meta">
          <span className="meta-item">作者: {article.author || '-'}</span>
          <span className="meta-item">主题: {article.topic || '-'}</span>
          <span className="meta-item">
            AI味: {article.ai_score != null ? `${article.ai_score}分` : '-'}
          </span>
          <span className="meta-item">
            状态: <span className={`status-badge ${article.status}`}>{article.status}</span>
          </span>
          <span className="meta-item">创建: {formatDate(article.created_at)}</span>
          {article.published_at && (
            <span className="meta-item">发布: {formatDate(article.published_at)}</span>
          )}
        </div>
      </div>

      {article.digest && (
        <div className="preview-digest">{article.digest}</div>
      )}

      {(article.source_urls?.length || mediaItems.length || article.warnings?.length) ? (
        <div className="preview-evidence">
          {article.warnings?.length ? (
            <div className="evidence-warnings">
              {article.warnings.map((warning, idx) => (
                <span key={`${warning}-${idx}`}>{warning}</span>
              ))}
            </div>
          ) : null}

          {article.source_urls?.length ? (
            <div className="evidence-block">
              <div className="evidence-title">检索来源</div>
              <div className="source-list">
                {article.source_urls.slice(0, 8).map((url, idx) => (
                  <a key={`${url}-${idx}`} href={url} target="_blank" rel="noreferrer">
                    {idx + 1}. {shortUrl(url)}
                  </a>
                ))}
              </div>
            </div>
          ) : null}

          {mediaItems.length ? (
            <div className="evidence-block">
              <div className="evidence-title">配图素材</div>
              <div className="media-strip">
                {mediaItems.slice(0, 8).map((item, idx) => (
                  <MediaThumb key={`${item.path || item.url || idx}-${idx}`} item={item} />
                ))}
              </div>
            </div>
          ) : null}
        </div>
      ) : null}

      <div
        className="preview-body"
        dangerouslySetInnerHTML={{ __html: article.content }}
      />

      <div className="article-actions">
        {article.status !== 'published' && article.status !== 'draft_created' && (
          <button
            className="btn btn-primary"
            onClick={handlePublish}
            disabled={publishing}
          >
            {publishing && <span className="loading-spinner" />}
            推送到草稿箱
          </button>
        )}
        {article.status === 'draft_created' && (
          <span className="published-note">已在微信草稿箱</span>
        )}
        {article.status === 'published' && (
          <span className="published-note">已发布到微信</span>
        )}
      </div>
    </div>
  )
}

function MediaThumb({ item }: { item: MediaItem & { group?: string } }) {
  const src = item.preview_url || item.url || ''
  const label = item.description || item.alt || item.group || '配图'
  return (
    <div className="media-thumb">
      {src ? <img src={src} alt={label} /> : <div className="media-thumb-fallback" />}
      <div>
        <span>{item.group || '配图'}</span>
        <strong>{label}</strong>
      </div>
    </div>
  )
}

function shortUrl(url: string) {
  try {
    const parsed = new URL(url)
    const path = parsed.pathname === '/' ? '' : parsed.pathname
    return `${parsed.hostname}${path}`.slice(0, 72)
  } catch {
    return url.slice(0, 72)
  }
}
