from models import Cafe

CURATED_QUESTS: dict[str, dict[str, list[Cafe]]] = {
    "paris": {
        "cozy": [
            Cafe(
                name="Le Chat Noir",
                address="18 Rue des Martyrs, 75009 Paris",
                distance_minutes_walk=4,
                vibe="Warm lighting, soft jazz, ideal for reading or journaling.",
            ),
            Cafe(
                name="Café Serendipité",
                address="3 Rue des Rosiers, 75004 Paris",
                distance_minutes_walk=7,
                vibe="Tiny spot tucked in a side street, vintage posters and comfy chairs.",
            ),
            Cafe(
                name="Brume Matinale",
                address="27 Quai des Grands Augustins, 75006 Paris",
                distance_minutes_walk=10,
                vibe="Slow mornings by the Seine with pastry smells everywhere.",
            ),
        ],
        "productive": [
            Cafe(
                name="Station Café",
                address="12 Rue de Châteaudun, 75009 Paris",
                distance_minutes_walk=5,
                vibe="Lots of plugs, big tables, quiet enough for deep work.",
            ),
            Cafe(
                name="Pixel & Crème",
                address="41 Rue Oberkampf, 75011 Paris",
                distance_minutes_walk=9,
                vibe="Laptop‑friendly, fast Wi‑Fi, great filter coffee.",
            ),
            Cafe(
                name="Le Bureau Vert",
                address="2 Rue du Faubourg Poissonnière, 75010 Paris",
                distance_minutes_walk=11,
                vibe="Plants everywhere, shared workbenches, focused energy.",
            ),
        ],
    },
    "bangalore": {
        "cozy": [
            Cafe(
                name="Monsoon Stories",
                address="Indiranagar, Bengaluru",
                distance_minutes_walk=6,
                vibe="Rain‑inspired interiors, soft music, perfect for slow conversations.",
            ),
            Cafe(
                name="The Hideout Brew",
                address="Koramangala 5th Block, Bengaluru",
                distance_minutes_walk=8,
                vibe="Dim lights, board games, lots of books lining the walls.",
            ),
            Cafe(
                name="Chai & Chapters",
                address="Jayanagar 4th T Block, Bengaluru",
                distance_minutes_walk=12,
                vibe="Cozy cushions, shelves of second‑hand novels, endless chai.",
            ),
        ],
        "productive": [
            Cafe(
                name="Startup Fuel Café",
                address="HSR Layout, Bengaluru",
                distance_minutes_walk=5,
                vibe="Standing desks, plug points everywhere, founders at every table.",
            ),
            Cafe(
                name="Focus Roastery",
                address="Whitefield, Bengaluru",
                distance_minutes_walk=9,
                vibe="Bright, minimalist design, quiet playlists, specialty coffee.",
            ),
            Cafe(
                name="Grid & Grind",
                address="Malleshwaram, Bengaluru",
                distance_minutes_walk=13,
                vibe="Co‑working style seating with community tables and strong espresso.",
            ),
        ],
    },
}
