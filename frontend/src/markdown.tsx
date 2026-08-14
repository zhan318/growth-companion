import { useMemo } from 'react'
import MarkdownIt from 'markdown-it'
import DOMPurify from 'dompurify'

// markdown-it 实例（模块级单例，避免每次渲染重建）
const md = new MarkdownIt({
  html: false,        // 不渲染原始 HTML（第一道安全闸）
  linkify: true,      // 自动识别 URL 生成链接
  breaks: true,       // 换行即 <br>
  typographer: true,  // 智能标点
}).enable(['table', 'strikethrough']) // GFM：表格 + 删除线

/** 渲染 markdown → 安全 HTML（markdown-it + DOMPurify 双层过滤） */
export function renderMarkdown(src: string): string {
  // DOMPurify 过滤 javascript: 等危险协议/脚本，第二道安全闸
  return DOMPurify.sanitize(md.render(src || ''), { USE_PROFILES: { html: true } })
}

interface MarkdownProps {
  content: string
  className?: string
}

/**
 * Markdown 渲染组件（替换 react-markdown）。
 * 用 dangerouslySetInnerHTML 直出 HTML，无组件树层级、无 unmount 副作用，
 * 规避 react-markdown 在 React 19 + StrictMode 下的 removeChild 崩溃。
 */
export default function Markdown({ content, className }: MarkdownProps) {
  const html = useMemo(() => renderMarkdown(content), [content])
  return <div className={className} dangerouslySetInnerHTML={{ __html: html }} />
}
