import { useEffect, useRef, useState } from 'react'
import Markdown from './markdown'
import { apiFetch } from './api'

interface InterviewExamProps {
  apiBase: string
  authHeaders: () => Record<string, string>
  modelProvider: string
  isDark: boolean
  onExit: () => void
  onToast: (msg: string) => void
}

interface QAPair {
  question: string
  answer: string
  feedback: string
}

const QUESTION_OPTIONS = [5, 10, 15]

export default function InterviewExam({ apiBase, authHeaders, modelProvider, isDark, onExit, onToast }: InterviewExamProps) {
  // ── 考试状态 ──
  const [phase, setPhase] = useState<'setup' | 'running' | 'finished'>('setup')
  const [topic, setTopic] = useState('')
  const [totalQuestions, setTotalQuestions] = useState(10)
  const [sessionId, setSessionId] = useState('')
  const [currentQuestion, setCurrentQuestion] = useState('')
  const [answer, setAnswer] = useState('')
  const [qaList, setQaList] = useState<QAPair[]>([])
  const [lastFeedback, setLastFeedback] = useState('')
  const [loading, setLoading] = useState(false)
  const [finishing, setFinishing] = useState(false)
  const [savedPath, setSavedPath] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (bottomRef.current) bottomRef.current.scrollIntoView({ behavior: 'smooth' })
  }, [lastFeedback, currentQuestion])

  // ── 创建独立面试会话（与工作台隔离）──
  const createSession = async () => {
    try {
      const res = await apiFetch(`${apiBase}/user/sessions`, { method: 'POST', headers: authHeaders() })
      if (res.ok) {
        const data = await res.json()
        setSessionId(data.session_id)
        return data.session_id
      }
    } catch {}
    return `iv_${Date.now()}`
  }

  // ── 开始面试：创建会话 + 发送主题 → 第一题 ──
  const startInterview = async () => {
    const t = topic.trim()
    if (!t) { onToast('请输入面试主题，如「Python 并发」'); return }
    setLoading(true)
    try {
      const sid = await createSession()
      const res = await apiFetch(`${apiBase}/chat`, {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({ message: t, session_id: sid, model_provider: modelProvider, mode: 'interview' }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setCurrentQuestion(data.reply || '（未获取到题目）')
      setPhase('running')
    } catch (e: any) {
      onToast(`开始面试失败：${e.message}`)
    } finally {
      setLoading(false)
    }
  }

  // ── 提交回答 → 点评 + 下一题 ──
  const submitAnswer = async () => {
    const a = answer.trim()
    if (!a) { onToast('请先填写回答'); return }
    if (loading) return
    setLoading(true)
    const q = currentQuestion
    try {
      const res = await apiFetch(`${apiBase}/chat`, {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({ message: a, session_id: sessionId, model_provider: modelProvider, mode: 'interview' }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      const feedback = data.reply || '（未获取到点评）'

      // 记录本轮问答（当前题 + 回答 + 点评）
      const newQA = [...qaList, { question: q, answer: a, feedback }]
      setQaList(newQA)
      setLastFeedback(feedback)
      setAnswer('')

      // 下一题：从点评里取（点评最后通常带下一题）
      // 简单处理：把点评作为"反馈 + 下一题"整体展示，下一题由 LLM 出在点评末尾
      setCurrentQuestion(feedback)

      // 答满 N 题 → 自动结束
      if (newQA.length >= totalQuestions) {
        await finishInterview(sessionId)
      }
    } catch (e: any) {
      onToast(`提交失败：${e.message}`)
    } finally {
      setLoading(false)
    }
  }

  // ── 结束面试：保存到 Obsidian ──
  const finishInterview = async (sid: string = sessionId) => {
    if (finishing) return
    setFinishing(true)
    try {
      const res = await apiFetch(`${apiBase}/interview/finish`, {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({ session_id: sid }),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.detail || '保存失败')
      }
      const data = await res.json()
      setSavedPath(data.path || '')
      setPhase('finished')
      onToast(data.has_weakness ? '已保存面试记录（含薄弱点分析）' : '已保存面试记录')
    } catch (e: any) {
      onToast(`保存失败：${e.message}`)
    } finally {
      setFinishing(false)
    }
  }

  const restart = () => {
    setPhase('setup')
    setTopic('')
    setCurrentQuestion('')
    setAnswer('')
    setQaList([])
    setLastFeedback('')
    setSavedPath('')
    setSessionId('')
  }

  // ── 样式工具 ──
  const cardCls = `rounded-2xl border p-5 ${isDark ? 'bg-gray-900 border-gray-700' : 'bg-white border-gray-200'} shadow-sm`
  const inputCls = `w-full rounded-xl border px-4 py-3 text-sm outline-none transition ${
    isDark
      ? 'bg-gray-800 border-gray-600 text-gray-100 focus:border-purple-400'
      : 'bg-white border-gray-300 text-gray-800 focus:border-purple-500'
  }`
  const btnPrimary = 'rounded-xl bg-purple-600 hover:bg-purple-500 text-white px-6 py-2.5 text-sm font-medium transition cursor-pointer disabled:opacity-50'
  const btnGhost = `rounded-xl border px-4 py-2 text-sm transition cursor-pointer ${
    isDark ? 'border-gray-600 text-gray-300 hover:bg-gray-800' : 'border-gray-300 text-gray-600 hover:bg-gray-100'
  }`

  // ═══════════ 设置页：输入主题 + 选题数 ═══════════
  if (phase === 'setup') {
    return (
      <div className="flex-1 flex flex-col overflow-y-auto px-4 py-10">
        <div className="max-w-xl mx-auto w-full space-y-6">
          <div className="text-center">
            <p className="text-5xl mb-3">🎯</p>
            <h2 className="text-2xl font-bold">模拟面试</h2>
            <p className={`text-sm mt-2 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
              基于你的 Obsidian 疑难总结出题，一题一答，结束自动总结到知识库
            </p>
          </div>

          <div className={cardCls}>
            <label className={`block text-sm font-medium mb-2 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
              面试主题
            </label>
            <input
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) startInterview() }}
              placeholder="如：Python 并发、面向对象、RAG..."
              className={inputCls}
              autoFocus
            />

            <div className="mt-4">
              <label className={`block text-sm font-medium mb-2 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                题目数量
              </label>
              <div className="flex gap-2">
                {QUESTION_OPTIONS.map((n) => (
                  <button
                    key={n}
                    onClick={() => setTotalQuestions(n)}
                    className={`flex-1 rounded-xl border py-2 text-sm transition cursor-pointer ${
                      totalQuestions === n
                        ? 'bg-purple-600 border-purple-600 text-white'
                        : isDark ? 'border-gray-600 text-gray-300 hover:bg-gray-800' : 'border-gray-300 text-gray-600 hover:bg-gray-100'
                    }`}
                  >
                    {n} 题
                  </button>
                ))}
              </div>
            </div>

            <div className="mt-6 flex justify-end gap-3">
              <button onClick={onExit} className={btnGhost}>返回入口</button>
              <button onClick={startInterview} disabled={loading || !topic.trim()} className={btnPrimary}>
                {loading ? '出题中...' : '开始面试'}
              </button>
            </div>
          </div>
        </div>
      </div>
    )
  }

  // ═══════════ 考试页 ═══════════
  if (phase === 'running') {
    const progress = Math.min(qaList.length / totalQuestions, 1) * 100
    return (
      <div className="flex-1 flex flex-col overflow-y-auto px-4 py-6">
        <div className="max-w-2xl mx-auto w-full space-y-4">
          {/* 顶栏：进度 + 结束 */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3 flex-1">
              <span className={`text-sm font-medium ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                第 {Math.min(qaList.length + 1, totalQuestions)} / {totalQuestions} 题
              </span>
              <div className={`flex-1 h-2 rounded-full overflow-hidden ${isDark ? 'bg-gray-800' : 'bg-gray-200'}`}>
                <div className="h-full bg-purple-500 rounded-full transition-all duration-500" style={{ width: `${progress}%` }} />
              </div>
            </div>
            <button
              onClick={() => finishInterview()}
              disabled={finishing || qaList.length === 0}
              className="ml-4 rounded-xl border border-purple-400 text-purple-500 hover:bg-purple-50 dark:hover:bg-purple-900/30 px-4 py-1.5 text-sm transition cursor-pointer disabled:opacity-40 shrink-0"
              title={qaList.length === 0 ? '至少回答一题后才能结束' : '结束并保存到 Obsidian'}
            >
              {finishing ? '保存中...' : '结束面试'}
            </button>
          </div>

          {/* 上题点评（可折叠展示，只显示上一题） */}
          {lastFeedback && (
            <div className={`rounded-2xl border p-5 ${isDark ? 'bg-purple-950/40 border-purple-800/40' : 'bg-purple-50 border-purple-200'}`}>
              <p className={`text-xs font-medium mb-2 ${isDark ? 'text-purple-300' : 'text-purple-600'}`}>📋 上题点评</p>
              <div className={`markdown-body text-sm ${isDark ? 'text-gray-200' : 'text-gray-700'}`}>
                <Markdown content={lastFeedback} />
              </div>
            </div>
          )}

          {/* 当前题目卡片 */}
          <div className={cardCls}>
            <p className={`text-xs font-medium mb-3 ${isDark ? 'text-purple-300' : 'text-purple-600'}`}>❓ 当前题目</p>
            <div className={`markdown-body text-base ${isDark ? 'text-gray-100' : 'text-gray-800'}`}>
              <Markdown content={currentQuestion} />
            </div>
          </div>

          {/* 回答输入 */}
          <div className={cardCls}>
            <label className={`block text-sm font-medium mb-2 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
              我的回答
            </label>
            <textarea
              value={answer}
              onChange={(e) => setAnswer(e.target.value)}
              placeholder="在这里输入你的回答..."
              rows={4}
              className={`${inputCls} resize-none`}
            />
            <div className="mt-3 flex justify-end">
              <button onClick={submitAnswer} disabled={loading || !answer.trim()} className={btnPrimary}>
                {loading ? '点评中...' : '提交回答'}
              </button>
            </div>
          </div>

          <div ref={bottomRef} />
        </div>
      </div>
    )
  }

  // ═══════════ 完成页 ═══════════
  return (
    <div className="flex-1 flex flex-col overflow-y-auto px-4 py-10">
      <div className="max-w-xl mx-auto w-full space-y-6">
        <div className={`${cardCls} text-center py-10`}>
          <p className="text-5xl mb-3">🎉</p>
          <h2 className="text-xl font-bold">面试完成</h2>
          <p className={`text-sm mt-2 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
            共完成 {qaList.length} 道题，记录已自动总结保存到 Obsidian
          </p>
          {savedPath && (
            <p className={`mt-3 text-sm font-mono ${isDark ? 'text-purple-300' : 'text-purple-600'}`}>
              📁 {savedPath}
            </p>
          )}
          <div className="mt-6 flex justify-center gap-3">
            <button onClick={restart} className={btnPrimary}>再来一场</button>
            <button onClick={onExit} className={btnGhost}>返回入口</button>
          </div>
        </div>
      </div>
    </div>
  )
}
