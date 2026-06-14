import React, { useState, useEffect, useRef } from 'react'

interface LogEntry {
  time: string
  level: string
  message: string
  module?: string
}

export default function LogPanel() {
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [collapsed, setCollapsed] = useState(false)
  const [autoScroll, setAutoScroll] = useState(true)
  const endRef = useRef<HTMLDivElement>(null)
  const bodyRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    // 启动时先拉取持久化历史（可回滚查看），再订阅实时流
    fetch('/api/logs')
      .then(r => r.json())
      .then(setLogs)
      .catch(() => {})

    const es = new EventSource('/api/logs/stream')
    es.onmessage = (e) => {
      try {
        const entry: LogEntry = JSON.parse(e.data)
        setLogs(prev => [...prev.slice(-499), entry])
      } catch {}
    }
    es.onerror = () => {}

    return () => es.close()
  }, [])

  useEffect(() => {
    if (!collapsed && autoScroll && endRef.current) {
      endRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [logs, collapsed, autoScroll])

  const handleScroll = () => {
    if (!bodyRef.current) return
    const { scrollTop, scrollHeight, clientHeight } = bodyRef.current
    setAutoScroll(scrollHeight - scrollTop - clientHeight < 40)
  }

  const levelColor: Record<string, string> = {
    DEBUG: '#8e8e93',
    INFO: '#0a84ff',
    WARNING: '#ff9f0a',
    ERROR: '#ff453a',
    SUCCESS: '#30d158',
  }

  return (
    <div className={`log-drawer ${collapsed ? 'collapsed' : 'expanded'}`}>
      <div className="log-header" onClick={() => setCollapsed(c => !c)}>
        <span className="log-title">
          {collapsed ? '▸' : '▾'} 运行日志
          <span className="log-count">{logs.length}</span>
        </span>
        <div className="log-actions" onClick={e => e.stopPropagation()}>
          <span className="log-hint">实时 · 可回滚查看</span>
          <button className="log-toggle" title="清空当前显示" onClick={() => setLogs([])}>清空</button>
        </div>
      </div>
      <div className="log-body" ref={bodyRef} onScroll={handleScroll}>
        {logs.length === 0 ? (
          <div className="log-empty">等待日志输出…</div>
        ) : (
          logs.map((log, i) => (
            <div key={i} className="log-line">
              <span className="log-time">{log.time}</span>
              <span className="log-level" style={{ color: levelColor[log.level] || '#8e8e93' }}>
                {log.level}
              </span>
              <span className="log-msg">{log.message}</span>
            </div>
          ))
        )}
        <div ref={endRef} />
      </div>
    </div>
  )
}
