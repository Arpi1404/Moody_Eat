import type { FoodItem } from "../data/restaurants";

type FoodCardProps = {
  item: FoodItem;
};

function FoodCard({ item }: FoodCardProps) {
  return (
    <article
      style={{
        width: "160px",
        flexShrink: 0,
        transform: "scale(1)",
        transition: "transform 200ms ease",
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.transform = "scale(1.03)";
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.transform = "scale(1)";
      }}
    >
      <div
        style={{
          width: "160px",
          height: "110px",
          background: item.bgColor,
          borderRadius: "14px",
          padding: "8px",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
        }}
      >
        <span
          style={{
            fontSize: "11px",
            background: "rgba(0, 0, 0, 0.5)",
            color: "#fff",
            backdropFilter: "blur(6px)",
            WebkitBackdropFilter: "blur(6px)",
            borderRadius: "999px",
            padding: "4px 8px",
            alignSelf: "flex-end",
            lineHeight: 1,
          }}
        >
          {item.tag}
        </span>

        <span
          style={{
            fontSize: "11px",
            background: "rgba(0, 0, 0, 0.5)",
            color: "#fff",
            backdropFilter: "blur(6px)",
            WebkitBackdropFilter: "blur(6px)",
            borderRadius: "999px",
            padding: "4px 8px",
            lineHeight: 1,
          }}
        >
          ★ {item.rating.toFixed(1)}
        </span>
      </div>

      <div
        style={{
          padding: "8px 4px",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          gap: "8px",
        }}
      >
        <p
          style={{
            margin: 0,
            color: "rgba(255, 255, 255, 0.85)",
            fontSize: "13px",
            fontWeight: 500,
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
          }}
        >
          {item.name}
        </p>

        <p
          style={{
            margin: 0,
            color: "#f97316",
            fontSize: "12px",
            flexShrink: 0,
          }}
        >
          ₹{item.price}
        </p>
      </div>
    </article>
  );
}

export default FoodCard;
