/* eslint-disable */
// 登录态 Lighthouse：启动 Chrome → CDP 注入 token → 导航 hub/chat → 交给 Lighthouse 测
// 用法: node lh-login.js <url> <token> <outdir>
const path = require('path')
const fs = require('fs')
const { spawn } = require('child_process')

const LH_DIR = process.env.LH_DIR || path.join(__dirname, 'node_modules')

async function main() {
  const url = process.argv[2]
  const token = process.argv[3]
  const outdir = process.argv[4]
  if (!url || !token || !outdir) {
    console.error('用法: node lh-login.js <url> <token> <outdir>')
    process.exit(1)
  }
  fs.mkdirSync(outdir, { recursive: true })

  const chromeLauncher = require(path.join(LH_DIR, 'chrome-launcher'))
  const lighthouse = require(path.join(LH_DIR, 'lighthouse'))

  // 1. 启动 headless Chrome 带调试端口（固定端口，避免随机端口就绪竞争）
  const chrome = await chromeLauncher.launch({
    chromeFlags: ['--headless=new', '--no-sandbox', '--disable-gpu', '--remote-debugging-port=9333'],
  })
  // 等待调试端口就绪（最多 20s）
  const waitPort = () => new Promise((resolve, reject) => {
    const http = require('http')
    const deadline = Date.now() + 20000
    const tryOnce = () => {
      http.get(`http://127.0.0.1:${chrome.port}/json/version`, (res) => {
        res.resume()
        resolve()
      }).on('error', () => {
        if (Date.now() > deadline) reject(new Error('调试端口就绪超时'))
        else setTimeout(tryOnce, 500)
      })
    }
    tryOnce()
  })
  await waitPort()

  try {
    // 2. 通过 CDP 注入 token（先导航到同源页面，再写 localStorage，最后跳转）
    const ws = await new Promise((resolve, reject) => {
      const http = require('http')
      http.get(`http://127.0.0.1:${chrome.port}/json/version`, (res) => {
        let data = ''
        res.on('data', (c) => (data += c))
        res.on('end', () => {
          try { resolve(JSON.parse(data).webSocketDebuggerUrl) } catch (e) { reject(e) }
        })
      }).on('error', reject)
    })
    const WebSocket = require(path.join(LH_DIR, 'ws'))
    const socket = new WebSocket(ws)
    await new Promise((r, j) => { socket.on('open', r); socket.on('error', j) })
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
    await send('Page.enable')
    await send('Runtime.enable')
    // 先导航到页面（让 origin 存在），再注入 localStorage，再刷新
    await send('Page.navigate', { url })
    await new Promise((r) => setTimeout(r, 1500))
    const inject = `
      localStorage.setItem('token', ${JSON.stringify(token)});
      localStorage.setItem('session_id', 'u4_default');
      localStorage.setItem('user_id', '4');
      localStorage.setItem('username', 'perf_user_final');
    `
    await send('Runtime.evaluate', { expression: inject })
    // 等 React 读到 token 后重新加载，进入 hub 页
    await new Promise((r) => setTimeout(r, 500))
    await send('Page.reload')
    socket.close()

    // 3. 跑 Lighthouse（连接同一个 Chrome）
    for (let i = 1; i <= 3; i++) {
      console.log(`--- 第 ${i} 次 ---`)
      const result = await lighthouse(url, {
        port: chrome.port,
        output: 'json',
        logLevel: 'error',
        onlyCategories: ['performance'],
        throttlingMethod: 'provided',
      }, null)
      fs.writeFileSync(path.join(outdir, `lh-login-run${i}.json`), JSON.stringify(result.lhr))
    }
  } finally {
    await chrome.kill()
  }
}

main().catch((e) => { console.error(e); process.exit(1) })
