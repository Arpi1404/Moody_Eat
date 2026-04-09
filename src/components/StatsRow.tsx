type StatItem = {
  num: string;
  label: string;
};

type StatsRowProps = {
  stats: StatItem[];
};

function StatsRow({ stats }: StatsRowProps) {
  return (
    <div className="flex gap-4 px-8 pb-6">
      {stats.map((stat, index) => (
        <div key={`${stat.label}-${index}`} className="flex items-stretch gap-4">
          <div className="flex flex-col gap-0.5">
            <p className="text-xl font-medium text-white">{stat.num}</p>
            <p className="text-[11px] uppercase tracking-wide text-white/35">
              {stat.label}
            </p>
          </div>

          {index < stats.length - 1 ? (
            <div className="w-px self-stretch bg-white/10" />
          ) : null}
        </div>
      ))}
    </div>
  );
}

export default StatsRow;
