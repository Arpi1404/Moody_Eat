import type { CSSProperties } from 'react'
import type { FoodItem } from '../data/restaurants'
import FoodCard from './FoodCard'

type FoodTickerProps = {
  items: FoodItem[]
}

function FoodTicker({ items }: FoodTickerProps) {
  const sourceItems = items.length > 0 ? items : []
  const minVisibleItems = 10
  const repeatsNeeded = Math.max(1, Math.ceil(minVisibleItems / Math.max(sourceItems.length, 1)))
  const primaryTrack = Array.from({ length: repeatsNeeded }, () => sourceItems).flat()
  const tickerItems = [...primaryTrack, ...primaryTrack]
  const animationDurationSeconds = Math.max(22, primaryTrack.length * 2.4)
  const tickerStyle: CSSProperties = {
    animationDuration: `${animationDurationSeconds}s`,
  }

  return (
    <div className="landing-ticker">
      <div className="landing-ticker-track" style={tickerStyle}>
        {tickerItems.map((item, index) => (
          <FoodCard key={`${item.id}-${index}`} item={item} />
        ))}
      </div>
    </div>
  )
}

export default FoodTicker
