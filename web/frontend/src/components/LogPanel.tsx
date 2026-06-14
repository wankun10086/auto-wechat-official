import React, { useState, useEffect, useRef } from 'react'

interface LogEntry {
  time: string
  level: string
  message: string
  module: string
}

export default function LogPanel() {
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [expanded, setExpanded] = useState(true)
  const [autoScroll, setAutoScroll] = useState(true)
  const endRef = useRef<HTMLDivElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    fetch('/api/logs')
      .then(r => r.json())
      .then(setLogs)
      .catch(() => {})

    const es = new EventSource('/api/logs/stream')
    es.onmessage = (e) => {
      try {
        const entry: LogEntry = JSON.parse(e.data)
        setLogs(prev => [...prev.slice(-199), entry])
      } catch {}
    }
    es.onerror = () => {}

    return () => es.close()
  }, [])

  useEffect(() => {
    if (autoScroll && endRef.current) {
      endRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [logs, autoScroll])

  const handleScroll = () => {
    if (!containerRef.current) return
    const { scrollTop, scrollHeight, clientHeight } = containerRef.current
    setAutoScroll(scrollHeight - scrollTop - clientHeight < 50)
  }

  const levelColor: Record<string, string> = {
    DEBUG: '#999',
    INFO: '#1890ff',
    WARNING: '#e6a23c',
    ERROR: '#f56c6c',
    SUCCESS: '#07c160',
  }

  return (
    <div className="log-panel">
      <div className="log-header" onClick={() => setExpanded(!expanded)}>
        <span className="log-title">
          {expanded ? '▼' : '▶'} 运行日志
          <span className="log-count">{logs.length}</span>
        </span>
        <span className="log-hint">实时输出，便于调试</span>
      </div>
      {expanded && (
        <>
          <div className="log-body" ref={containerRef} onScroll={handleScroll}>
            {logs.length === 0 ? (
              <div className="log-empty">等待日志输出...</div>
            ) : (
              logs.map((log, i) => (
                <div key={i} className="log-line">
                  <span className="log-time">{log.time}</span>
                  <span className="log-level" style={{ color: levelColor[log.level] || '#999' }}>
                    {log.level}
                  </span>
                  <span className="log-msg">{log.message}</span>
                </div>
              ))
            )}
            <div ref={endRef} />
          </div>
          <div className="log-footer">
            <label className="log-auto-scroll">
              <input
                type="checkbox"
                checked={autoScroll}
                onChange={e => setAutoScroll(e.target.checked)}
              />
              自动滚动
            </label>
            <button className="btn btn-sm" onClick={() => setLogs([])}>清空</button>
          </div>
        </>
      )}
    </div>
  )
}
