const BASE = ''

export interface GenerateParams {
  url: string
  topic?: string
  source_type?: 'url' | 'file' | 'topic'
  model?: string
  style: string
  prompt: string
  screenshot: string
  no_images: boolean
  publish: boolean
}

export interface UploadResult {
  path: string
  name: string
  size: number
}

export interface TaskStatus {
  task_id: string
  status: string
  progress: number
  message: string
  article_id?: number
}

export interface ArticleItem {
  id: number
  title: string
  status: string
  ai_score: number
  digest: string
  created_at: string
  topic: string
  model: string
}

export interface ArticleDetail {
  id: number
  title: string
  content: string
  raw_content: string
  digest: string
  author: string
  topic: string
  ai_score: number
  status: string
  media_id: string
  created_at: string
  published_at?: string
}

export interface ModelInfo {
  name: string
  model: string
  has_key: boolean
  supports_image: boolean
  is_current: boolean
}

export async function generate(params: GenerateParams): Promise<{task_id: string}> {
  const res = await fetch(`${BASE}/api/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  })
  return res.json()
}

export async function uploadFile(file: File): Promise<UploadResult> {
  const content = await new Promise<string>((resolve, reject) => {
    const r = new FileReader()
    r.onload = () => {
      const s = r.result as string
      const i = s.indexOf(',')
      resolve(i >= 0 ? s.slice(i + 1) : s)
    }
    r.onerror = () => reject(new Error('读取文件失败'))
    r.readAsDataURL(file)
  })
  const res = await fetch(`${BASE}/api/upload`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: file.name, content }),
  })
  if (!res.ok) {
    const d = await res.json().catch(() => ({}))
    throw new Error(d.detail || '上传失败')
  }
  return res.json()
}

export async function getTask(taskId: string): Promise<TaskStatus> {
  const res = await fetch(`${BASE}/api/tasks/${taskId}`)
  return res.json()
}

export async function getArticles(): Promise<ArticleItem[]> {
  const res = await fetch(`${BASE}/api/articles`)
  return res.json()
}

export async function getArticle(id: number): Promise<ArticleDetail> {
  const res = await fetch(`${BASE}/api/articles/${id}`)
  return res.json()
}

export async function publishArticle(id: number): Promise<{success: boolean; message: string}> {
  const res = await fetch(`${BASE}/api/articles/${id}/publish`, { method: 'POST' })
  return res.json()
}

export async function getModels(): Promise<ModelInfo[]> {
  const res = await fetch(`${BASE}/api/models`)
  return res.json()
}

export interface SettingsData {
  ai: {
    provider: string
    deepseek: { api_key?: string; api_key_set?: boolean; base_url?: string; model?: string }
    kimi: { api_key?: string; api_key_set?: boolean; base_url?: string; model?: string }
    minimax: { api_key?: string; api_key_set?: boolean; base_url?: string; model?: string; image_model?: string }
    glm: { api_key?: string; api_key_set?: boolean; base_url?: string; model?: string; image_model?: string; image_size?: string }
    temperature: number
    max_tokens: number
  }
  wechat: {
    app_id: string
    author: string
    default_thumb_media_id: string
  }
  content: {
    min_length: number
    max_length: number
    humanize_rounds: number
  }
}

export async function getSettings(): Promise<SettingsData> {
  const res = await fetch(`${BASE}/api/settings`)
  return res.json()
}

export async function updateSettings(data: Partial<SettingsData>): Promise<{success: boolean; message: string}> {
  const res = await fetch(`${BASE}/api/settings`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  return res.json()
}
