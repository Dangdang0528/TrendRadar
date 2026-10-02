import type { ReactNode } from 'react'

// 登录/注册共用的左右分栏:左侧品牌叙事,右侧表单
export function AuthShell({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string
  subtitle: string
  children: ReactNode
  footer: ReactNode
}) {
  return (
    <div className="auth">
      <div className="auth__aside">
        <div className="brand">
          <span className="brand__mark">NewsRadar</span>
          <span className="brand__sub">订阅推送</span>
        </div>
        <h2>把热榜里与你相关的那几条,按时送到手边。</h2>
        <p>订阅平台热榜、RSS 与关键词,绑定飞书或邮箱,在指定时间收到推送;可选开启 AI 深度总结。</p>
        <ul className="auth__points">
          <li>多平台热榜 + RSS 聚合</li>
          <li>关键词筛选,只留你要的</li>
          <li>正文级 AI 深度总结(可选)</li>
          <li>飞书 / 邮件 / Webhook 投递</li>
        </ul>
      </div>

      <div className="auth__panel">
        <div className="auth__form">
          <h1>{title}</h1>
          <p className="sub">{subtitle}</p>
          {children}
          <div className="auth__switch">{footer}</div>
        </div>
      </div>
    </div>
  )
}