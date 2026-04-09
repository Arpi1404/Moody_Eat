import type { FoodItem } from "../data/restaurants";
import FoodCard from "./FoodCard";

type FoodTickerProps = {
  items: FoodItem[];
};

function FoodTicker({ items }: FoodTickerProps) {
  const tickerItems = [...items, ...items];

  return (
    <div className="overflow-x-hidden py-4">
      <div className="flex w-max gap-3 [animation:ticker_30s_linear_infinite] hover:[animation-play-state:paused]">
        {tickerItems.map((item, index) => (
          <FoodCard key={`${item.id}-${index}`} item={item} />
        ))}
      </div>
    </div>
  );
}

export default FoodTicker;
