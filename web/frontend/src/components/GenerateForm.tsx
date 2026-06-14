import React, { useState } from 'react'
import { generate } from '../api'
import type { GenerateParams, ModelInfo } from '../api'

const STYLES = [
  { value: 'tech_explanation', label: '技术解析' },
  { value: 'product_review', label: '产品评测' },
  { value: 'industry_analysis', label: '行业分析' },
  { value: 'tutorial', label: '教程指南' },
]

interface Props {
  models: ModelInfo[]
  onGenerated: (taskId: string) => void
  onError: (msg: string) => void
}

export default function GenerateForm({ models, onGenerated, onError }: Props) {
  const [url, setUrl] = useState('')
  const [selectedModel, setSelectedModel] = useState('')
  const [style, setStyle] = useState('tech_explanation')
  const [prompt, setPrompt] = useState('')
  const [screenshot, setScreenshot] = useState('')
  const [noImages, setNoImages] = useState(false)
  const [publish, setPublish] = useState(false)
  const [loading, setLoading] = useState(false)

  const screenshotOptions = [
    { value: 'code', label: '代码块' },
    { value: 'chart', label: '图表' },
    { value: 'table', label: '表格' },
    { value: 'image', label: '图片' },
    { value: 'fullpage', label: '全页面' },
  ]

  const handleScreenshotToggle = (val: string) => {
    setScreenshot(prev => {
      const parts = prev ? prev.split(',').filter(Boolean) : []
      if (parts.includes(val)) {
        return parts.filter(p => p !== val).join(',')
      }
      return [...parts, val].join(',')
    })
  }

  const handleSubmit = async (shouldPublish: boolean) => {
    if (!url.trim()) {
      onError('请输入链接地址')
      return
    }
    setLoading(true)
    try {
      const params: GenerateParams = {
        url: url.trim(),
        model: selectedModel || undefined,
        style,
        prompt: prompt.trim(),
        screenshot,
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

  return (
    <div className="card">
      <div className="card-title">生成文章</div>

      <div className="form-group">
        <label>源链接</label>
        <input
          className="input"
          type="url"
          placeholder="粘贴GitHub仓库、技术文章、任意网页链接"
          value={url}
          onChange={e => setUrl(e.target.value)}
        />
      </div>

      <div className="form-group">
        <label>选择模型</label>
        <div className="model-cards">
          {models.length === 0 ? (
            <>
              {['DeepSeek', 'Kimi', 'MiniMax'].map(name => (
                <div key={name} className="model-card disabled">
                  <div className="model-name">{name}</div>
                  <div className="model-status">加载中...</div>
                </div>
              ))}
            </>
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

      <div className="form-group">
        <label>截图选项</label>
        <div className="checkbox-group">
          {screenshotOptions.map(opt => (
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

      <div className="form-group">
        <label>额外提示词（可选）</label>
        <textarea
          className="textarea"
          placeholder="输入额外的写作要求或提示..."
          value={prompt}
          onChange={e => setPrompt(e.target.value)}
          rows={3}
        />
      </div>

      <div className="form-group">
        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={noImages}
            onChange={e => setNoImages(e.target.checked)}
          />
          不包含图片
        </label>
      </div>

      <div className="btn-group">
        <button
          className="btn btn-primary btn-block"
          onClick={() => handleSubmit(false)}
          disabled={loading || !url.trim()}
        >
          {loading && <span className="loading-spinner" />}
          生成文章
        </button>
        <button
          className="btn btn-block"
          onClick={() => handleSubmit(true)}
          disabled={loading || !url.trim()}
        >
          生成并发布
        </button>
      </div>
    </div>
  )
}
