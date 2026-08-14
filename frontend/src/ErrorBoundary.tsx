import { Component } from 'react'
import type { ReactNode } from 'react'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
  error?: Error
}

/**
 * 全局错误边界：任何子组件渲染/生命周期抛错时，
 * 降级渲染错误提示而不是白屏（React 18+ 默认行为是 unmount 整个根）。
 */
class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error) {
    // 上报到控制台，便于排查
    console.error('[ErrorBoundary] 捕获到渲染错误:', error)
  }

  handleReset = () => {
    this.setState({ hasError: false, error: undefined })
    window.location.reload()
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-dvh flex flex-col items-center justify-center gap-4 bg-gray-50 dark:bg-gray-950 px-6 text-center">
          <p className="text-5xl">😵</p>
          <h1 className="text-xl font-semibold text-gray-800 dark:text-gray-100">
            页面出错了
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 max-w-md break-all">
            {this.state.error?.message || '发生未知错误'}
          </p>
          <button
            onClick={this.handleReset}
            className="px-6 py-2.5 rounded-xl bg-teal-600 hover:bg-teal-500 text-white text-sm font-medium transition cursor-pointer"
          >
            刷新重试
          </button>
        </div>
      )
    }
    return this.props.children
  }
}

export default ErrorBoundary
