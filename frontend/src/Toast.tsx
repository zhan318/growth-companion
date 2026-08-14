interface ToastProps {
  message: string
}

/**
 * 全局 Toast 提示（fixed 定位，任何页面都能显示）。
 * 挂载方式：每个页面分支最外层渲染 <Toast message={toast} />
 */
export default function Toast({ message }: ToastProps) {
  if (!message) return null
  return (
    <div className="fixed top-16 left-1/2 -translate-x-1/2 z-[999] whitespace-nowrap text-sm px-4 py-2 rounded-xl shadow-lg bg-gray-900/90 dark:bg-gray-100/90 text-white dark:text-gray-900 backdrop-blur">
      {message}
    </div>
  )
}
