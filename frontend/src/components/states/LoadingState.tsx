export function LoadingState({ message = 'Loading...' }: { message?: string }) {
  return (
    <div className="state-card state-card--loading" role="status" aria-live="polite">
      <span className="state-spinner" aria-hidden />
      <p>{message}</p>
    </div>
  )
}

export default LoadingState
