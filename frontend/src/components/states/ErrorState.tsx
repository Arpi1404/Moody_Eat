export function ErrorState({
  icon = '!',
  title,
  description,
  retryLabel = 'Try again',
  onRetry,
}: {
  icon?: string
  title: string
  description: string
  retryLabel?: string
  onRetry?: () => void
}) {
  return (
    <div className="state-card state-card--error" role="alert">
      <span className="state-icon" aria-hidden>
        {icon}
      </span>
      <p className="state-title">{title}</p>
      <p className="state-description">{description}</p>
      {onRetry && (
        <button type="button" className="state-action" onClick={onRetry}>
          {retryLabel}
        </button>
      )}
    </div>
  )
}

export default ErrorState
