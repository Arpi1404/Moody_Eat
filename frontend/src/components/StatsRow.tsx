type StatItem = {
  num: string
  label: string
}

type StatsRowProps = {
  stats: StatItem[]
}

function StatsRow({ stats }: StatsRowProps) {
  return (
    <div className="landing-stats">
      {stats.map((stat, index) => (
        <div key={`${stat.label}-${index}`} className="landing-stat">
          <div>
            <p className="landing-stat-num">{stat.num}</p>
            <p className="landing-stat-label">{stat.label}</p>
          </div>
          {index < stats.length - 1 ? <div className="landing-stat-divider" /> : null}
        </div>
      ))}
    </div>
  )
}

export default StatsRow
