type CategoryChipsProps = {
  categories: string[];
  active: string;
  onChange: (cat: string) => void;
};

function CategoryChips({ categories, active, onChange }: CategoryChipsProps) {
  return (
    <div className="flex flex-wrap gap-2 px-8 pb-5">
      {categories.map((category) => {
        const isActive = category === active;

        return (
          <button
            key={category}
            type="button"
            onClick={() => onChange(category)}
            className={`rounded-full border px-4 py-1.5 text-xs transition-all duration-200 ${
              isActive
                ? "border-[#f97316] bg-[#f97316] text-white"
                : "border-white/10 bg-transparent text-white/50 hover:border-white/30 hover:text-white"
            }`}
          >
            {category}
          </button>
        );
      })}
    </div>
  );
}

export default CategoryChips;
