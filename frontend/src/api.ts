/**
 * 统一 API 请求工具：fetch + 超时 + 错误分类。
 * 所有接口请求都走这里，避免"fetch 永久 pending / catch 静默吞错"。
 */

const DEFAULT_TIMEOUT = 8000

/** 统一 API 错误：带 HTTP 状态码（网络/超时错误 status 为 undefined） */
export class ApiError extends Error {
  status?: number

  constructor(message: string, status?: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

/**
 * 带超时的 fetch 封装。
 * - 超时/网络错误抛 ApiError（调用方 catch 后必须给用户提示，不再静默）
 * - 返回原始 Response，调用方自行处理 res.ok / res.json()
 */
export async function apiFetch(
  url: string,
  options: RequestInit = {},
  timeout: number = DEFAULT_TIMEOUT,
): Promise<Response> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeout)
  try {
    return await fetch(url, { ...options, signal: controller.signal })
  } catch (e: any) {
    if (e?.name === 'AbortError') {
      throw new ApiError('请求超时，请重试')
    }
    throw new ApiError(e?.message || '网络错误，请检查连接')
  } finally {
    clearTimeout(timer)
  }
}
