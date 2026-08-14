/* eslint-disable */
// 边界3：前端真实用户路径全流程（登录→hub→工作台对话→MBTI→面试→看板）
// 用法: node boundary3-ui-test.js <token>
const token = process.argv[2]
if (!token) { console.error('用法: node boundary3-ui-test.js <token>'); process.exit(1) }

const http = require('http')
const WebSocket = require('E:/dev-cache/npm/_npx/0f94ee7615faf582/node_modules/ws')

function getPageTarget() {
  return new Promise((resolve, reject) => {
    http.get('http://127.0.0.1:9333/json/list', (res) => {
      let data = ''
      res.on('data', (c) => (data += c))
      res.on('end', () => {
        const targets = JSON.parse(data)
        const page = targets.find((t) => t.type === 'page')
        page ? resolve(page) : reject(new Error('无 page target'))
      })
    }).on('error', reject)
  })
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

async function main() {
  const page = await getPageTarget()
  const socket = new WebSocket(page.webSocketDebuggerUrl)
  let msgId = 0
  const pending = new Map()
  const errors = []
  socket.on('message', (raw) => {
    const m = JSON.parse(raw.toString())
    if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id) }
    // 监听页面异常
    if (m.method === 'Runtime.exceptionThrown') {
      errors.push(m.params.exceptionDetails?.text || 'JS exception')
    }
    if (m.method === 'Log.entryAdded' && m.params.entry.level === 'error') {
      errors.push(m.params.entry.text)
    }
  })
  const send = (method, params = {}) => new Promise((resolve) => {
    const id = ++msgId
    pending.set(id, resolve)
    socket.send(JSON.stringify({ id, method, params }))
  })
  const evalJs = async (expr) => {
    const r = await send('Runtime.evaluate', { expression: expr, returnByValue: true })
    return r.result?.result?.value
  }
  const click = async (selector) => {
    const r = await evalJs(`(() => { const el = document.querySelector(${JSON.stringify(selector)}); if (!el) return 'NOT_FOUND:${selector}'; el.click(); return 'OK'; })()`)
    return r
  }
  const type = async (selector, text) => {
    const r = await evalJs(`(() => { const el = document.querySelector(${JSON.stringify(selector)}); if (!el) return 'NOT_FOUND:${selector}'; const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set; setter.call(el, ${JSON.stringify(text)}); el.dispatchEvent(new Event('input', { bubbles: true })); return 'OK'; })()`)
    return r
  }
  const text = () => evalJs('document.body.innerText.slice(0, 300)')
  const step = (name, ok) => console.log(`${ok ? '✅' : '❌'} ${name}${typeof ok === 'string' && ok.startsWith('NOT_FOUND') ? ' → ' + ok : ''}`)

  socket.on('open', async () => {
    await send('Page.enable')
    await send('Runtime.enable')
    await send('Log.enable')

    // 1. 注入 token 进入 hub
    await send('Page.navigate', { url: 'http://127.0.0.1:8000/index.html' })
    await sleep(2500)
    await evalJs(`localStorage.setItem('token', ${JSON.stringify(token)}); localStorage.setItem('session_id', 'u4_default'); localStorage.setItem('user_id', '4'); localStorage.setItem('username', 'perf_user_final');`)
    await send('Page.reload')
    await sleep(2500)
    const hubText = await text()
    step('登录 → hub 页渲染（欢迎语）', hubText.includes('欢迎回来') || hubText.includes('perf_user_final'))

    // 2. 工作台对话
    const wsClick = await click('button[onclick*="workspace"], button')
    // 找「工作台」卡片按钮：通过文本定位
    const wsGo = await evalJs(`(() => { const btns = [...document.querySelectorAll('button')]; const b = btns.find(x => x.innerText.includes('进入') && x.closest('div') && x.closest('div').innerText.includes('工作台')); if (!b) return 'NOT_FOUND:工作台'; b.click(); return 'OK'; })()`)
    step('hub → 工作台', wsGo === 'OK')
    await sleep(1500)
    // 发消息
    const inputSel = 'textarea, input[type="text"], input:not([type])'
    const typed = await type(inputSel, '你好，介绍一下你自己')
    await sleep(300)
    const sendBtn = await evalJs(`(() => { const btns = [...document.querySelectorAll('button')]; const b = btns.find(x => x.innerText.includes('发送') || x.innerText.includes('发') || x.title === '发送'); if (!b) return 'NOT_FOUND:发送'; b.click(); return 'OK'; })()`)
    step('工作台发消息', sendBtn === 'OK')
    await sleep(12000) // 等真实 LLM 回复
    const chatText = await text()
    step('工作台收到回复', chatText.length > 100)

    // 3. MBTI
    const backHub = await evalJs(`(() => { const btns = [...document.querySelectorAll('button')]; const b = btns.find(x => x.innerText.includes('入口') || x.innerText.includes('返回')); if (!b) return 'NOT_FOUND:返回'; b.click(); return 'OK'; })()`)
    await sleep(1500)
    const mbtiGo = await evalJs(`(() => { const btns = [...document.querySelectorAll('button')]; const b = btns.find(x => x.closest('div') && x.closest('div').innerText.includes('MBTI')); if (!b) return 'NOT_FOUND:MBTI'; b.click(); return 'OK'; })()`)
    step('hub → MBTI', mbtiGo === 'OK')
    await sleep(1500)
    const mbtiText = await text()
    step('MBTI 页渲染', mbtiText.includes('MBTI') || mbtiText.includes('性格') || mbtiText.includes('理想岗位'))

    // 4. 模拟面试
    const backHub2 = await evalJs(`(() => { const btns = [...document.querySelectorAll('button')]; const b = btns.find(x => x.innerText.includes('入口') || x.innerText.includes('返回')); if (!b) return 'NOT_FOUND:返回'; b.click(); return 'OK'; })()`)
    await sleep(1500)
    const ivGo = await evalJs(`(() => { const btns = [...document.querySelectorAll('button')]; const b = btns.find(x => x.closest('div') && x.closest('div').innerText.includes('模拟面试')); if (!b) return 'NOT_FOUND:面试'; b.click(); return 'OK'; })()`)
    step('hub → 模拟面试', ivGo === 'OK')
    await sleep(1500)
    const ivText = await text()
    step('面试页渲染', ivText.length > 50)

    // 5. 数据看板
    const backHub3 = await evalJs(`(() => { const btns = [...document.querySelectorAll('button')]; const b = btns.find(x => x.innerText.includes('入口') || x.innerText.includes('返回')); if (!b) return 'NOT_FOUND:返回'; b.click(); return 'OK'; })()`)
    await sleep(1500)
    const dbGo = await evalJs(`(() => { const btns = [...document.querySelectorAll('button')]; const b = btns.find(x => x.closest('div') && x.closest('div').innerText.includes('数据看板')); if (!b) return 'NOT_FOUND:看板'; b.click(); return 'OK'; })()`)
    step('hub → 数据看板', dbGo === 'OK')
    await sleep(2000)
    const dbText = await text()
    step('看板页渲染', dbText.includes('笔记') || dbText.includes('会话') || dbText.includes('MBTI'))

    // 6. 汇总
    console.log('\n== 页面 JS 异常（应无）==')
    console.log(errors.length ? errors.slice(0, 5).join(' | ') : '✅ 无 JS 异常')
    const white = await evalJs('document.body.innerText.trim().length > 0 && document.getElementById("root") && document.getElementById("root").children.length > 0')
    console.log('白屏检查:', white ? '✅ 非白屏' : '❌ 白屏')
    socket.close()
    process.exit(0)
  })
  socket.on('error', (e) => { console.error('WS 错误:', e.message); process.exit(1) })
}

main().catch((e) => { console.error(e.message); process.exit(1) })
