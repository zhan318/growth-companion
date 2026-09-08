import { useState, useRef, useEffect } from 'react'
import InterviewExam from './InterviewExam'
import Markdown from './markdown'
import Toast from './Toast'
import Button from './Button'
import { apiFetch } from './api'

interface Message {
  role: 'user' | 'assistant'
  content: string
}

// MBTI 16 型一句话描述
const MBTI_DESC: Record<string, string> = {
  ISTJ: '务实可靠，讲规则重承诺，天生的执行者',
  ISFJ: '温和细心，默默守护，照顾他人感受',
  INFJ: '理想主义，洞察人心，追求深层的意义',
  INTJ: '独立理性，战略思维，目标感极强的规划者',
  ISTP: '冷静灵活，动手能力强，喜欢研究事物原理',
  ISFP: '安静敏感，活在当下，用行动而非言语表达',
  INFP: '理想化，忠于内心价值观，想象力丰富',
  INTP: '逻辑严密，好奇钻研，热爱抽象与理论',
  ESTP: '精力充沛，反应快，享受刺激与实战',
  ESFP: '热情开朗，活在当下，天生的气氛担当',
  ENFP: '热情有感染力，充满创意，渴望可能性',
  ENTP: '机敏善辩，点子多，喜欢挑战常规',
  ESTJ: '果断高效，组织力强，天生的管理者',
  ESFJ: '热心尽责，善于协调，重视人际关系和谐',
  ENFJ: '富有感染力，乐于助人，天生的领导者',
  ENTJ: '强势果决，远见卓识，天生的统帅',
}

// ── 中央 welcome 页 3 个模式胶囊 ──
const MODE_PILLS: Record<'workspace' | 'interview' | 'knowledge', { icon: string; label: string; subtitle: string }> = {
  workspace: { icon: '💬', label: '日常对话',  subtitle: '问答、工具调用、查天气算数学' },
  interview: { icon: '🎯', label: '模拟面试',  subtitle: '考试式出题，听你回答再给反馈' },
  knowledge: { icon: '📚', label: '知识库',    subtitle: '优先引用 Obsidian 笔记回答' },
}

