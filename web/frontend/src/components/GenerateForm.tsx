import React, { useState, useRef } from 'react'
import { generate, uploadFile } from '../api'
import type { GenerateParams, ModelInfo, UploadResult } from '../api'

const STYLES = [
  { value: 'tech_explanation', label: '技术解析' },
  { value: 'product_review', label: '产品评测' },
  { value: 'industry_analysis', label: '行业分析' },
  { value: 'tutorial', label: '教程指南' },
]

const SCREENSHOT_OPTIONS = [
  { value: 'code', label: '代码块' },
  { value: 'charts', label: '图表' },
  { value: 'tables', label: '表格' },
  { value: 'images', label: '图片' },
  { value: 'fullpage', label: '全页面' },
]

type SourceType = 'url' | 'file' | 'topic'

interface Props {
  models: ModelInfo[]
  onGenerated: (taskId: string) => void
  onError: (msg: string) => void
}

export default function GenerateForm({ models, onGenerated, onError }: Props) {
  const [sourceType, setSourceType] = useState<SourceType>('url')
  const [url, setUrl] = useState('')
  const [topic, setTopic] = useState('')
  const [uploaded, setUploaded] = useState<UploadResult | null>(null)
  const [uploading, setUploading] = useState(false)
  const [dragging, setDragging] = useState(false)

  const [selectedModel, setSelectedModel] = useState('')
  const [style, setStyle] = useState('tech_explanation')
  const [prompt, setPrompt] = useState('')
  const [screenshot, setScreenshot] = useState('')
  const [noImages, setNoImages] = useState(false)
  const [loading, setLoading] = useState(false)

  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleScreenshotToggle = (val: string) => {
    setScreenshot(prev => {
      const parts = prev ? prev.split(',').filter(Boolean) : []
      if (parts.includes(val)) return parts.filter(p => p !== val).join(',')
      return [...parts, val].join(',')
    })
  }

  const handleFile = async (file?: File | null) => {
    if (!file) return
    setUploading(true)
    try {
      const result = await uploadFile(file)
      setUploaded(result)
    } catch (e) {
      onError((e as Error).message || '上传失败')
      setUploaded(null)
    } finally {
      setUploading(false)
    }
  }

  const canSubmit = () => {
    if (loading || uploading) return false
    if (sourceType === 'url') return !!url.trim()
    if (sourceType === 'topic') return !!topic.trim()
    return !!uploaded
  }

  const handleSubmit = async (shouldPublish: boolean) => {
    if (sourceType === 'url' && !url.trim()) { onError('请输入链接地址'); return }
    if (sourceType === 'file' && !uploaded) { onError('请先上传文件'); return }
    if (sourceType === 'topic' && !topic.trim()) { onError('请输入议题'); return }
    setLoading(true)
    try {
      const params: GenerateParams = {
        url: sourceType === 'file' ? uploaded!.path : url.trim(),
        topic: topic.trim(),
        source_type: sourceType,
        model: selectedModel || undefined,
        style,
        prompt: prompt.trim(),
        screenshot: sourceType === 'url' ? screenshot : '',
        no_images: noImages,
        publish: shouldPublish,
      }
      const result = await generate(params)
      onGenerated(result.task_id)
    } catch {
      onError('请求失败，请检查网络')
    } finally {
      setLoading(false)
    }
  }

  const switchSource = (t: SourceType) => {
    setSourceType(t)
    if (t !== 'url') setScreenshot('')
  }

  return (
    <div className="card">
      <div className="card-title">生成文章</div>

      <div className="form-group">
        <label>内容来源</label>
        <div className="segmented">
          <button
            type="button"
            className={`seg ${sourceType === 'url' ? 'active' : ''}`}
            onClick={() => switchSource('url')}
          >链接</button>
          <button
            type="button"
            className={`seg ${sourceType === 'file' ? 'active' : ''}`}
            onClick={() => switchSource('file')}
          >本地文件</button>
          <button
            type="button"
            className={`seg ${sourceType === 'topic' ? 'active' : ''}`}
            onClick={() => switchSource('topic')}
          >议题</button>
        </div>
      </div>

      {sourceType === 'url' ? (
        <div className="form-group">
          <label>源链接</label>
          <input
            className="input"
            type="url"
            placeholder="粘贴 GitHub 仓库、技术文章或任意网页链接"
            value={url}
            onChange={e => setUrl(e.target.value)}
          />
        </div>
      ) : sourceType === 'file' ? (
        <div className="form-group">
          <label>本地文件</label>
          <div
            className={`dropzone ${dragging ? 'drag' : ''} ${uploaded ? 'filled' : ''}`}
            onClick={() => !uploading && fileInputRef.current?.click()}
            onDragOver={e => { e.preventDefault(); setDragging(true) }}
            onDragLeave={() => setDragging(false)}
            onDrop={e => {
              e.preventDefault(); setDragging(false)
              handleFile(e.dataTransfer.files?.[0])
            }}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".md,.markdown,.txt,.html,.htm"
              hidden
              onChange={e => handleFile(e.target.files?.[0])}
            />
            {uploading ? (
              <div className="dropzone-status"><span className="loading-spinner" /> 上传中…</div>
            ) : uploaded ? (
              <div className="dropzone-file">
                <span className="file-name">{uploaded.name}</span>
                <span className="file-size">{(uploaded.size / 1024).toFixed(1)} KB</span>
                <button
                  type="button"
                  className="file-remove"
                  onClick={e => { e.stopPropagation(); setUploaded(null) }}
                >移除</button>
              </div>
            ) : (
              <div className="dropzone-hint">点击或拖入文件 · 支持 .md .txt .html</div>
            )}
          </div>
        </div>
      ) : (
        <div className="form-group">
          <label>议题</label>
          <textarea
            className="textarea"
            placeholder="输入一个议题，例如：AI Agent 产品趋势、GLM 新模型解读、微信生态自动化"
            value={topic}
            onChange={e => setTopic(e.target.value)}
            rows={3}
          />
        </div>
      )}

      <div className="form-group">
        <label>选择模型</label>
        <div className="model-cards">
          {models.length === 0 ? (
            ['DeepSeek', 'Kimi', 'MiniMax'].map(name => (
              <div key={name} className="model-card disabled">
                <div className="model-name">{name}</div>
                <div className="model-status">加载中…</div>
              </div>
            ))
          ) : (
            models.map(m => (
              <div
                key={m.name}
                className={`model-card ${selectedModel === m.name ? 'selected' : ''} ${!m.has_key ? 'disabled' : ''}`}
                onClick={() => m.has_key && setSelectedModel(m.name)}
              >
                <div className="model-name">{m.name}</div>
                <div className={`model-status ${m.has_key ? 'available' : ''}`}>
                  {m.is_current ? '当前使用' : m.has_key ? '可用' : '未配置'}
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      <div className="form-group">
        <label>文章风格</label>
        <select className="select" value={style} onChange={e => setStyle(e.target.value)}>
          {STYLES.map(s => (
            <option key={s.value} value={s.value}>{s.label}</option>
          ))}
        </select>
      </div>

      {sourceType === 'url' && (
        <div className="form-group">
          <label>截图选项</label>
          <div className="checkbox-group">
            {SCREENSHOT_OPTIONS.map(opt => (
              <label key={opt.value} className="checkbox-label">
                <input
                  type="checkbox"
                  checked={screenshot.split(',').includes(opt.value)}
                  onChange={() => handleScreenshotToggle(opt.value)}
                />
                {opt.label}
              </label>
            ))}
          </div>
        </div>
      )}

      <div className="form-group">
        <label>额外提示词（可选）</label>
        <textarea
          className="textarea"
          placeholder="输入额外的写作要求或提示…"
          value={prompt}
          onChange={e => setPrompt(e.target.value)}
          rows={3}
        />
      </div>

      <div className="form-group">
        <label className="checkbox-label">
          <input type="checkbox" checked={noImages} onChange={e => setNoImages(e.target.checked)} />
          不包含图片
        </label>
      </div>

      <div className="btn-group">
        <button
          className="btn btn-primary btn-block"
          onClick={() => handleSubmit(false)}
          disabled={!canSubmit()}
        >
          {loading && <span className="loading-spinner" />}
          生成文章
        </button>
        <button
          className="btn btn-block"
          onClick={() => handleSubmit(true)}
          disabled={!canSubmit()}
        >
          生成并推送到草稿箱
        </button>
      </div>
    </div>
  )
}
