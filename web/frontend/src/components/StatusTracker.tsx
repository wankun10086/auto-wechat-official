import React, { useState, useEffect, useRef } from 'react'
import { getTask } from '../api'

interface Props {
  taskId: string
  onDone: (articleId: number) => void
  onError: (msg: string) => void
}

export default function StatusTracker({ taskId, onDone, onError }: Props) {
  const [progress, setProgress] = useState(0)
  const [message, setMessage] = useState('准备中...')
  const [status, setStatus] = useState('processing')
  const timerRef = useRef<number | null>(null)

  useEffect(() => {
    const poll = async () => {
      try {
        const task = await getTask(taskId)
        setProgress(task.progress)
        setMessage(task.message || '处理中...')
        setStatus(task.status)

        if (task.status === 'completed' || task.status === 'done') {
          if (timerRef.current) clearInterval(timerRef.current)
          if (task.article_id) {
            onDone(task.article_id)
          }
        } else if (task.status === 'failed') {
          if (timerRef.current) clearInterval(timerRef.current)
          onError(task.message || '生成失败')
        }
      } catch {
        onError('查询任务状态失败')
        if (timerRef.current) clearInterval(timerRef.current)
      }
    }

    poll()
    timerRef.current = window.setInterval(poll, 2000)

    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [taskId])

  const isFailed = status === 'failed'

  return (
    <div className="card">
      <div className="card-title">生成进度</div>

      <div className="progress-bar-container">
        <div
          className={`progress-bar ${isFailed ? 'failed' : ''}`}
          style={{ width: `${isFailed ? 100 : progress}%` }}
        />
      </div>

      <div className="progress-text">
        <span>{message}</span>
        <span>{progress}%</span>
      </div>

      {isFailed && (
        <div className="progress-message failed-msg">
          生成失败: {message}
        </div>
      )}

      {!isFailed && status === 'processing' && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 12 }}>
          <span className="loading-spinner" />
          <span className="progress-message">{message}</span>
        </div>
      )}
    </div>
  )
}