function App() {
  // ── 认证状态 ──
  const [token, setToken] = useState(() => localStorage.getItem('token') || '')
  const [sessionId, setSessionId] = useState(() => localStorage.getItem('session_id') || '')
  const [userId, setUserId] = useState(() => Number(localStorage.getItem('user_id') || '0'))
  const [username, setUsername] = useState(() => localStorage.getItem('username') || '')
  const [page, setPage] = useState<'auth' | 'hub' | 'chat' | 'profile' | 'mbti' | 'dashboard'>(token ? 'hub' : 'auth')

  // ── 聊天状态 ──
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [historyLoading, setHistoryLoading] = useState(false)
  const [modelProvider, setModelProvider] = useState('deepseek')
  const [isDark, setIsDark] = useState(false)
  const [toast, setToast] = useState('')
  // 各模型是否真正配置密钥（false = 选中后将用 DeepSeek 兜底）
  const [modelEffective, setModelEffective] = useState<Record<string, boolean>>({})
  const bottomRef = useRef<HTMLDivElement>(null)

  // ── 认证表单状态 ──
  const [authMode, setAuthMode] = useState<'login' | 'register'>('login')
  const [authUser, setAuthUser] = useState('')
  const [authEmail, setAuthEmail] = useState('')
  const [authPass, setAuthPass] = useState('')
  const [authPass2, setAuthPass2] = useState('')
  const [showPass, setShowPass] = useState(false)
  const [showPass2, setShowPass2] = useState(false)
  const [profileInfo, setProfileInfo] = useState<any>(null)
  const [profileName, setProfileName] = useState('')
  const [pwdOld, setPwdOld] = useState('')
  const [pwdNew, setPwdNew] = useState('')
  const [pwdNew2, setPwdNew2] = useState('')
  const [profileMsg, setProfileMsg] = useState({ type: '', text: '' })
  const [sessions, setSessions] = useState<any[]>([])
  const [showSidebar, setShowSidebar] = useState(true)
  // 会话三点菜单：哪个会话的菜单打开 / 哪个会话在内联改标题 / 编辑中的标题值
  const [menuFor, setMenuFor] = useState<string | null>(null)
  const [editingFor, setEditingFor] = useState<string | null>(null)
  const [editingTitle, setEditingTitle] = useState('')
  const [authError, setAuthError] = useState('')
  const [authLoading, setAuthLoading] = useState(false)
  // 工作模式：工作台｜模拟面试｜知识库（knowledge 走 hint 注入，后端 mode 仍映射为 workspace）
  const [chatMode, setChatMode] = useState<'workspace' | 'interview' | 'knowledge'>('workspace')
  // 输入区「回答风格偏好 chip」状态：3 个开关（默认：知识库开、其他关）
  const [toolChips, setToolChips] = useState<{ deepThink: boolean; webSearch: boolean; knowledgeBase: boolean }>({
    deepThink: false, webSearch: false, knowledgeBase: true,
  })
  // 右上头像菜单开合
  const [userMenuOpen, setUserMenuOpen] = useState(false)
  // MBTI 测试状态
  const [mbtiStep, setMbtiStep] = useState(0)
  const [mbtiRole, setMbtiRole] = useState('')
  const [mbtiQuestions, setMbtiQuestions] = useState<any[]>([])
  const [mbtiAnswers, setMbtiAnswers] = useState<number[]>([])
  const [mbtiIdx, setMbtiIdx] = useState(0)
  const [mbtiLoading, setMbtiLoading] = useState(false)
  const [mbtiResult, setMbtiResult] = useState<any>(null)
  const [mbtiError, setMbtiError] = useState('')
  const [mbtiHistory, setMbtiHistory] = useState<any[]>([])
  const [exportingMbti, setExportingMbti] = useState(false)
  // 数据看板状态
  const [dashboardStats, setDashboardStats] = useState<any>(null)
  const [dashboardLoading, setDashboardLoading] = useState(false)
  // 面试记录保存状态
  const [savingInterview, setSavingInterview] = useState(false)
  const [buildingWeakness, setBuildingWeakness] = useState(false)
  // 用户级 LLM 密钥（前端切换器用）
  const [configuredProviders, setConfiguredProviders] = useState<string[]>([])
  const [showKeySettings, setShowKeySettings] = useState(false)
  const [keyDrafts, setKeyDrafts] = useState<Record<string, string>>({})
  const [keySaving, setKeySaving] = useState(false)

  const apiBase = import.meta.env.VITE_API_URL || ''

  // 保存认证信息到 localStorage
  const saveAuth = (t: string, sid: string, uid: number, uname: string) => {
    setToken(t); setSessionId(sid); setUserId(uid); setUsername(uname)
    localStorage.setItem('token', t)
    localStorage.setItem('session_id', sid)
    localStorage.setItem('user_id', String(uid))
    localStorage.setItem('username', uname)
  }

  const clearAuth = () => {
    setToken(''); setSessionId(''); setUserId(0); setUsername('')
    localStorage.removeItem('token')
    localStorage.removeItem('session_id')
    localStorage.removeItem('user_id')
    localStorage.removeItem('username')
    setPage('auth')
    setMessages([])
  }

  // ── 模型信息 ──
  const MODEL_INFO: Record<string, { label: string; role: string; scene: string }> = {
    deepseek: { label: 'DeepSeek', role: '通用助手', scene: '日常对话、问答、工具调用' },
    glm: { label: '智谱 GLM', role: '创意写作', scene: '写文章、文案、翻译、故事' },
    qwen: { label: '通义千问', role: '逻辑分析', scene: '推理、代码、数学、技术问题' },
    yi: { label: '零一万物', role: '头脑风暴', scene: '灵感发散、快速生成、脑洞' },
  }

  useEffect(() => {
    if (!toast) return
    const timer = setTimeout(() => setToast(''), 2000)
    return () => clearTimeout(timer)
  }, [toast])

  // GitHub OAuth 回调：URL 带 github_token 时自动登录
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const ghToken = params.get('github_token')
    if (!ghToken) return
    // 清除 URL 中的 token
    window.history.replaceState({}, '', window.location.pathname)
    // 用 GitHub token 作为认证 token
    saveAuth(ghToken, '', 0, '')
    setPage('hub')
    // 前端会通过 token 自动获取用户信息和会话列表
  }, [])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  // ── 认证操作 ──
  const authHeaders = (): Record<string, string> => ({
    'Content-Type': 'application/json',
    ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
  })

  const handleAuth = async (e: React.FormEvent) => {
    e.preventDefault()
    setAuthError('')

    if (authMode === 'register') {
      if (!authUser.trim() || !authEmail.trim() || !authPass) {
        setAuthError('请填写所有字段'); return
      }
      if (authPass.length < 6) { setAuthError('密码至少 6 位'); return }
      if (authPass !== authPass2) { setAuthError('两次密码不一致'); return }
    } else {
      if (!authUser.trim() || !authPass) { setAuthError('请填写用户名和密码'); return }
    }

    setAuthLoading(true)
    try {
      const endpoint = authMode === 'login' ? '/auth/login' : '/auth/register'
      const body: any = { username: authUser.trim(), password: authPass }
      if (authMode === 'register') body.email = authEmail.trim()

      const res = await apiFetch(`${apiBase}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      // 先读成文本，再尝试 JSON 解析，防止后端返回 HTML 时崩溃
      const text = await res.text()
      let data: any
      try { data = JSON.parse(text) } catch { throw new Error('服务器返回了意外的响应，请检查后端是否已启动') }
      if (!res.ok) { setAuthError(data.error?.detail || data.detail || '操作失败'); return }

      saveAuth(data.token, data.session_id, data.user_id, authUser.trim())
      setPage('hub')
    } catch (e: any) {
      setAuthError(e.message || '网络错误')
    } finally {
      setAuthLoading(false)
    }
  }

  const handleLogout = async () => {
    try {
      await apiFetch(`${apiBase}/auth/logout`, {
        method: 'POST',
        headers: authHeaders(),
      })
    } catch { /* ignore */ }
    clearAuth()
  }

  // ── MBTI 测试操作 ──
  const startMbti = async () => {
    if (!mbtiRole.trim()) { setMbtiError('请先输入你的理想岗位'); return }
    setMbtiError('')
    setMbtiLoading(true)
    try {
      const res = await apiFetch(`${apiBase}/mbti/questions`, { headers: authHeaders() })
      if (!res.ok) throw new Error(`加载题目失败: HTTP ${res.status}`)
      const data = await res.json()
      setMbtiQuestions(data.questions || [])
      setMbtiAnswers([])
      setMbtiIdx(0)
      setMbtiResult(null)
      setMbtiStep(1)
    } catch (e: any) {
      setMbtiError(e.message || '加载题目失败')
    } finally {
      setMbtiLoading(false)
    }
  }

  const answerMbti = async (optIdx: number) => {
    const newAnswers = [...mbtiAnswers]
    newAnswers[mbtiIdx] = optIdx
    setMbtiAnswers(newAnswers)

    // 最后一题 → 提交
    if (mbtiIdx >= mbtiQuestions.length - 1) {
      await submitMbti(newAnswers)
    } else {
      setMbtiIdx(mbtiIdx + 1)
    }
  }

  const submitMbti = async (answers: number[]) => {
    setMbtiLoading(true)
    setMbtiError('')
    try {
      // 题库是随机顺序返回的，提交前按题目 id 升序重排，保证与后端固定题库对应
      const byId = mbtiQuestions
        .map((q, i) => ({ id: q.id, ans: answers[i] }))
        .sort((a: any, b: any) => a.id - b.id)
      const sortedAnswers = byId.map((x: any) => x.ans)

      const res = await apiFetch(`${apiBase}/mbti/analyze`, {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({ ideal_role: mbtiRole, answers: sortedAnswers }),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.detail || `分析失败: HTTP ${res.status}`)
      }
      const data = await res.json()
      setMbtiResult(data)
      setMbtiStep(2)
      // 拉取历史（结果页展示类型稳定性）
      try {
        const hres = await apiFetch(`${apiBase}/mbti/history`, { headers: authHeaders() })
        if (hres.ok) {
          const hdata = await hres.json()
          setMbtiHistory(hdata.history || [])
        }
      } catch { /* 历史拉取失败不影响结果展示 */ }
    } catch (e: any) {
      setMbtiError(e.message || '分析失败，请重试')
      setMbtiStep(1)
    } finally {
      setMbtiLoading(false)
    }
  }

  const resetMbti = () => {
    setMbtiStep(0)
    setMbtiRole('')
    setMbtiQuestions([])
    setMbtiAnswers([])
    setMbtiIdx(0)
    setMbtiResult(null)
    setMbtiError('')
  }

  // ── MBTI 档案导出 ──
  const exportMbti = async () => {
    setExportingMbti(true)
    try {
      const res = await apiFetch(`${apiBase}/mbti/export`, {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({
          mbti: mbtiResult.mbti,
          ideal_role: mbtiRole,
          analysis: mbtiResult.analysis || '',
          scores: mbtiResult.scores || {},
        }),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.detail || '导出失败')
      }
      const data = await res.json()
      setToast(`已导出档案：${data.path}`)
    } catch (e: any) {
      setToast(e.message || '导出失败')
    } finally {
      setExportingMbti(false)
    }
  }

  // ── 数据看板 ──
  const fetchDashboard = async () => {
    setDashboardLoading(true)
    try {
      const res = await apiFetch(`${apiBase}/dashboard/stats`, { headers: authHeaders() })
      if (!res.ok) throw new Error(`加载失败 (HTTP ${res.status})`)
      const data = await res.json()
      setDashboardStats(data)
      setToast('已更新')
    } catch (e: any) {
      // 失败时填默认值（不 null），UI 至少能显示 0，不变全貌空白
      setDashboardStats((prev: any) => prev || {
        notes_count: 0, interview_count: 0, mbti_count: 0, session_count: 0, mbti_history: [],
      })
      setToast(e?.message || '加载失败')
    } finally {
      setDashboardLoading(false)
    }
  }

  // ── 面试记录归档 ──
  const handleSaveInterview = async () => {
    setSavingInterview(true)
    try {
      const res = await apiFetch(`${apiBase}/interview/save`, {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({ session_id: sessionId }),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.detail || '保存失败')
      }
      const data = await res.json()
      setToast(`已保存到 Obsidian：${data.path}`)
    } catch (e: any) {
      setToast(e.message || '保存失败')
    } finally {
      setSavingInterview(false)
    }
  }

  // ── 薄弱点画像 ──
  const handleWeaknessProfile = async () => {
    setBuildingWeakness(true)
    try {
      const res = await apiFetch(`${apiBase}/interview/weakness`, {
        method: 'POST',
        headers: authHeaders(),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.detail || '生成失败')
      }
      const data = await res.json()
      setToast(`已生成画像（基于 ${data.record_count} 份记录）：${data.path}`)
    } catch (e: any) {
      setToast(e.message || '生成失败')
    } finally {
      setBuildingWeakness(false)
    }
  }

  // ── 一键存为 Obsidian 笔记 ──
  const saveAsNote = async (content: string) => {
    try {
      const res = await apiFetch(`${apiBase}/notes/save`, {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({ content }),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.detail || '保存失败')
      }
      const data = await res.json()
      setToast(`已存为笔记：${data.path}`)
    } catch (e: any) {
      setToast(e.message || '保存失败')
    }
  }

  // 切换账号：不清除 token，让登录页可以返回聊天
  const switchUser = () => {
    setPage('auth')
    setMessages([])
  }

  // ── 个人主页操作 ──
  const fetchProfile = async () => {
    try {
      const res = await apiFetch(`${apiBase}/user/profile`, { headers: authHeaders() })
      if (!res.ok) throw new Error('获取信息失败')
      const data = await res.json()
      setProfileInfo(data)
      setProfileName(data.display_name || '')
    } catch (e: any) {
      setProfileMsg({ type: 'error', text: e.message })
    }
  }

  const handleUpdateName = async (e: React.FormEvent) => {
    e.preventDefault()
    setProfileMsg({ type: '', text: '' })
    try {
      const res = await apiFetch(`${apiBase}/user/profile`, {
        method: 'PUT',
        headers: authHeaders(),
        body: JSON.stringify({ display_name: profileName.trim() }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || '修改失败')
      setProfileInfo((prev: any) => prev ? { ...prev, display_name: profileName.trim() } : prev)
      setProfileMsg({ type: 'success', text: data.message })
    } catch (e: any) {
      setProfileMsg({ type: 'error', text: e.message })
    }
  }

  const handleUpdatePwd = async (e: React.FormEvent) => {
    e.preventDefault()
    setProfileMsg({ type: '', text: '' })
    if (pwdNew.length < 6) { setProfileMsg({ type: 'error', text: '新密码至少 6 位' }); return }
    if (pwdNew !== pwdNew2) { setProfileMsg({ type: 'error', text: '两次密码不一致' }); return }
    try {
      const res = await apiFetch(`${apiBase}/user/password`, {
        method: 'PUT',
        headers: authHeaders(),
        body: JSON.stringify({ old_password: pwdOld, new_password: pwdNew }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || '修改失败')
      setProfileMsg({ type: 'success', text: data.message })
      setPwdOld(''); setPwdNew(''); setPwdNew2('')
    } catch (e: any) {
      setProfileMsg({ type: 'error', text: e.message })
    }
  }

  // ── 会话管理 ──
  const fetchSessions = async () => {
    try {
      const res = await apiFetch(`${apiBase}/user/sessions`, { headers: authHeaders() })
      if (res.ok) {
        const data = await res.json()
        setSessions(data.sessions || [])
      }
    } catch {}
  }

  // 拉取指定会话的历史消息
  const fetchMessages = async (sid: string) => {
    setHistoryLoading(true)
    try {
      const res = await apiFetch(`${apiBase}/user/sessions/${sid}/messages?limit=200`, { headers: authHeaders() })
      if (res.ok) {
        const data = await res.json()
        setMessages(data.messages || [])
      } else if (res.status === 401) {
        clearAuth()
      } else {
        setMessages([])
      }
    } catch {
      setMessages([])
    } finally {
      setHistoryLoading(false)
    }
  }

  const switchSession = async (newId: string) => {
    if (newId === sessionId) return
    setSessionId(newId)
    setMessages([])
    localStorage.setItem('session_id', newId)
    // 移动端自动收起侧边栏
    if (window.innerWidth < 768) setShowSidebar(false)
    await fetchMessages(newId)
  }

  const newSession = async () => {
    try {
      const res = await apiFetch(`${apiBase}/user/sessions`, {
        method: 'POST',
        headers: authHeaders(),
      })
      if (res.ok) {
        const data = await res.json()
        await switchSession(data.session_id)
        await fetchSessions()
      }
    } catch {}
  }

  const deleteSession = async (sid: string) => {
    try {
      const res = await apiFetch(`${apiBase}/user/sessions/${sid}`, {
        method: 'DELETE',
        headers: authHeaders(),
      })
      if (res.ok) {
        if (sid === sessionId) {
          // 如果删除的是当前会话，切换到第一个可用会话
          const remaining = sessions.filter((s: any) => s.session_id !== sid)
          if (remaining.length > 0) {
            await switchSession(remaining[0].session_id)
          }
        }
        await fetchSessions()
      }
    } catch {}
  }

  // ── 会话操作：修改标题 / 保存到笔记 ──
  const renameSession = async (sid: string, label: string) => {
    setEditingFor(null)
    const title = label.trim()
    if (!title) { setToast('标题不能为空'); return }
    try {
      const res = await apiFetch(`${apiBase}/user/sessions/${sid}`, {
        method: 'PATCH',
        headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ label: title }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || '修改失败')
      setSessions((prev: any[]) => prev.map((s) =>
        s.session_id === sid ? { ...s, label: title } : s,
      ))
      setToast('标题已更新')
    } catch (e: any) {
      setToast(e.message || '修改失败')
    }
  }

  const saveSessionToNote = async (sid: string) => {
    setMenuFor(null)
    try {
      const res = await apiFetch(`${apiBase}/notes/save-session`, {
        method: 'POST',
        headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sid }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || '保存失败')
      setToast(`已保存到 Obsidian：${data.path}`)
    } catch (e: any) {
      setToast(e.message || '保存失败')
    }
  }

  // 按创建时间给会话分组（今天 / 7 天内 / 30 天内 / 更早）
  const groupSessions = (list: any[]) => {
    const now = new Date()
    const today = new Date(now); today.setHours(0, 0, 0, 0)
    const d7 = new Date(today); d7.setDate(d7.getDate() - 7)
    const d30 = new Date(today); d30.setDate(d30.getDate() - 30)
    const buckets: Record<string, any[]> = { 今天: [], 七天内: [], 三十天内: [], 更早: [] }
    for (const s of list) {
      const d = new Date(s.created_at)
      if (isNaN(d.getTime())) { buckets.更早.push(s); continue }
      if (d >= today) buckets.今天.push(s)
      else if (d >= d7) buckets.七天内.push(s)
      else if (d >= d30) buckets.三十天内.push(s)
      else buckets.更早.push(s)
    }
    return Object.entries(buckets).filter(([, v]) => v.length > 0)
  }

  // 加载当前用户已配置的模型密钥（用于切换器标记「你的密钥」）
  const fetchLLMKeys = async () => {
    try {
      const res = await apiFetch(`${apiBase}/user/llm-keys`, { headers: authHeaders() })
      if (res.ok) {
        const data = await res.json()
        setConfiguredProviders(data.configured_providers || [])
      }
    } catch {}
  }

  // 拉取各模型「是否真正配置密钥」状态（用于切换器标记兜底 + 切换提示）
  const fetchModels = async () => {
    try {
      const res = await apiFetch(`${apiBase}/models`, { headers: authHeaders() })
      if (res.ok) {
        const data = await res.json()
        const eff: Record<string, boolean> = {}
        for (const m of (data.models || [])) eff[m.id] = !!m.effective
        setModelEffective(eff)
      }
    } catch {}
  }

  // 登录/切换页面时加载会话列表 + 当前会话历史 + 模型密钥配置
  useEffect(() => {
    if (token) {
      fetchSessions()
      if (sessionId) fetchMessages(sessionId)
      fetchLLMKeys()
      fetchModels()
    }
  }, [token])

  // ── 模型密钥设置 ──
  const saveKeys = async () => {
    setKeySaving(true)
    try {
      for (const [provider, apiKey] of Object.entries(keyDrafts)) {
        if (apiKey && apiKey.trim()) {
          await apiFetch(`${apiBase}/user/llm-keys`, {
            method: 'PUT',
            headers: authHeaders(),
            body: JSON.stringify({ provider, api_key: apiKey.trim() }),
          })
        }
      }
      await fetchLLMKeys()
      await fetchModels()
      setKeyDrafts({})
      setShowKeySettings(false)
      setToast('密钥已保存')
    } catch {
      setToast('保存失败，请重试')
    } finally {
      setKeySaving(false)
    }
  }

  const deleteKey = async (provider: string) => {
    try {
      await apiFetch(`${apiBase}/user/llm-keys/${provider}`, { method: 'DELETE', headers: authHeaders() })
      await fetchLLMKeys()
      await fetchModels()
      setToast(`已删除 ${MODEL_INFO[provider]?.label || provider} 的密钥`)
    } catch {
      setToast('删除失败')
    }
  }

  // ── 聊天操作 ──
  // 把"知识库"模式和工具 chip 翻译成 system hint，注入到 message 前面（零后端改动）
  const buildUserMessage = (raw: string): string => {
    const hints: string[] = []
    // 模式胶囊（中央 welcome 选的）→ 强制语义
    if (chatMode === 'knowledge') {
      hints.push('【请基于我的 Obsidian 知识库回答，直接引用笔记内容】')
    } else if (chatMode === 'interview') {
      hints.push('【这是模拟面试模式，按出题→倾听→点评节奏进行】')
    }
    // 工具能力 chip（输入区下方）→ 可叠加
    if (toolChips.deepThink) hints.push('【允许多轮工具调用，逐步推理】')
    if (toolChips.webSearch) hints.push('【允许调用联网搜索获取最新信息】')
    if (toolChips.knowledgeBase) hints.push('【优先检索 Obsidian 知识库】')
    return hints.length ? `${hints.join('\n')}\n\n${raw}` : raw
  }

  // 后端 /chat 接口只接 workspace | interview，knowledge 走 workspace（hint 承担语义）
  const backendMode: 'workspace' | 'interview' = chatMode === 'interview' ? 'interview' : 'workspace'

  const sendMessage = async () => {
    const text = input.trim()
    if (!text || loading) return

    setInput('')
    const finalMessage = buildUserMessage(text)
    // 用户看到的消息仍是原文，hint 仅作为"额外上下文"传后端，不污染 UI
    setMessages((prev) => [
      ...prev,
      { role: 'user', content: text },
      { role: 'assistant', content: '' },
    ])
    setLoading(true)

    try {
      const res = await apiFetch(`${apiBase}/chat`, {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({ message: finalMessage, session_id: sessionId, model_provider: modelProvider, mode: backendMode }),
      })

      if (!res.ok) {
        if (res.status === 401) { clearAuth(); throw new Error('登录已过期，请重新登录') }
        throw new Error(`请求失败: HTTP ${res.status}`)
      }

      const data = await res.json()
      setMessages((prev) => {
        const next = [...prev]
        next[next.length - 1] = { role: 'assistant', content: data.reply || '(未获取到回答)' }
        return next
      })
      // 刷新会话列表（更新预览文字）
      fetchSessions()
    } catch (e: any) {
      setMessages((prev) => {
        const next = [...prev]
        const last = next[next.length - 1]
        if (last?.role === 'assistant' && !last.content) {
          next[next.length - 1] = { role: 'assistant', content: `请求失败：${e.message}` }
        } else {
          next.push({ role: 'assistant', content: `请求失败：${e.message}` })
        }
        return next
      })
    } finally {
      setLoading(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage() }
  }

  // ═══════════════════════════════════════
  //  渲染：登录/注册页
  // ═══════════════════════════════════════
  if (page === 'auth') {
    return (
      <div className="flex items-center justify-center min-h-dvh bg-gray-50 dark:bg-gray-950">
      <Toast message={toast} />
        <div className="w-full max-w-sm mx-4">
          <div className="text-center mb-8">
            <p className="text-5xl mb-3">🧠</p>
            <h1 className="text-2xl font-bold text-gray-800 dark:text-gray-100">智能个人助手</h1>
            <p className="text-sm text-gray-400 mt-1">连接你的 Obsidian 笔记库</p>
          </div>

          {/* 如果已登录（切换账号场景），显示返回聊天按钮 */}
          {token && (
            <div className="text-center mb-2">
        <Button
          variant="secondary"
          size="sm"
          isDark={false}
          onClick={() => setPage('hub')}
          className="text-sm"
        >返回入口</Button>
            </div>
          )}
          <form onSubmit={handleAuth} className="bg-white dark:bg-gray-900 rounded-2xl shadow-sm border border-gray-200 dark:border-gray-800 p-6 space-y-4">
            <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-100">
              {authMode === 'login' ? '登录' : '注册'}
            </h2>

            <input
              type="text" placeholder="用户名" required
              value={authUser} onChange={(e) => setAuthUser(e.target.value)}
              className="w-full rounded-xl border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 px-4 py-2.5 text-sm outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 text-gray-800 dark:text-gray-100 placeholder-gray-400"
            />

            {authMode === 'register' && (
              <input
                type="email" placeholder="邮箱" required
                value={authEmail} onChange={(e) => setAuthEmail(e.target.value)}
                className="w-full rounded-xl border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 px-4 py-2.5 text-sm outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 text-gray-800 dark:text-gray-100 placeholder-gray-400"
              />
            )}

            <div className="relative">
              <input
                type={showPass ? "text" : "password"} placeholder="密码" required
                value={authPass} onChange={(e) => setAuthPass(e.target.value)}
                className="w-full rounded-xl border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 px-4 py-2.5 pr-10 text-sm outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 text-gray-800 dark:text-gray-100 placeholder-gray-400"
              />
              <button type="button" onClick={() => setShowPass(!showPass)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 cursor-pointer text-sm select-none"
                title={showPass ? "隐藏密码" : "显示密码"}
              >
                {showPass ? "😀" : "🙈"}
              </button>
            </div>

            {authMode === 'register' && (
              <div className="relative">
                <input
                  type={showPass2 ? "text" : "password"} placeholder="确认密码" required
                  value={authPass2} onChange={(e) => setAuthPass2(e.target.value)}
                  className="w-full rounded-xl border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 px-4 py-2.5 pr-10 text-sm outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 text-gray-800 dark:text-gray-100 placeholder-gray-400"
                />
                <button type="button" onClick={() => setShowPass2(!showPass2)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 cursor-pointer text-sm select-none"
                  title={showPass2 ? "隐藏密码" : "显示密码"}
                >
                  {showPass2 ? "😀" : "🙈"}
                </button>
              </div>
            )}

            {authError && (
              <p className="text-sm text-red-500">{authError}</p>
            )}

            <button
              type="submit" disabled={authLoading}
              className="w-full rounded-xl bg-blue-600 py-2.5 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-40 transition"
            >
              {authLoading ? '处理中...' : authMode === 'login' ? '登录' : '注册'}
            </button>

            <p className="text-xs text-center text-gray-400">
              {authMode === 'login' ? (
                <>还没有账号？<button type="button" onClick={() => { setAuthMode('register'); setAuthError('') }} className="text-blue-500 hover:underline cursor-pointer">注册</button></>
              ) : (
                <>已有账号？<button type="button" onClick={() => { setAuthMode('login'); setAuthError('') }} className="text-blue-500 hover:underline cursor-pointer">登录</button></>
              )}
            </p>

            {/* GitHub 登录按钮 */}
            <div className="relative pt-3">
              <div className="absolute inset-0 flex items-center"><div className="w-full border-t border-gray-200 dark:border-gray-700"></div></div>
              <div className="relative flex justify-center"><span className="bg-white dark:bg-gray-900 px-2 text-xs text-gray-400">或</span></div>
            </div>
            <a
              href={`${apiBase}/auth/github/login`}
              className="flex items-center justify-center gap-2 w-full rounded-xl bg-gray-800 dark:bg-gray-700 py-2.5 text-sm font-medium text-white hover:bg-gray-700 dark:hover:bg-gray-600 transition cursor-pointer no-underline"
            >
              <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor"><path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/></svg>
              GitHub 登录
            </a>
          </form>
        </div>
      </div>
    )
  }

  // ═══════════════════════════════════════
  //  渲染：功能入口页（hub）
  // ═══════════════════════════════════════
  if (page === 'hub') {
    return (
      <div className="relative flex flex-col min-h-dvh overflow-hidden bg-gradient-to-br from-blue-50 via-white to-purple-50 dark:from-gray-900 dark:via-gray-950 dark:to-gray-900">
      <Toast message={toast} />
        {/* 浮动装饰圆点 */}
        <div className="absolute inset-0 pointer-events-none" aria-hidden="true">
          <div className="hub-blob absolute w-80 h-80 rounded-full bg-blue-200/50 dark:bg-blue-500/10" style={{ top: '6%', left: '8%' }} />
          <div className="hub-blob absolute w-64 h-64 rounded-full bg-purple-200/50 dark:bg-purple-500/10" style={{ bottom: '18%', left: '14%', animationDelay: '1.4s' }} />
          <div className="hub-blob absolute w-72 h-72 rounded-full bg-pink-200/40 dark:bg-pink-500/10" style={{ top: '12%', right: '6%', animationDelay: '0.7s' }} />
          <div className="hub-blob absolute w-48 h-48 rounded-full bg-teal-200/40 dark:bg-teal-500/10" style={{ bottom: '8%', right: '14%', animationDelay: '2.1s' }} />
        </div>

        {/* 顶部工具条 */}
        <header className="relative z-10 shrink-0 flex items-center justify-between px-6 py-4">
          <span className="text-sm font-medium text-gray-700 dark:text-gray-300">智能个人助手</span>
          <div className="flex items-center gap-3 text-xs">
            <span className="text-gray-500 dark:text-gray-400">{username}</span>
            <button onClick={() => { setPage('profile'); setTimeout(fetchProfile, 50) }}
              className="text-gray-500 hover:text-blue-500 dark:text-gray-400 dark:hover:text-blue-400 transition cursor-pointer">个人中心</button>
            <button onClick={() => setIsDark(!isDark)}
              className="text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300 transition cursor-pointer">
              {isDark ? '☀️' : '🌙'}
            </button>
            <button onClick={handleLogout}
              className="text-gray-500 hover:text-red-500 dark:text-gray-400 dark:hover:text-red-400 transition cursor-pointer">退出</button>
          </div>
        </header>

        {/* 欢迎区 */}
        <main className="relative z-10 flex-1 flex flex-col justify-center px-6 md:px-12">
          <div className="hub-fade-up">
            <p className="text-6xl mb-4">🧠</p>
            <h1 className="text-3xl font-bold text-gray-800 dark:text-gray-100">
              欢迎回来，{username || '朋友'}
            </h1>
            <p className="text-gray-500 dark:text-gray-400 mt-2 text-sm">今天想做点什么？选择一个入口开始。</p>
          </div>
        </main>

        {/* 右下角功能入口卡片 */}
        <div className="relative z-10 shrink-0 flex flex-wrap justify-end items-end gap-5 px-6 pb-8 md:px-12">
          <button onClick={() => { setChatMode('workspace'); setMessages([]); setPage('chat') }}
            className="hub-card w-64 md:w-72 rounded-3xl bg-white/90 dark:bg-gray-900/90 backdrop-blur border border-gray-200 dark:border-gray-700 shadow-lg p-6 text-left hover:shadow-2xl hover:border-blue-400 dark:hover:border-blue-500 hover:-translate-y-1.5 transition-all duration-300 cursor-pointer group">
            <div className="flex items-start justify-between">
              <span className="text-4xl transition-transform duration-300 group-hover:scale-110">🧠</span>
              <span className="text-blue-500 opacity-0 group-hover:opacity-100 transition-opacity text-sm">进入 →</span>
            </div>
            <h2 className="mt-4 text-lg font-semibold text-gray-800 dark:text-gray-100">工作台</h2>
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400 leading-relaxed">日常问答 · Obsidian 笔记 · 查天气、算数学、看 AI 热榜、搜网页</p>
          </button>

          <button onClick={() => { setChatMode('interview'); setMessages([]); setPage('chat') }}
            className="hub-card w-64 md:w-72 rounded-3xl bg-white/90 dark:bg-gray-900/90 backdrop-blur border border-gray-200 dark:border-gray-700 shadow-lg p-6 text-left hover:shadow-2xl hover:border-purple-400 dark:hover:border-purple-500 hover:-translate-y-1.5 transition-all duration-300 cursor-pointer group">
            <div className="flex items-start justify-between">
              <span className="text-4xl transition-transform duration-300 group-hover:scale-110">🎯</span>
              <span className="text-purple-500 opacity-0 group-hover:opacity-100 transition-opacity text-sm">进入 →</span>
            </div>
            <h2 className="mt-4 text-lg font-semibold text-gray-800 dark:text-gray-100">模拟面试</h2>
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400 leading-relaxed">考试式答题 · 自动总结到知识库 · 薄弱点分析</p>
          </button>

          <button onClick={() => { setPage('mbti') }}
            className="hub-card w-64 md:w-72 rounded-3xl bg-white/90 dark:bg-gray-900/90 backdrop-blur border border-gray-200 dark:border-gray-700 shadow-lg p-6 text-left hover:shadow-2xl hover:border-teal-400 dark:hover:border-teal-500 hover:-translate-y-1.5 transition-all duration-300 cursor-pointer group">
            <div className="flex items-start justify-between">
              <span className="text-4xl transition-transform duration-300 group-hover:scale-110">🧭</span>
              <span className="text-teal-500 opacity-0 group-hover:opacity-100 transition-opacity text-sm">进入 →</span>
            </div>
            <h2 className="mt-4 text-lg font-semibold text-gray-800 dark:text-gray-100">MBTI 性格测试</h2>
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400 leading-relaxed">输入理想岗位 · 30 道选择题 · 测出你的 MBTI 并分析岗位适配度</p>
          </button>

          <button onClick={() => { setPage('dashboard'); fetchDashboard() }}
            className="hub-card w-64 md:w-72 rounded-3xl bg-white/90 dark:bg-gray-900/90 backdrop-blur border border-gray-200 dark:border-gray-700 shadow-lg p-6 text-left hover:shadow-2xl hover:border-blue-400 dark:hover:border-blue-500 hover:-translate-y-1.5 transition-all duration-300 cursor-pointer group">
            <div className="flex items-start justify-between">
              <span className="text-4xl transition-transform duration-300 group-hover:scale-110">📊</span>
              <span className="text-blue-500 opacity-0 group-hover:opacity-100 transition-opacity text-sm">进入 →</span>
            </div>
            <h2 className="mt-4 text-lg font-semibold text-gray-800 dark:text-gray-100">数据看板</h2>
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400 leading-relaxed">笔记数 · 面试次数 · MBTI 历史，你的学习成长轨迹</p>
          </button>
        </div>
      </div>
    )
  }

  // ═══════════════════════════════════════
  //  渲染：MBTI 性格测试
  // ═══════════════════════════════════════
  if (page === 'mbti') {
    const q = mbtiQuestions[mbtiIdx]
    const progress = mbtiQuestions.length ? Math.round((mbtiIdx / mbtiQuestions.length) * 100) : 0
    return (
      <div className="relative flex flex-col min-h-dvh overflow-hidden bg-gradient-to-br from-teal-50 via-white to-blue-50 dark:from-gray-900 dark:via-gray-950 dark:to-gray-900">
      <Toast message={toast} />
        <div className="absolute inset-0 pointer-events-none" aria-hidden="true">
          <div className="hub-blob absolute w-72 h-72 rounded-full bg-teal-200/40 dark:bg-teal-500/10" style={{ top: '8%', right: '6%' }} />
          <div className="hub-blob absolute w-64 h-64 rounded-full bg-blue-200/40 dark:bg-blue-500/10" style={{ bottom: '12%', left: '8%', animationDelay: '1.6s' }} />
        </div>

        <header className="relative z-10 shrink-0 flex items-center justify-between px-6 py-4">
          <button onClick={() => setPage('hub')}
            className="text-sm text-gray-500 hover:text-blue-500 dark:text-gray-400 dark:hover:text-blue-400 transition cursor-pointer">← 返回入口</button>
          <span className="text-sm font-medium text-gray-700 dark:text-gray-300">MBTI 性格测试</span>
        </header>

        <main className="relative z-10 flex-1 flex flex-col items-center justify-center px-6 pb-10">
          {/* 第 1 步：输入理想岗位 */}
          {mbtiStep === 0 && (
            <div className="w-full max-w-xl text-center hub-fade-up">
              <p className="text-6xl mb-4">🧭</p>
              <h1 className="text-2xl font-bold text-gray-800 dark:text-gray-100">MBTI 性格测试</h1>
              <p className="text-sm text-gray-500 dark:text-gray-400 mt-2 mb-8">
                先告诉我你的理想岗位，测试完成后会分析你的性格与它的适配差异
              </p>
              <input
                value={mbtiRole}
                onChange={(e) => setMbtiRole(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') startMbti() }}
                placeholder="输入理想岗位，如：后端开发 / 产品经理 / 数据分析师"
                className={`w-full rounded-2xl border px-5 py-4 text-lg text-center outline-none focus:border-teal-500 focus:ring-2 focus:ring-teal-500/30 transition ${isDark ? "border-gray-700 bg-gray-900 text-gray-100 placeholder-gray-500" : "border-gray-300 bg-white text-gray-800 placeholder-gray-400"}`}
              />
              {mbtiError && <p className="text-sm text-red-500 mt-3">{mbtiError}</p>}
              <button
                onClick={startMbti}
                disabled={mbtiLoading}
                className="mt-6 px-10 py-3 rounded-2xl bg-teal-600 hover:bg-teal-500 text-white font-medium text-base transition cursor-pointer disabled:opacity-50"
              >{mbtiLoading ? '加载题目中...' : '开始测试 →'}</button>
            </div>
          )}

          {/* 第 2 步：答题 */}
          {mbtiStep === 1 && q && (
            <div className="w-full max-w-2xl hub-fade-up">
              <div className="flex items-center justify-between text-xs text-gray-500 dark:text-gray-400 mb-2">
                <span>第 {mbtiIdx + 1} / {mbtiQuestions.length} 题</span>
                <span>{progress}%</span>
              </div>
              <div className={`h-1.5 rounded-full overflow-hidden mb-8 ${isDark ? "bg-gray-800" : "bg-gray-200"}`}>
                <div className="h-full bg-teal-500 transition-all duration-300" style={{ width: `${progress}%` }} />
              </div>

              <h2 className="text-xl md:text-2xl font-semibold text-gray-800 dark:text-gray-100 text-center mb-8">{q.text}</h2>

              <div className="space-y-4">
                {q.options.map((opt: any, i: number) => (
                  <button
                    key={i}
                    onClick={() => answerMbti(i)}
                    disabled={mbtiLoading}
                    className={`w-full flex items-center gap-4 rounded-2xl border px-5 py-4 text-left transition-all duration-200 cursor-pointer disabled:opacity-60 group ${
                      isDark
                        ? "border-gray-700 bg-gray-900 hover:border-teal-500 hover:bg-gray-800 text-gray-100"
                        : "border-gray-200 bg-white hover:border-teal-500 hover:bg-teal-50/50 text-gray-800"
                    }`}
                  >
                    <span className={`shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium ${isDark ? "bg-gray-800 text-gray-300 group-hover:bg-teal-600 group-hover:text-white" : "bg-gray-100 text-gray-500 group-hover:bg-teal-600 group-hover:text-white"} transition`}>
                      {opt.label}
                    </span>
                    <span className="text-base">{opt.text}</span>
                  </button>
                ))}
              </div>

              <div className="flex justify-between mt-6">
                <button
                  onClick={() => setMbtiIdx(Math.max(0, mbtiIdx - 1))}
                  className={`text-sm px-4 py-2 rounded-xl border transition cursor-pointer ${mbtiIdx === 0 ? "opacity-0 pointer-events-none" : ""} ${isDark ? "border-gray-700 text-gray-400 hover:text-gray-200" : "border-gray-300 text-gray-500 hover:text-gray-700"}`}
                >← 上一题</button>
                <span className="text-xs text-gray-400 self-center">{mbtiLoading ? '分析中...' : '选择后将自动进入下一题'}</span>
              </div>
            </div>
          )}

          {/* 第 3 步：结果 */}
          {mbtiStep === 2 && mbtiResult && (
            <div className="w-full max-w-2xl hub-fade-up">
              <div className={`rounded-3xl border p-8 ${isDark ? "bg-gray-900 border-gray-700" : "bg-white border-gray-200"} shadow-lg`}>
                <p className="text-center text-xs text-gray-400">你的 MBTI 类型</p>
                <p className="text-center text-6xl font-bold text-teal-600 dark:text-teal-400 mt-2 tracking-wider">{mbtiResult.mbti}</p>
                <p className="text-center text-sm text-gray-500 dark:text-gray-400 mt-3">{MBTI_DESC[mbtiResult.mbti] || ''}</p>

                <div className="mt-6 flex justify-center gap-4 text-xs">
                  {Object.entries(mbtiResult.scores || {}).map(([k, v]: any) => (
                    <span key={k} className={`px-2 py-1 rounded ${isDark ? "bg-gray-800 text-gray-300" : "bg-gray-100 text-gray-600"}`}>{k}: {v}</span>
                  ))}
                </div>

                <div className="mt-6 border-t pt-6 border-gray-100 dark:border-gray-800">
                  <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    理想岗位「{mbtiRole}」的适配分析
                  </p>
                  <div className="markdown-body">
                    <Markdown content={mbtiResult.analysis || ''} />
                  </div>
                </div>

                {mbtiHistory.length > 1 && (
                  <div className="mt-6 border-t pt-6 border-gray-100 dark:border-gray-800">
                    <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">历史测试（观察类型稳定性）</p>
                    <div className="space-y-1.5 text-xs text-gray-500 dark:text-gray-400">
                      {mbtiHistory.slice(0, 6).map((h: any, i: number) => (
                        <div key={i} className="flex items-center justify-between">
                          <span className="font-mono">{h.created_at?.slice(0, 16) || ''}</span>
                          <span className={`font-semibold ${h.mbti === mbtiResult.mbti ? "text-teal-600 dark:text-teal-400" : "text-gray-500 dark:text-gray-400"}`}>{h.mbti}</span>
                          <span className="truncate max-w-[40%]">{h.ideal_role || '-'}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                <div className="mt-8 flex flex-wrap justify-center gap-4">
                  <button onClick={resetMbti}
                    className="px-6 py-2.5 rounded-xl bg-teal-600 hover:bg-teal-500 text-white text-sm font-medium transition cursor-pointer">重新测试</button>
                  <button onClick={exportMbti} disabled={exportingMbti}
                    className="px-6 py-2.5 rounded-xl border border-teal-500 text-teal-600 dark:text-teal-400 text-sm font-medium transition cursor-pointer hover:bg-teal-50 dark:hover:bg-teal-900/20 disabled:opacity-50">
                    {exportingMbti ? '导出中...' : '📝 导出档案'}
                  </button>
                  <button onClick={() => setPage('hub')}
                    className={`px-6 py-2.5 rounded-xl border text-sm transition cursor-pointer ${isDark ? "border-gray-700 text-gray-300 hover:text-gray-100" : "border-gray-300 text-gray-600 hover:text-gray-800"}`}>返回入口</button>
                </div>
              </div>
            </div>
          )}

          {mbtiStep === 1 && !q && (
            <p className="text-gray-500">{mbtiLoading ? '加载题目中...' : '题目加载失败，请返回重试'}</p>
          )}
        </main>
      </div>
    )
  }

  // ═══════════════════════════════════════
  //  渲染：数据看板
  // ═══════════════════════════════════════
  if (page === 'dashboard') {
    const stats = dashboardStats
    const cards = [
      { icon: '📚', label: '知识库笔记', value: stats?.notes_count, color: 'text-blue-500' },
      { icon: '🎯', label: '面试记录', value: stats?.interview_count, color: 'text-purple-500' },
      { icon: '🧭', label: 'MBTI 测试', value: stats?.mbti_count, color: 'text-teal-500' },
      { icon: '💬', label: '会话数', value: stats?.session_count, color: 'text-amber-500' },
    ]
    return (
      <div className="relative flex flex-col min-h-dvh overflow-hidden bg-gradient-to-br from-blue-50 via-white to-purple-50 dark:from-gray-900 dark:via-gray-950 dark:to-gray-900">
      <Toast message={toast} />
        <div className="absolute inset-0 pointer-events-none" aria-hidden="true">
          <div className="hub-blob absolute w-72 h-72 rounded-full bg-blue-200/40 dark:bg-blue-500/10" style={{ top: '8%', left: '6%' }} />
          <div className="hub-blob absolute w-64 h-64 rounded-full bg-purple-200/40 dark:bg-purple-500/10" style={{ bottom: '10%', right: '8%', animationDelay: '1.5s' }} />
        </div>

        <header className="relative z-10 shrink-0 flex items-center justify-between px-6 py-4">
      <Button
        variant="ghost"
        size="sm"
        isDark={isDark}
        onClick={() => setPage('hub')}
        title="返回功能入口"
      >← 返回入口</Button>
          <span className="text-sm font-medium text-gray-700 dark:text-gray-300">数据看板</span>
        </header>

        <main className="relative z-10 flex-1 flex flex-col items-center px-6 pb-10">
          <div className="w-full max-w-3xl hub-fade-up">
            <h1 className="text-2xl font-bold text-gray-800 dark:text-gray-100 mb-1">📊 数据看板</h1>
            <p className="text-sm text-gray-500 dark:text-gray-400 mb-8">你的学习与使用轨迹</p>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {cards.map((c, i) => (
                <div key={i} className={`rounded-2xl border p-5 text-center ${isDark ? "bg-gray-900 border-gray-700" : "bg-white border-gray-200"} shadow-sm`}>
                  <p className="text-3xl mb-2">{c.icon}</p>
                  <p className={`text-3xl font-bold ${c.color}`}>{stats ? c.value : '—'}</p>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">{c.label}</p>
                </div>
              ))}
            </div>

            {(stats?.mbti_history?.length || 0) > 0 && (
              <div className={`mt-6 rounded-2xl border p-6 ${isDark ? "bg-gray-900 border-gray-700" : "bg-white border-gray-200"} shadow-sm`}>
                <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-4">MBTI 测试历史</p>
                <div className="space-y-2 text-sm">
                  {stats.mbti_history.map((h: any, i: number) => (
                    <div key={i} className="flex items-center justify-between">
                      <span className="text-xs text-gray-400 font-mono">{h.created_at?.slice(0, 16) || ''}</span>
                      <span className="font-semibold text-gray-700 dark:text-gray-200">{h.mbti}</span>
                      <span className="text-xs text-gray-500 dark:text-gray-400">{h.ideal_role || '-'}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="mt-8 flex justify-center gap-4">
        <Button
          variant="secondary"
          size="md"
          isDark={isDark}
          onClick={fetchDashboard}
          disabled={dashboardLoading}
        >{dashboardLoading ? '刷新中...' : '刷新'}</Button>
        <Button
          variant="ghost"
          size="md"
          isDark={isDark}
          onClick={() => setPage('hub')}
        >返回入口</Button>
            </div>
          </div>
        </main>
      </div>
    )
  }

  // ═══════════════════════════════════════
  //  渲染：个人主页
  // ═══════════════════════════════════════
  if (page === 'profile') {
    return (
      <div className="flex flex-col h-dvh bg-gray-50 dark:bg-gray-950">
      <Toast message={toast} />
        <header className="shrink-0 border-b px-4 py-3 bg-white dark:bg-gray-900 border-gray-200 dark:border-gray-800">
          <div className="max-w-3xl mx-auto flex items-center justify-between">
            <h1 className="text-lg font-semibold text-gray-800 dark:text-gray-100">个人中心</h1>
            <button onClick={() => setPage('hub')}
              className="text-xs text-blue-500 hover:text-blue-400 transition cursor-pointer">
              返回入口
            </button>
          </div>
        </header>

        <main className="flex-1 overflow-y-auto px-4 py-6">
          <div className="max-w-lg mx-auto space-y-6">

            <div className="bg-white dark:bg-gray-900 rounded-2xl shadow-sm border border-gray-200 dark:border-gray-800 p-6">
              <h2 className="text-sm font-semibold text-gray-500 dark:text-gray-400 mb-3">账号信息</h2>
              <div className="space-y-2 text-sm">
                <p className="text-gray-800 dark:text-gray-100">用户名：{profileInfo?.username || '...'}</p>
                <p className="text-gray-800 dark:text-gray-100">邮箱：{profileInfo?.email || '...'}</p>
                <p className="text-gray-800 dark:text-gray-100">显示名称：{profileInfo?.display_name || '...'}</p>
              </div>
            </div>

            <form onSubmit={handleUpdateName} className="bg-white dark:bg-gray-900 rounded-2xl shadow-sm border border-gray-200 dark:border-gray-800 p-6 space-y-3">
              <h2 className="text-sm font-semibold text-gray-500 dark:text-gray-400">修改显示名称</h2>
              <input type="text" placeholder="新显示名称" required
                value={profileName} onChange={(e) => setProfileName(e.target.value)}
                className="w-full rounded-xl border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 px-4 py-2 text-sm outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 text-gray-800 dark:text-gray-100 placeholder-gray-400"
              />
              <button type="submit" className="rounded-xl bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 transition">保存</button>
            </form>

            <form onSubmit={handleUpdatePwd} className="bg-white dark:bg-gray-900 rounded-2xl shadow-sm border border-gray-200 dark:border-gray-800 p-6 space-y-3">
              <h2 className="text-sm font-semibold text-gray-500 dark:text-gray-400">修改密码</h2>
              <input type="password" placeholder="当前密码" required
                value={pwdOld} onChange={(e) => setPwdOld(e.target.value)}
                className="w-full rounded-xl border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 px-4 py-2 text-sm outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 text-gray-800 dark:text-gray-100 placeholder-gray-400"
              />
              <input type="password" placeholder="新密码（至少 6 位）" required
                value={pwdNew} onChange={(e) => setPwdNew(e.target.value)}
                className="w-full rounded-xl border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 px-4 py-2 text-sm outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 text-gray-800 dark:text-gray-100 placeholder-gray-400"
              />
              <input type="password" placeholder="确认新密码" required
                value={pwdNew2} onChange={(e) => setPwdNew2(e.target.value)}
                className="w-full rounded-xl border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 px-4 py-2 text-sm outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 text-gray-800 dark:text-gray-100 placeholder-gray-400"
              />
              <button type="submit" className="rounded-xl bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 transition">修改密码</button>
            </form>

            {profileMsg.text && (
              <div className={`text-sm px-4 py-2 rounded-xl ${
                profileMsg.type === 'success' ? 'bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300' :
                'bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300'}`}>
                {profileMsg.text}
              </div>
            )}

            <div className="text-center pt-2 pb-8">
              <button onClick={switchUser}
                className="text-sm text-gray-400 hover:text-red-500 transition cursor-pointer">
                切换用户
              </button>
            </div>
          </div>
        </main>
      </div>
    )
  }

  // ═══════════════════════════════════════
  //  渲染：聊天页
  // ═══════════════════════════════════════

  // 面试模式：渲染独立考试式组件（无侧栏、无聊天流）
  if (page === 'chat' && chatMode === 'interview') {
    return (
      <div className="flex h-dvh">
      <Toast message={toast} />
        <div className={`flex flex-col flex-1 ${isDark ? 'bg-gray-950 text-gray-100' : 'bg-gradient-to-br from-purple-50 via-white to-indigo-50 text-gray-800'}`}>
          <header className={`shrink-0 border-b px-4 py-3 ${isDark ? "border-gray-800" : "border-purple-200 bg-white/70"}`}>
            <div className="max-w-3xl mx-auto flex items-center justify-between">
              <div className="flex items-center gap-2">
                <button onClick={() => setPage('hub')}
                  className="text-sm text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition cursor-pointer"
                  title="返回入口">←</button>
                <span className="font-semibold text-purple-600 dark:text-purple-400">🎯 模拟面试</span>
              </div>
            </div>
          </header>
          <InterviewExam
            apiBase={apiBase}
            authHeaders={authHeaders}
            modelProvider={modelProvider}
            isDark={isDark}
            onExit={() => setPage('hub')}
            onToast={setToast}
          />
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-dvh">
  <Toast message={toast} />
      {/* 侧边栏 - 历史会话 */}
      <aside className={`${showSidebar ? "w-60" : "w-0"} flex-shrink-0 transition-all duration-200 overflow-hidden border-r ${isDark ? "border-gray-800 bg-gray-900" : "border-gray-200 bg-gray-50"}`}>
        <div className="flex flex-col h-full">
          <div className="p-3">
      <Button
        variant="primary"
        size="sm"
        isDark={isDark}
        onClick={newSession}
        className="w-full"
      >+ 新建会话</Button>
          </div>
          <nav className="flex-1 overflow-y-auto px-2 pb-2 space-y-1">
            {groupSessions(sessions).map(([groupName, items]: [string, any[]]) => (
              <div key={groupName}>
                <p className="px-3 pt-3 pb-1 text-[11px] font-medium text-gray-400 dark:text-gray-500">{groupName}</p>
                {items.map((s: any) => (
                  <div key={s.session_id} className="relative group">
                    <div
                      className={`flex items-center gap-1 rounded-lg px-3 py-2 text-sm cursor-pointer transition ${
                        s.session_id === sessionId
                          ? 'bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-300'
                          : 'hover:bg-gray-200 dark:hover:bg-gray-800 text-gray-700 dark:text-gray-300'
                      }`}
                      onClick={() => switchSession(s.session_id)}
                    >
                      {/* 标题或内联编辑框 */}
                      {editingFor === s.session_id ? (
                        <input
                          autoFocus
                          value={editingTitle}
                          onChange={(e) => setEditingTitle(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') renameSession(s.session_id, editingTitle)
                            if (e.key === 'Escape') setEditingFor(null)
                          }}
                          onBlur={() => renameSession(s.session_id, editingTitle)}
                          onClick={(e) => e.stopPropagation()}
                          className="flex-1 min-w-0 text-xs rounded px-1.5 py-0.5 border border-blue-500 outline-none bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-100"
                          placeholder="输入新标题"
                        />
                      ) : (
                        <span className="flex-1 truncate" title={s.preview || s.label}>
                          {s.label || s.preview || '新对话'}
                        </span>
                      )}
                      {/* 三个点菜单按钮（hover 显示） */}
                      <button
                        onClick={(e) => { e.stopPropagation(); setMenuFor(menuFor === s.session_id ? null : s.session_id) }}
                        className="opacity-0 group-hover:opacity-100 shrink-0 text-xs text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 px-1 rounded cursor-pointer transition"
                        title="会话操作"
                      >⋯</button>
                    </div>
                    {/* 三点弹出菜单 */}
                    {menuFor === s.session_id && (
                      <>
                        <div className="fixed inset-0 z-40" onClick={(e) => { e.stopPropagation(); setMenuFor(null) }} />
                        <div
                          className={`absolute right-2 top-8 z-50 w-40 rounded-xl border shadow-lg py-1 text-sm ${
                            isDark ? "bg-gray-900 border-gray-700" : "bg-white border-gray-200"
                          }`}
                          onClick={(e) => e.stopPropagation()}
                        >
                          <button
                            onClick={(e) => { e.stopPropagation(); setMenuFor(null); setEditingFor(s.session_id); setEditingTitle(s.label || '') }}
                            className="w-full text-left px-3 py-1.5 hover:bg-gray-100 dark:hover:bg-gray-800 cursor-pointer"
                          >✏️ 修改标题</button>
                          <button
                            onClick={(e) => { e.stopPropagation(); saveSessionToNote(s.session_id) }}
                            className="w-full text-left px-3 py-1.5 hover:bg-gray-100 dark:hover:bg-gray-800 cursor-pointer"
                          >📝 保存到笔记</button>
                          <button
                            onClick={(e) => { e.stopPropagation(); setMenuFor(null); deleteSession(s.session_id) }}
                            className="w-full text-left px-3 py-1.5 text-red-500 hover:bg-red-50 dark:hover:bg-red-900/30 cursor-pointer"
                          >🗑️ 删除会话</button>
                        </div>
                      </>
                    )}
                  </div>
                ))}
              </div>
            ))}
            {sessions.length === 0 && (
              <p className="text-xs text-gray-400 text-center mt-4">暂无历史对话</p>
            )}
          </nav>
        </div>
      </aside>

      {/* 主聊天区 */}
      <div className={`flex flex-col flex-1 ${
        isDark
          ? "bg-gray-950 text-gray-100"
          : "bg-white text-gray-800"
      }`}>
      {/* 顶栏：DeepSeek 风精简一行（折叠 + 标题 + 当前模式胶囊 + 3 操作图标 + 头像下拉菜单） */}
      <header className={`shrink-0 border-b px-4 py-3 ${isDark ? "border-gray-800 bg-gray-950" : "border-gray-200"}`}>
        <div className="max-w-3xl mx-auto flex items-center justify-between gap-2">
          {/* 左：折叠 + 标题 + 当前模式胶囊 */}
          <div className="flex items-center gap-3 min-w-0">
            <Button
              variant="ghost" size="sm" isDark={isDark}
              onClick={() => setShowSidebar(!showSidebar)}
              title={showSidebar ? '隐藏侧边栏' : '显示侧边栏'}
            >{showSidebar ? '⟨' : '⟩'}</Button>
            <span className={`text-base font-semibold whitespace-nowrap ${isDark ? "text-gray-100" : "text-gray-800"}`}>
              成长智伴
            </span>
            {/* 当前模式 chip（点击下钻中央 welcome 重选） */}
            <button
              onClick={() => setMessages([])}
              title="点击回到中央选择模式"
              className={`hidden sm:inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-medium cursor-pointer transition ${isDark ? 'bg-blue-500/15 text-blue-400 hover:bg-blue-500/25' : 'bg-blue-50 text-blue-700 hover:bg-blue-100'}`}
            >
              {MODE_PILLS[chatMode].icon} {MODE_PILLS[chatMode].label}
            </button>
          </div>

          {/* 右：3 个图标按钮 + 用户头像菜单 */}
          <div className="flex items-center gap-1 shrink-0">
            <button onClick={() => setShowKeySettings(true)} title="模型密钥设置"
              className={`w-8 h-8 rounded-lg flex items-center justify-center cursor-pointer transition ${isDark ? "hover:bg-gray-800 text-gray-400" : "hover:bg-gray-100 text-gray-500"}`}
            >🔑</button>
            <button onClick={() => setPage('hub')} title="返回功能入口"
              className={`w-8 h-8 rounded-lg flex items-center justify-center cursor-pointer transition ${isDark ? "hover:bg-gray-800 text-gray-400" : "hover:bg-gray-100 text-gray-500"}`}
            >🏠</button>
            <button onClick={() => setIsDark(!isDark)} title="切换主题"
              className={`w-8 h-8 rounded-lg flex items-center justify-center cursor-pointer transition ${isDark ? "hover:bg-gray-800 text-gray-400" : "hover:bg-gray-100 text-gray-500"}`}
            >{isDark ? '☀️' : '🌙'}</button>

            {/* 用户头像（含点击下拉菜单：模型切换、个人中心、MBTI、看板、清空、面试归档、薄弱点、退出） */}
            <div className="relative ml-1">
              <button
                onClick={() => setUserMenuOpen(!userMenuOpen)}
                className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-semibold cursor-pointer transition ring-1 ${isDark ? 'bg-blue-500/30 text-blue-200 ring-blue-400/30 hover:bg-blue-500/50' : 'bg-blue-500 text-white ring-blue-300 hover:bg-blue-400'}`}
                title={username || '账号'}
              >{(username[0] || '?').toUpperCase()}</button>

              {userMenuOpen && (
                <>
                  <div className="fixed inset-0 z-40" onClick={() => setUserMenuOpen(false)} />
                  <div className={`absolute right-0 top-10 z-50 w-64 rounded-xl border shadow-xl py-1 text-sm ${isDark ? 'bg-gray-900 border-gray-700 text-gray-200' : 'bg-white border-gray-200 text-gray-700'}`}>
                    <div className={`px-4 py-2.5 border-b ${isDark ? 'border-gray-800' : 'border-gray-100'}`}>
                      <p className="text-xs opacity-60">已登录</p>
                      <p className="font-medium truncate">{username || '匿名'}</p>
                    </div>

                    {/* 模型切换器 */}
                    <div className={`px-3 py-2 border-b ${isDark ? 'border-gray-800' : 'border-gray-100'}`}>
                      <p className="text-[11px] opacity-60 mb-1">当前模型</p>
                      <select
                        value={modelProvider}
                        onChange={(e) => {
                          const val = e.target.value
                          setModelProvider(val)
                          if (!modelEffective[val]) {
                            setToast(`${MODEL_INFO[val].label} 未配置密钥，将使用 DeepSeek 兜底回答`)
                          } else {
                            setToast(`已切换到 ${MODEL_INFO[val].label} · ${MODEL_INFO[val].role}`)
                          }
                          setUserMenuOpen(false)
                        }}
                        className={`w-full text-xs rounded px-2 py-1.5 cursor-pointer border ${isDark ? "bg-gray-800 text-gray-200 border-gray-700" : "bg-gray-50 text-gray-700 border-gray-200"}`}
                        title="点击切换模型"
                      >
                        {Object.entries(MODEL_INFO).map(([key, info]) => (
                          <option key={key} value={key}>
                            {info.label} · {info.role}
                            {configuredProviders.includes(key) ? " ✓" : ""}
                            {modelEffective[key] === false ? " (兜底)" : ""}
                          </option>
                        ))}
                      </select>
                    </div>

                    <button onClick={() => { setUserMenuOpen(false); setPage('profile'); setTimeout(fetchProfile, 50) }}
                      className="w-full text-left px-4 py-2 hover:bg-gray-100 dark:hover:bg-gray-800 cursor-pointer">👤 个人中心</button>
                    <button onClick={() => { setUserMenuOpen(false); setPage('mbti') }}
                      className="w-full text-left px-4 py-2 hover:bg-gray-100 dark:hover:bg-gray-800 cursor-pointer">🧭 MBTI 测试</button>
                    <button onClick={() => { setUserMenuOpen(false); setPage('dashboard'); fetchDashboard() }}
                      className="w-full text-left px-4 py-2 hover:bg-gray-100 dark:hover:bg-gray-800 cursor-pointer">📊 数据看板</button>

                    {messages.length > 0 && (
                      <button onClick={() => { setMessages([]); setUserMenuOpen(false) }}
                        className="w-full text-left px-4 py-2 hover:bg-gray-100 dark:hover:bg-gray-800 cursor-pointer">🗑️ 清空消息</button>
                    )}

                    {chatMode === 'interview' && messages.length > 0 && (
                      <>
                        <div className={`my-1 border-t ${isDark ? 'border-gray-800' : 'border-gray-100'}`} />
                        <button onClick={() => { handleSaveInterview(); setUserMenuOpen(false) }} disabled={savingInterview}
                          className="w-full text-left px-4 py-2 hover:bg-gray-100 dark:hover:bg-gray-800 cursor-pointer disabled:opacity-50">{savingInterview ? '归档中...' : '📝 保存面试记录'}</button>
                        <button onClick={() => { handleWeaknessProfile(); setUserMenuOpen(false) }} disabled={buildingWeakness}
                          className="w-full text-left px-4 py-2 hover:bg-gray-100 dark:hover:bg-gray-800 cursor-pointer disabled:opacity-50">{buildingWeakness ? '生成中...' : '📊 生成薄弱点画像'}</button>
                      </>
                    )}

                    <div className={`my-1 border-t ${isDark ? 'border-gray-800' : 'border-gray-100'}`} />
                    <button onClick={handleLogout}
                      className="w-full text-left px-4 py-2 text-red-500 hover:bg-red-50 dark:hover:bg-red-900/30 cursor-pointer">🚪 退出登录</button>
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      </header>

      {/* 消息列表 */}
      <main className="flex-1 overflow-y-auto px-4 py-6">
        <div className="max-w-3xl mx-auto space-y-4">
          {messages.length === 0 && !historyLoading && (
            <div className="flex flex-col items-center justify-center h-full mt-10">
              <p className={`text-2xl font-semibold mb-2 ${isDark ? "text-gray-200" : "text-gray-800"}`}>
                今天想聊些什么？
              </p>
              <p className={`text-sm mb-6 ${isDark ? "text-gray-500" : "text-gray-400"}`}>
                选个模式开聊，随时再换
              </p>
              <div className="flex flex-wrap justify-center gap-3 max-w-2xl">
                {(Object.keys(MODE_PILLS) as Array<keyof typeof MODE_PILLS>).map((m) => {
                  const p = MODE_PILLS[m]
                  const active = chatMode === m
                  return (
                    <button
                      key={m}
                      onClick={() => {
                        if (m === 'interview') {
                          // 切到 interview 触发早返到独立考试式组件
                          setChatMode('interview')
                          setMessages([])
                        } else {
                          setChatMode(m)
                        }
                      }}
                      className={`flex flex-col items-start gap-1 px-5 py-4 rounded-2xl border-2 transition cursor-pointer min-w-[180px] ${
                        active
                          ? isDark
                            ? 'border-blue-500 bg-blue-500/10'
                            : 'border-blue-500 bg-blue-50'
                          : isDark
                            ? 'border-gray-700 hover:border-gray-500 bg-gray-900/40'
                            : 'border-gray-200 hover:border-gray-300 bg-white'
                      }`}
                    >
                      <div className="flex items-center gap-2">
                        <span className="text-2xl">{p.icon}</span>
                        <span className={`text-sm font-semibold ${isDark ? "text-gray-100" : "text-gray-800"}`}>{p.label}</span>
                      </div>
                      <p className={`text-[11px] text-left ${isDark ? "text-gray-500" : "text-gray-400"}`}>
                        {p.subtitle}
                      </p>
                    </button>
                  )
                })}
              </div>
            </div>
          )}

          {historyLoading && (
            <div className={`flex justify-center mt-10 ${isDark ? "text-gray-500" : "text-gray-400"}`}>
              <p className="text-sm">加载历史对话中...</p>
            </div>
          )}

          {messages.map((msg, i) => (
            <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div className={`group max-w-[75%] rounded-2xl px-4 py-2.5 leading-relaxed ${
                msg.role === 'user'
                  ? `bg-blue-600 text-white rounded-br-md whitespace-pre-wrap ${isDark ? "!bg-blue-500" : ""}`
                  : `rounded-bl-md whitespace-normal ${isDark ? "!bg-gray-800 !text-gray-100" : "bg-gray-100 text-gray-800"}`
              }`}>
                <div className="relative">
                  {msg.role === 'user' ? (
                    msg.content
                  ) : (
                    <div className="markdown-body">
                      <Markdown content={msg.content} />
                    </div>
                  )}
                  <div className="absolute -top-1 -right-1 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition">
                    {msg.role === 'assistant' && chatMode === 'workspace' && (
                      <button
                        onClick={() => saveAsNote(msg.content)}
                        className="text-xs bg-teal-500 hover:bg-teal-400 text-white rounded px-1.5 py-0.5 cursor-pointer"
                        title="存为 Obsidian 笔记">存笔记</button>
                    )}
                    <button
                      onClick={() => navigator.clipboard.writeText(msg.content)}
                      className="text-xs bg-gray-300 hover:bg-gray-400 text-gray-700 rounded px-1.5 py-0.5 cursor-pointer"
                      title="复制">复制</button>
                  </div>
                </div>
              </div>
            </div>
          ))}

          {loading && (
            <div className="flex justify-start">
              <div className={`rounded-2xl rounded-bl-md px-4 py-3 ${isDark ? "bg-gray-800" : "bg-gray-100"}`}>
                <span className="inline-flex gap-1">
                  <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" />
                  <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce [animation-delay:0.1s]" />
                  <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce [animation-delay:0.2s]" />
                </span>
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>
      </main>

      {/* 输入区（chip 行 + 输入框 + 附件 + 圆形发送） */}
      <footer className={`shrink-0 border-t px-4 py-3 ${isDark ? "border-gray-800 bg-gray-950" : "border-gray-200 bg-white"}`}>
        <div className="max-w-3xl mx-auto space-y-2">
          {/* 工具能力 chip 行（与 sendMessage.buildUserMessage 联动） */}
          <div className="flex items-center gap-2 flex-wrap">
            {([
              { key: 'deepThink',     icon: '🧠', label: '展开推理' },
              { key: 'webSearch',     icon: '🌐', label: '联网辅助' },
              { key: 'knowledgeBase', icon: '📚', label: '引用笔记' },
            ] as const).map(({ key, icon, label }) => {
              const on = (toolChips as any)[key] as boolean
              return (
                <button
                  key={key}
                  onClick={() => setToolChips((c) => ({ ...c, [key]: !on }))}
                  className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium border transition cursor-pointer ${
                    on
                      ? isDark
                        ? 'bg-blue-500/20 border-blue-400/50 text-blue-300'
                        : 'bg-blue-50 border-blue-200 text-blue-700'
                      : isDark
                        ? 'bg-gray-900 border-gray-700 text-gray-400 hover:border-gray-500'
                        : 'bg-white border-gray-200 text-gray-500 hover:border-gray-300'
                  }`}
                  title={on ? `已开启：${label}` : `点击开启：${label}`}
                >
                  <span>{icon}</span><span>{label}</span>
                </button>
              )
            })}
          </div>

          {/* 输入行 */}
          <div className={`flex items-end gap-2 rounded-2xl border px-3 py-2 transition ${isDark ? "border-gray-700 bg-gray-900 focus-within:border-blue-500" : "border-gray-300 bg-white focus-within:border-blue-500 focus-within:shadow-sm"}`}>
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={
                chatMode === 'knowledge' ? "向你的 Obsidian 笔记库提问…"
                : "给成长智伴发条消息..."
              }
              rows={1}
              className={`flex-1 resize-none bg-transparent border-0 px-1 py-1.5 text-sm outline-none ${isDark ? "text-gray-100 placeholder-gray-500" : "text-gray-800 placeholder-gray-400"}`}
            />
            {/* 附件（先占位，为后续支持文件附件预留 UI 锚点） */}
            <button
              type="button"
              onClick={() => setToast('附件功能待后续版本支持')}
              title="附件"
              className={`shrink-0 w-9 h-9 rounded-full flex items-center justify-center cursor-pointer transition ${isDark ? "hover:bg-gray-800 text-gray-500" : "hover:bg-gray-100 text-gray-400"}`}
            >📎</button>
            {/* 圆形发送按钮 */}
            <button
              type="button"
              onClick={sendMessage}
              disabled={loading || !input.trim()}
              title={loading ? '生成中...' : '发送 (Enter)'}
              className={`shrink-0 w-9 h-9 rounded-full flex items-center justify-center cursor-pointer transition ${
                loading || !input.trim()
                  ? isDark ? "bg-gray-800 text-gray-600 cursor-not-allowed" : "bg-gray-100 text-gray-300 cursor-not-allowed"
                  : isDark ? "bg-blue-500 hover:bg-blue-400 text-white" : "bg-blue-600 hover:bg-blue-500 text-white shadow-sm"
              }`}
            >↑</button>
          </div>
          <p className={`text-[11px] text-center ${isDark ? "text-gray-600" : "text-gray-400"}`}>Enter 发送 · Shift+Enter 换行</p>
        </div>
      </footer>

      {/* 模型密钥设置弹窗 */}
      {showKeySettings && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
          onClick={() => setShowKeySettings(false)}
        >
          <div
            className={`w-full max-w-md rounded-2xl shadow-xl ${isDark ? "bg-gray-900 text-gray-100" : "bg-white text-gray-800"} p-5`}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-base font-semibold">模型密钥设置</h2>
              <button
                onClick={() => setShowKeySettings(false)}
                className="text-gray-400 hover:text-gray-600 cursor-pointer"
                title="关闭">✕</button>
            </div>
            <p className="text-xs text-gray-400 mb-4">
              填写你自己的各厂商 API Key，保存后即可在上方切换器中使用，无需改动后端。留空的项不会修改。
            </p>
            <div className="space-y-3">
              {Object.entries(MODEL_INFO).map(([key, info]) => (
                <div key={key} className={`rounded-lg border p-3 ${isDark ? "border-gray-700" : "border-gray-200"}`}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-sm font-medium">{info.label} · {info.role}</span>
                    {configuredProviders.includes(key)
                      ? <span className="text-xs text-green-500">已配置</span>
                      : <span className="text-xs text-gray-400">未配置</span>}
                  </div>
                  <input
                    type="password"
                    value={keyDrafts[key] || ''}
                    onChange={(e) => setKeyDrafts((p) => ({ ...p, [key]: e.target.value }))}
                    placeholder="粘贴 API Key（留空不修改）"
                    className={`w-full rounded-md border px-3 py-1.5 text-sm outline-none focus:border-blue-500 ${isDark ? "border-gray-700 bg-gray-800 text-gray-100 placeholder-gray-500" : "border-gray-300 bg-white text-gray-800 placeholder-gray-400"}`}
                  />
                  {configuredProviders.includes(key) && (
                    <button
                      onClick={() => deleteKey(key)}
                      className="mt-2 text-xs text-red-500 hover:text-red-600 cursor-pointer"
                    >删除该密钥</button>
                  )}
                </div>
              ))}
            </div>
            <div className="mt-4 flex justify-end gap-2">
              <button
                onClick={() => setShowKeySettings(false)}
                className="text-sm px-3 py-1.5 rounded-md border border-gray-300 text-gray-500 cursor-pointer"
              >取消</button>
              <button
                onClick={saveKeys}
                disabled={keySaving}
                className="text-sm px-3 py-1.5 rounded-md bg-blue-600 text-white hover:bg-blue-500 disabled:opacity-40 cursor-pointer"
              >{keySaving ? '保存中...' : '保存'}</button>
            </div>
          </div>
        </div>
      )}
    </div>
    </div>
  )
}

export default App
