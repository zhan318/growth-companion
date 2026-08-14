import type { ButtonHTMLAttributes, ReactNode } from 'react'

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger'
type Size = 'sm' | 'md' | 'lg'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
  /** 暗色模式开关（从父组件传入 isDark） */
  isDark?: boolean
  /** 简洁 text 节点 */
  children?: ReactNode
}

/**
 * 统一 Button 组件（A 风格：现代精炼）。
 *
 * 设计要点：
 * - 默认：清晰边框 + 轻微阴影 → 让按钮"立起来"，位置一眼能找到
 * - hover：边框加粗 + 背景色变亮 + 阴影增强 → 三态差异明显
 * - active：轻微缩放 0.97 + 阴影减少 → 物理按下反馈
 * - focus-visible：2px ring → 键盘可达性 + 视觉引导
 *
 * 4 种 variant：primary（强调操作）/ secondary（次要操作）/ ghost（轻量）/ danger（危险）
 * 3 种 size：sm（小工具栏）/ md（默认）/ lg（大按钮）
 */
export default function Button({
  variant = 'secondary',
  size = 'md',
  isDark = false,
  className = '',
  children,
  disabled,
  ...rest
}: ButtonProps) {
  // ---- 尺寸（padding + 字号）----
  const sizeCls =
    size === 'sm'
      ? 'px-2.5 py-1 text-xs'
      : size === 'lg'
        ? 'px-6 py-3 text-base'
        : 'px-4 py-2 text-sm'

  // ---- variant 基色（默认态）----
  // 每种 variant 提供：背景 / 文字 / 边框 / hover 边框色 + 阴影强度
  const variants: Record<Variant, {
    bg: string; hoverBg: string; text: string;
    border: string; hoverBorder: string;
    shadow: string;
    ring: string;
  }> = {
    primary: {
      bg: 'bg-blue-600',
      hoverBg: 'hover:bg-blue-500',
      text: 'text-white',
      border: 'border-blue-700',
      hoverBorder: 'hover:border-blue-400',
      shadow: 'shadow-sm hover:shadow-md',
      ring: 'focus-visible:ring-blue-400',
    },
    secondary: isDark
      ? {
          bg: 'bg-gray-800',
          hoverBg: 'hover:bg-gray-700',
          text: 'text-gray-200',
          border: 'border-gray-600',
          hoverBorder: 'hover:border-blue-400',
          shadow: 'shadow-sm hover:shadow-md',
          ring: 'focus-visible:ring-blue-400',
        }
      : {
          bg: 'bg-white',
          hoverBg: 'hover:bg-gray-50',
          text: 'text-gray-700',
          border: 'border-gray-300',
          hoverBorder: 'hover:border-blue-500',
          shadow: 'shadow-sm hover:shadow-md',
          ring: 'focus-visible:ring-blue-400',
        },
    ghost: isDark
      ? {
          bg: 'bg-transparent',
          hoverBg: 'hover:bg-gray-800',
          text: 'text-gray-400',
          border: 'border-transparent',
          hoverBorder: 'hover:border-gray-600',
          shadow: 'hover:shadow-sm',
          ring: 'focus-visible:ring-blue-400',
        }
      : {
          bg: 'bg-transparent',
          hoverBg: 'hover:bg-gray-100',
          text: 'text-gray-500',
          border: 'border-transparent',
          hoverBorder: 'hover:border-gray-300',
          shadow: 'hover:shadow-sm',
          ring: 'focus-visible:ring-blue-400',
        },
    danger: {
      bg: 'bg-white',
      hoverBg: 'hover:bg-red-50',
      text: 'text-red-600',
      border: 'border-red-300',
      hoverBorder: 'hover:border-red-500',
      shadow: 'shadow-sm hover:shadow-md',
      ring: 'focus-visible:ring-red-400',
    },
  }

  const v = variants[variant]

  // ---- 组合 className----
  // active 缩放 + 阴影减少 + transition + focus ring + disabled 样式
  const baseCls = [
    'inline-flex items-center justify-center gap-1.5',
    'rounded-xl',
    'font-medium',
    'border',
    'transition-all duration-150 ease-out',
    'cursor-pointer',
    'select-none',
    // 三态
    v.bg, v.hoverBg, v.text, v.border, v.hoverBorder,
    v.shadow,
    'hover:-translate-y-px',
    'active:translate-y-0 active:scale-[0.97] active:shadow-none',
    `focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-1 ${v.ring} ${isDark ? 'focus-visible:ring-offset-gray-900' : 'focus-visible:ring-offset-white'}`,
    // disabled
    'disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:translate-y-0 disabled:active:scale-100',
    // 尺寸
    sizeCls,
    className,
  ].join(' ')

  return (
    <button {...rest} disabled={disabled} className={baseCls}>
      {children}
    </button>
  )
}