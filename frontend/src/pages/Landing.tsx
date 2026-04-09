import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import CategoryChips from '../components/CategoryChips'
import FoodTicker from '../components/FoodTicker'
import StatsRow from '../components/StatsRow'
import { CATEGORIES, FOOD_ITEMS, STATS } from '../data/restaurants'

function Landing() {
  const navigate = useNavigate()
  const [activeCategory, setActiveCategory] = useState('All')
  const handleExploreRoute = () => navigate('/explore')

  const filteredItems = useMemo(
    () =>
      activeCategory === 'All'
        ? FOOD_ITEMS
        : FOOD_ITEMS.filter((item) => item.category === activeCategory),
    [activeCategory],
  )

  return (
    <main className="landing-page">
      <div className="landing-shell">
        <div className="landing-top-glow" />

        <nav className="landing-nav">
          <p className="landing-brand">
            outing<span className="landing-brand-dot">.</span>
          </p>
          <button
            type="button"
            className="landing-pill-button landing-pill-button--compact"
            onClick={handleExploreRoute}
          >
            Sign in
          </button>
        </nav>

        <section className="landing-hero">
          <p className="landing-kicker">
            Discover · Dine · Plan
          </p>
          <h1 className="landing-title">
            Your next <span className="landing-title-accent">great meal</span>
            <br />
            starts here
          </h1>
          <p className="landing-subtitle">
            Handpicked restaurants, live availability, curated for the occasion.
          </p>
          <div className="landing-actions">
            <button type="button" className="landing-pill-button" onClick={handleExploreRoute}>
              Plan an outing
            </button>
            <button type="button" className="landing-pill-button" onClick={handleExploreRoute}>
              Browse near me
            </button>
          </div>
        </section>

        <CategoryChips
          categories={CATEGORIES}
          active={activeCategory}
          onChange={setActiveCategory}
        />

        <section className="landing-ticker-wrap">
          {filteredItems.length > 0 ? (
            <FoodTicker items={filteredItems} />
          ) : (
            <FoodTicker items={FOOD_ITEMS} />
          )}
        </section>

        <StatsRow stats={STATS} />
      </div>
    </main>
  )
}

export default Landing
