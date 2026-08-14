/* eslint-disable */
// 登录态注入 v2：连接 page target → 导航应用 → 写 localStorage → reload
// 用法: node lh-inject.js <token>
const token = process.argv[2]
if (!token) { console.error('用法: node lh-inject.js <token>'); process.exit(1) }

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

async function main() {
  const page = await getPageTarget()
  const socket = new WebSocket(page.webSocketDebuggerUrl)
  let msgId = 0
  const pending = new Map()
  socket.on('message', (raw) => {
    const m = JSON.parse(raw.toString())
    if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id) }
  })
  const send = (method, params = {}) => new Promise((resolve) => {
    const id = ++msgId
    pending.set(id, resolve)
    socket.send(JSON.stringify({ id, method, params }))
  })
  socket.on('open', async () => {
    await send('Page.enable')
    await send('Runtime.enable')
    // 导航到应用，等待加载后写入 localStorage
    await send('Page.navigate', { url: 'http://127.0.0.1:8000/' })
    await new Promise((r) => setTimeout(r, 2500))
    const inject = await send('Runtime.evaluate', {
      expression: `
        localStorage.setItem('token', ${JSON.stringify(token)});
        localStorage.setItem('session_id', 'u4_default');
        localStorage.setItem('user_id', '4');
        localStorage.setItem('username', 'perf_user_final');
        'OK ' + location.href
      `,
    })
    console.log('注入:', inject.result?.result?.value || JSON.stringify(inject.result))
    // reload 让 React 读到 token → 进 hub 页
    await new Promise((r) => setTimeout(r, 300))
    await send('Page.reload')
    await new Promise((r) => setTimeout(r, 2500))
    const check = await send('Runtime.evaluate', {
      expression: `JSON.stringify({url: location.href, hasToken: !!localStorage.getItem('token')})`,
    })
    console.log('reload 后:', check.result?.result?.value)
    socket.close()
  })
  socket.on('error', (e) => { console.error('WS 错误:', e.message); process.exit(1) })
}

main().catch((e) => { console.error(e.message); process.exit(1) })
