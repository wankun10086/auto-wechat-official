import React, { useState, useEffect } from 'react'
import { getSettings, updateSettings } from '../api'
import type { SettingsData } from '../api'

interface Props {
  onBack: () => void
  onSaved: () => void
  onError: (msg: string) => void
}

export default function Settings({ onBack, onSaved, onError }: Props) {
  const [settings, setSettings] = useState<SettingsData | null>(null)
  const [saving, setSaving] = useState(false)
  const [activeTab, setActiveTab] = useState<'ai' | 'wechat' | 'content'>('ai')

  useEffect(() => {
    getSettings().then(setSettings).catch(() => onError('加载配置失败'))
  }, [])

  const handleSave = async () => {
    if (!settings) return
    setSaving(true)
    try {
      const res = await updateSettings(settings)
      if (res.success) {
        onSaved()
      } else {
        onError(res.message)
      }
    } catch {
      onError('保存失败')
    } finally {
      setSaving(false)
    }
  }

  const updateAi = (provider: string, key: string, value: string) => {
    if (!settings) return
    const current = (settings.ai as Record<string, unknown>)[provider] as Record<string, unknown> || {}
    setSettings({
      ...settings,
      ai: {
        ...settings.ai,
        [provider]: { ...current, [key]: value },
      },
    })
  }

  const updateAiGlobal = (key: string, value: number | string) => {
    if (!settings) return
    setSettings({ ...settings, ai: { ...settings.ai, [key]: value } })
  }

  const updateWechat = (key: string, value: string) => {
    if (!settings) return
    setSettings({ ...settings, wechat: { ...settings.wechat, [key]: value } })
  }

  const updateContent = (key: string, value: number) => {
    if (!settings) return
    setSettings({ ...settings, content: { ...settings.content, [key]: value } })
  }

  const keyPlaceholder = (provider: 'deepseek' | 'kimi' | 'minimax' | 'glm', fallback: string) => {
    const current = settings?.ai[provider]
    return current?.api_key_set ? '已配置，留空不修改' : fallback
  }

  const keyHint = (provider: 'deepseek' | 'kimi' | 'minimax' | 'glm') => {
    const current = settings?.ai[provider]
    return current?.api_key_set ? <div className="hint">API Key 已配置；只有输入新值才会覆盖。</div> : null
  }

  if (!settings) {
    return (
      <div className="card">
        <div className="empty-state">
          <div className="loading-spinner large" />
          <div className="empty-text" style={{ marginTop: 16 }}>加载配置中...</div>
        </div>
      </div>
    )
  }

  return (
    <div className="card">
      <div className="card-title">
        <button className="back-btn" onClick={onBack}>← 返回</button>
        <span>系统设置</span>
        <button className="btn btn-primary btn-sm" onClick={handleSave} disabled={saving}>
          {saving ? '保存中...' : '保存配置'}
        </button>
      </div>

      <div className="settings-tabs">
        <button className={`settings-tab ${activeTab === 'ai' ? 'active' : ''}`} onClick={() => setActiveTab('ai')}>
          模型配置
        </button>
        <button className={`settings-tab ${activeTab === 'wechat' ? 'active' : ''}`} onClick={() => setActiveTab('wechat')}>
          微信配置
        </button>
        <button className={`settings-tab ${activeTab === 'content' ? 'active' : ''}`} onClick={() => setActiveTab('content')}>
          内容配置
        </button>
      </div>

      {activeTab === 'ai' && (
        <div className="settings-section">
          <div className="settings-group">
            <h3>默认模型</h3>
            <div className="form-group">
              <label>当前使用的模型</label>
              <select className="select" value={settings.ai.provider} onChange={e => updateAiGlobal('provider', e.target.value)}>
                <option value="deepseek">DeepSeek</option>
                <option value="kimi">Kimi</option>
                <option value="minimax">MiniMax</option>
                <option value="glm">GLM</option>
              </select>
            </div>
            <div className="form-row">
              <div className="form-group" style={{ flex: 1 }}>
                <label>Temperature</label>
                <input className="input" type="number" step="0.1" min="0" max="2" value={settings.ai.temperature} onChange={e => updateAiGlobal('temperature', parseFloat(e.target.value))} />
              </div>
              <div className="form-group" style={{ flex: 1 }}>
                <label>Max Tokens</label>
                <input className="input" type="number" step="100" value={settings.ai.max_tokens} onChange={e => updateAiGlobal('max_tokens', parseInt(e.target.value))} />
              </div>
            </div>
          </div>

          <div className="settings-group">
            <h3>
              DeepSeek
              {settings.ai.provider === 'deepseek' && <span className="current-badge">当前使用</span>}
            </h3>
            <div className="form-group">
              <label>API Key</label>
              <input className="input" type="password" placeholder={keyPlaceholder('deepseek', 'sk-...')} value={settings.ai.deepseek.api_key || ''} onChange={e => updateAi('deepseek', 'api_key', e.target.value)} />
              {keyHint('deepseek')}
            </div>
            <div className="form-row">
              <div className="form-group" style={{ flex: 1 }}>
                <label>Base URL</label>
                <input className="input" value={settings.ai.deepseek.base_url || ''} onChange={e => updateAi('deepseek', 'base_url', e.target.value)} />
              </div>
              <div className="form-group" style={{ flex: 1 }}>
                <label>模型名称</label>
                <input className="input" value={settings.ai.deepseek.model || ''} onChange={e => updateAi('deepseek', 'model', e.target.value)} />
              </div>
            </div>
          </div>

          <div className="settings-group">
            <h3>
              Kimi (Moonshot)
              {settings.ai.provider === 'kimi' && <span className="current-badge">当前使用</span>}
            </h3>
            <div className="form-group">
              <label>API Key</label>
              <input className="input" type="password" placeholder={keyPlaceholder('kimi', 'sk-...')} value={settings.ai.kimi.api_key || ''} onChange={e => updateAi('kimi', 'api_key', e.target.value)} />
              {keyHint('kimi')}
            </div>
            <div className="form-row">
              <div className="form-group" style={{ flex: 1 }}>
                <label>Base URL</label>
                <input className="input" value={settings.ai.kimi.base_url || ''} onChange={e => updateAi('kimi', 'base_url', e.target.value)} />
              </div>
              <div className="form-group" style={{ flex: 1 }}>
                <label>模型名称</label>
                <input className="input" value={settings.ai.kimi.model || ''} onChange={e => updateAi('kimi', 'model', e.target.value)} />
              </div>
            </div>
          </div>

          <div className="settings-group">
            <h3>
              MiniMax
              {settings.ai.provider === 'minimax' && <span className="current-badge">当前使用</span>}
            </h3>
            <div className="form-group">
              <label>API Key</label>
              <input className="input" type="password" placeholder={keyPlaceholder('minimax', '输入MiniMax API Key')} value={settings.ai.minimax.api_key || ''} onChange={e => updateAi('minimax', 'api_key', e.target.value)} />
              {keyHint('minimax')}
            </div>
            <div className="form-row">
              <div className="form-group" style={{ flex: 1 }}>
                <label>Base URL</label>
                <input className="input" value={settings.ai.minimax.base_url || ''} onChange={e => updateAi('minimax', 'base_url', e.target.value)} />
              </div>
              <div className="form-group" style={{ flex: 1 }}>
                <label>文本模型</label>
                <input className="input" value={settings.ai.minimax.model || ''} onChange={e => updateAi('minimax', 'model', e.target.value)} />
              </div>
            </div>
            <div className="form-group">
              <label>图片模型</label>
              <input className="input" value={settings.ai.minimax.image_model || ''} onChange={e => updateAi('minimax', 'image_model', e.target.value)} />
              <div className="hint">用于AI配图生成，如 image-01</div>
            </div>
          </div>
          <div className="settings-group">
            <h3>
              GLM
              {settings.ai.provider === 'glm' && <span className="current-badge">当前使用</span>}
            </h3>
            <div className="form-group">
              <label>API Key</label>
              <input className="input" type="password" placeholder={keyPlaceholder('glm', '输入智谱 API Key')} value={settings.ai.glm?.api_key || ''} onChange={e => updateAi('glm', 'api_key', e.target.value)} />
              {keyHint('glm')}
            </div>
            <div className="form-row">
              <div className="form-group" style={{ flex: 1 }}>
                <label>Base URL</label>
                <input className="input" value={settings.ai.glm?.base_url || ''} onChange={e => updateAi('glm', 'base_url', e.target.value)} />
              </div>
              <div className="form-group" style={{ flex: 1 }}>
                <label>文本模型</label>
                <input className="input" value={settings.ai.glm?.model || ''} onChange={e => updateAi('glm', 'model', e.target.value)} />
              </div>
            </div>
            <div className="form-row">
              <div className="form-group" style={{ flex: 1 }}>
                <label>图片模型</label>
                <input className="input" value={settings.ai.glm?.image_model || ''} onChange={e => updateAi('glm', 'image_model', e.target.value)} />
              </div>
              <div className="form-group" style={{ flex: 1 }}>
                <label>图片尺寸</label>
                <input className="input" value={settings.ai.glm?.image_size || ''} onChange={e => updateAi('glm', 'image_size', e.target.value)} />
              </div>
            </div>
          </div>
        </div>
      )}

      {activeTab === 'wechat' && (
        <div className="settings-section">
          <div className="settings-group">
            <h3>微信公众号配置</h3>
            <div className="form-group">
              <label>AppID</label>
              <input className="input" placeholder="wx..." value={settings.wechat.app_id} onChange={e => updateWechat('app_id', e.target.value)} />
            </div>
            <div className="form-group">
              <label>作者名</label>
              <input className="input" placeholder="显示在文章上的作者名" value={settings.wechat.author} onChange={e => updateWechat('author', e.target.value)} />
            </div>
            <div className="form-group">
              <label>默认封面图 Media ID</label>
              <input className="input" placeholder="封面图素材ID" value={settings.wechat.default_thumb_media_id} onChange={e => updateWechat('default_thumb_media_id', e.target.value)} />
              <div className="hint">在公众号后台上传封面图后获取的素材ID</div>
            </div>
          </div>
        </div>
      )}

      {activeTab === 'content' && (
        <div className="settings-section">
          <div className="settings-group">
            <h3>文章生成参数</h3>
            <div className="form-row">
              <div className="form-group" style={{ flex: 1 }}>
                <label>最短字数</label>
                <input className="input" type="number" value={settings.content.min_length} onChange={e => updateContent('min_length', parseInt(e.target.value))} />
              </div>
              <div className="form-group" style={{ flex: 1 }}>
                <label>最长字数</label>
                <input className="input" type="number" value={settings.content.max_length} onChange={e => updateContent('max_length', parseInt(e.target.value))} />
              </div>
            </div>
            <div className="form-group">
              <label>去AI味轮数</label>
              <input className="input" type="number" min="0" max="5" value={settings.content.humanize_rounds} onChange={e => updateContent('humanize_rounds', parseInt(e.target.value))} />
              <div className="hint">每轮包含口语化改写+情感注入，轮数越多越自然但耗时更长</div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
