import type { FoodItem } from '../data/restaurants'

type FoodCardProps = {
  item: FoodItem
}

function FoodCard({ item }: FoodCardProps) {
  const iconByName: Record<string, string> = {
    'Butter Chicken': '🍛',
    'Wood-fire Pizza': '🍕',
    'Truffle Risotto': '🍲',
    'Sushi Platter': '🍣',
    'Grilled Prawns': '🦐',
    'Tandoori Platter': '🍗',
    'Thai Green Curry': '🥗',
    'Smash Burger': '🍔',
    'Dal Makhani': '🥘',
    'Pita Board': '🫓',
    'Club Sandwich': '🥪',
    'Molten Lava Cake': '🍮',
  }

  const icon = iconByName[item.name] ?? '🍽️'

  return (
    <article className="food-card">
      <div
        className="food-card-visual"
        style={{ background: item.bgColor }}
      >
        <div className="food-card-sheen" />
        <div className="food-card-ambient">
          <div className="food-card-blob food-card-blob--left" />
          <div className="food-card-blob food-card-blob--right" />
        </div>

        <div className="food-card-shadow" />
        <div className="food-card-plate">
          <span>{icon}</span>
        </div>

        <span className="food-card-chip food-card-chip--tag">
          {item.tag}
        </span>
        <span className="food-card-chip food-card-chip--rating">
          ★ {item.rating.toFixed(1)}
        </span>
      </div>

      <div className="food-card-meta">
        <p className="food-card-name">{item.name}</p>
        <p className="food-card-price">₹{item.price}</p>
      </div>
    </article>
  )
}

export default FoodCard
