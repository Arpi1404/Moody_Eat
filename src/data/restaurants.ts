export type FoodItem = {
  id: string;
  name: string;
  price: number;
  tag: string;
  category: string;
  bgColor: string;
  rating: number;
};

export const FOOD_ITEMS: FoodItem[] = [
  {
    id: "butter-chicken",
    name: "Butter Chicken",
    price: 380,
    tag: "Trending",
    category: "Fine dining",
    bgColor: "#2a1500",
    rating: 4.8,
  },
  {
    id: "wood-fire-pizza",
    name: "Wood-fire Pizza",
    price: 640,
    tag: "Popular",
    category: "Fine dining",
    bgColor: "#1a0d00",
    rating: 4.7,
  },
  {
    id: "truffle-risotto",
    name: "Truffle Risotto",
    price: 920,
    tag: "Date night",
    category: "Date night",
    bgColor: "#0a0a1a",
    rating: 4.9,
  },
  {
    id: "sushi-platter",
    name: "Sushi Platter",
    price: 1100,
    tag: "Rooftop",
    category: "Rooftop",
    bgColor: "#001515",
    rating: 4.9,
  },
  {
    id: "grilled-prawns",
    name: "Grilled Prawns",
    price: 740,
    tag: "Trending",
    category: "Fine dining",
    bgColor: "#001225",
    rating: 4.8,
  },
  {
    id: "tandoori-platter",
    name: "Tandoori Platter",
    price: 850,
    tag: "Chef's pick",
    category: "Group",
    bgColor: "#1a0505",
    rating: 4.7,
  },
  {
    id: "thai-green-curry",
    name: "Thai Green Curry",
    price: 420,
    tag: "Vegan",
    category: "Cafe",
    bgColor: "#001a0d",
    rating: 4.6,
  },
  {
    id: "smash-burger",
    name: "Smash Burger",
    price: 360,
    tag: "Popular",
    category: "Street food",
    bgColor: "#150800",
    rating: 4.6,
  },
  {
    id: "dal-makhani",
    name: "Dal Makhani",
    price: 280,
    tag: "Bestseller",
    category: "Street food",
    bgColor: "#160f00",
    rating: 4.7,
  },
  {
    id: "pita-board",
    name: "Pita Board",
    price: 520,
    tag: "New",
    category: "Cafe",
    bgColor: "#0d1f12",
    rating: 4.5,
  },
  {
    id: "club-sandwich",
    name: "Club Sandwich",
    price: 290,
    tag: "Popular",
    category: "Street food",
    bgColor: "#1a0d00",
    rating: 4.5,
  },
  {
    id: "molten-lava-cake",
    name: "Molten Lava Cake",
    price: 320,
    tag: "Dessert",
    category: "Date night",
    bgColor: "#130d18",
    rating: 4.8,
  },
];

export const CATEGORIES = [
  "All",
  "Fine dining",
  "Rooftop",
  "Street food",
  "Cafe",
  "Date night",
  "Group",
];

export const STATS = [
  { num: "2,400+", label: "Restaurants" },
  { num: "18 cities", label: "Across India" },
  { num: "4.8 ★", label: "Avg rating" },
];
