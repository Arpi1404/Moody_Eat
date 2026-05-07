import type { ReactNode } from 'react'

export function EmptyState({
  icon = '✨',
  title,
  description,
  cta,
}: {
  icon?: string
  title: string
  description: string
  cta?: ReactNode
}) {
  return (
    <div className="state-card state-card--empty">
      <span className="state-icon" aria-hidden>
        {icon}
      </span>
      <p className="state-title">{title}</p>
      <p className="state-description">{description}</p>
      {cta && <div className="state-cta">{cta}</div>}
    </div>
  )
}

export default EmptyState
