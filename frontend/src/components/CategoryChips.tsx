type CategoryChipsProps = {
  categories: string[]
  active: string
  onChange: (cat: string) => void
}

function CategoryChips({ categories, active, onChange }: CategoryChipsProps) {
  return (
    <div className="landing-chip-row">
      {categories.map((category) => {
        const isActive = category === active

        return (
          <button
            key={category}
            type="button"
            onClick={() => onChange(category)}
            className={`landing-chip ${isActive ? 'landing-chip--active' : ''}`}
            aria-pressed={isActive}
          >
            {category}
          </button>
        )
      })}
    </div>
  )
}

export default CategoryChips
