"""Realistic name generation.

Children get names popular for US births ~2012-2021; adults get names typical of
their parents' generation. Surnames are frequency-weighted so common names repeat
the way they do in a real district, and capped so no surname takes over the roster.
"""
from __future__ import annotations

import random

from faker.providers.person.en_US import Provider as EnUS

# --- Children (US birth cohorts ~2012-2021) -----------------------------------

KID_GENERAL_F = [
    "Olivia", "Emma", "Ava", "Charlotte", "Sophia", "Amelia", "Isabella", "Mia", "Evelyn", "Harper",
    "Abigail", "Emily", "Elizabeth", "Avery", "Sofia", "Ella", "Madison", "Scarlett", "Victoria", "Aria",
    "Grace", "Chloe", "Camila", "Penelope", "Riley", "Layla", "Lillian", "Nora", "Zoey", "Mila",
    "Aubrey", "Hannah", "Lily", "Addison", "Eleanor", "Natalie", "Luna", "Savannah", "Brooklyn", "Leah",
    "Zoe", "Stella", "Hazel", "Ellie", "Paisley", "Audrey", "Skylar", "Violet", "Claire", "Bella",
    "Aurora", "Lucy", "Anna", "Samantha", "Caroline", "Genesis", "Aaliyah", "Kennedy", "Kinsley", "Allison",
    "Maya", "Sarah", "Madelyn", "Adeline", "Alexa", "Ariana", "Elena", "Gabriella", "Naomi", "Alice",
    "Sadie", "Hailey", "Eva", "Emilia", "Autumn", "Quinn", "Nevaeh", "Piper", "Ruby", "Serenity",
    "Willow", "Everly", "Cora", "Kaylee", "Lydia", "Aubree", "Arianna", "Eliana", "Peyton", "Melanie",
    "Gianna", "Isabelle", "Julia", "Valentina", "Nova", "Clara", "Vivian", "Reagan", "Mackenzie", "Madeline",
]
KID_GENERAL_M = [
    "Liam", "Noah", "William", "James", "Oliver", "Benjamin", "Elijah", "Lucas", "Mason", "Logan",
    "Alexander", "Ethan", "Jacob", "Michael", "Daniel", "Henry", "Jackson", "Sebastian", "Aiden", "Matthew",
    "Samuel", "David", "Joseph", "Carter", "Owen", "Wyatt", "John", "Jack", "Luke", "Jayden",
    "Dylan", "Grayson", "Levi", "Isaac", "Gabriel", "Julian", "Mateo", "Anthony", "Jaxon", "Lincoln",
    "Joshua", "Christopher", "Andrew", "Theodore", "Caleb", "Ryan", "Asher", "Nathan", "Thomas", "Leo",
    "Isaiah", "Charles", "Josiah", "Hudson", "Christian", "Hunter", "Connor", "Eli", "Ezra", "Aaron",
    "Landon", "Adrian", "Jonathan", "Nolan", "Jeremiah", "Easton", "Elias", "Colton", "Cameron", "Carson",
    "Robert", "Angel", "Maverick", "Nicholas", "Dominic", "Jaxson", "Greyson", "Adam", "Ian", "Austin",
    "Santiago", "Jordan", "Cooper", "Brayden", "Roman", "Evan", "Ezekiel", "Xavier", "Jose", "Jace",
    "Jameson", "Leonardo", "Bryson", "Axel", "Everett", "Parker", "Kayden", "Miles", "Sawyer", "Jason",
]
KID_HISPANIC_F = [
    "Sofia", "Camila", "Valentina", "Isabella", "Mia", "Emma", "Victoria", "Lucia", "Natalia", "Valeria",
    "Ximena", "Gabriela", "Daniela", "Mariana", "Elena", "Andrea", "Jimena", "Alexa", "Renata", "Regina",
    "Genesis", "Ashley", "Emily", "Kimberly", "Melanie", "Leah", "Luciana", "Catalina", "Abigail", "Ariana",
    "Allison", "Nicole", "Paola", "Fernanda", "Aylin", "Itzel", "Arely", "Yaretzi", "Dulce", "Esmeralda",
]
KID_HISPANIC_M = [
    "Mateo", "Santiago", "Sebastian", "Diego", "Daniel", "Leonardo", "Matias", "Gael", "Emiliano", "Angel",
    "Adrian", "Alexander", "Carlos", "Luis", "Jose", "Miguel", "Julian", "Nicolas", "Gabriel", "David",
    "Isaac", "Aiden", "Jayden", "Christopher", "Anthony", "Liam", "Noah", "Ethan", "Joshua", "Jesus",
    "Eduardo", "Javier", "Fernando", "Ivan", "Andres", "Rafael", "Ricardo", "Alejandro", "Jorge", "Emmanuel",
]
KID_ASIAN_HERITAGE_F = [
    "Mei", "Ananya", "Aanya", "Priya", "Jia", "Yuna", "Hana", "Linh", "Mai", "Anh",
    "Seo-yeon", "Ji-woo", "Sakura", "Aiko", "Diya", "Isha", "Kavya", "Xinyi", "Ying", "Thao",
]
KID_ASIAN_HERITAGE_M = [
    "Arjun", "Rohan", "Aarav", "Vihaan", "Kenji", "Haruto", "Minh", "Bao", "Duc", "Wei",
    "Jun", "Hao", "Min-jun", "Ji-ho", "Ren", "Kai", "Dev", "Ishaan", "Tuan", "Quang",
]

# --- Adults ---------------------------------------------------------------------

ADULT_HISPANIC_F = [
    "Maria", "Ana", "Rosa", "Guadalupe", "Veronica", "Alejandra", "Claudia", "Patricia", "Leticia", "Adriana",
    "Gabriela", "Elizabeth", "Monica", "Yesenia", "Araceli", "Martha", "Laura", "Diana", "Brenda", "Karina",
    "Sandra", "Norma", "Silvia", "Blanca", "Lorena", "Angelica", "Erika", "Jessica", "Marisol", "Cristina",
]
ADULT_HISPANIC_M = [
    "Jose", "Juan", "Luis", "Carlos", "Jorge", "Miguel", "Francisco", "Antonio", "Jesus", "Alejandro",
    "Manuel", "Ricardo", "Eduardo", "Roberto", "Fernando", "Javier", "Sergio", "Mario", "Raul", "Oscar",
    "Ruben", "Arturo", "Hector", "Victor", "Daniel", "Martin", "Pedro", "Salvador", "Armando", "Ramon",
]
ADULT_ASIAN_F = [
    "Linh", "Thuy", "Hoa", "Mai", "Lan", "Mei", "Li", "Hui", "Yan", "Jing",
    "Priya", "Anjali", "Neha", "Pooja", "Sunita", "Ji-yeon", "Soo-jin", "Min-ji", "Yuki", "Keiko",
    "Grace", "Jennifer", "Michelle", "Christine", "Amy", "Joy", "Maricel", "Rowena", "Jasmine", "Cecilia",
]
ADULT_ASIAN_M = [
    "Minh", "Tuan", "Hung", "Dung", "Long", "Wei", "Jian", "Hao", "Lei", "Ming",
    "Raj", "Vikram", "Sanjay", "Amit", "Rahul", "Sung-min", "Jae-hyun", "Dong-hyun", "Hiroshi", "Takeshi",
    "David", "Kevin", "Eric", "Andrew", "Jason", "Paolo", "Rommel", "Jerome", "Marvin", "Daniel",
]

# --- Surnames -------------------------------------------------------------------

# Weighted roughly by US frequency among Hispanic households.
HISPANIC_SURNAMES = {
    "Garcia": 30, "Rodriguez": 26, "Martinez": 25, "Hernandez": 25, "Lopez": 24, "Gonzalez": 23,
    "Perez": 17, "Sanchez": 17, "Ramirez": 16, "Torres": 14, "Flores": 14, "Rivera": 13, "Gomez": 12,
    "Diaz": 12, "Cruz": 9, "Morales": 9, "Reyes": 9, "Gutierrez": 9, "Ortiz": 8, "Chavez": 8,
    "Ramos": 7, "Ruiz": 7, "Alvarez": 7, "Mendoza": 7, "Castillo": 6, "Jimenez": 6, "Vasquez": 6,
    "Moreno": 6, "Romero": 6, "Herrera": 6, "Medina": 5, "Aguilar": 5, "Vargas": 5, "Guzman": 5,
    "Mendez": 4, "Salazar": 4, "Soto": 4, "Delgado": 4, "Pena": 4, "Rios": 4, "Contreras": 4,
    "Sandoval": 4, "Guerrero": 4, "Estrada": 4, "Nunez": 3, "Navarro": 3, "Cortez": 3, "Dominguez": 3,
    "Valdez": 3, "Juarez": 3, "Luna": 3, "Ochoa": 3, "Cervantes": 3, "Ibarra": 3, "Rosales": 3,
    "Fuentes": 3, "Avila": 3, "Lara": 3, "Camacho": 3, "Espinoza": 3, "Zamora": 2, "Velasquez": 2,
    "Trujillo": 2, "Maldonado": 2, "Padilla": 2, "Acosta": 2, "Cabrera": 2, "Villanueva": 2,
    "Orozco": 2, "Solis": 2, "Barajas": 2, "Magana": 2, "Arellano": 2, "Quintero": 2, "Bautista": 2,
}
ASIAN_SURNAMES = {
    "Nguyen": 30, "Tran": 14, "Le": 10, "Pham": 8, "Huynh": 4, "Vo": 4, "Dang": 3, "Bui": 3,
    "Kim": 14, "Lee": 14, "Park": 8, "Choi": 4, "Jung": 3, "Kang": 3,
    "Chen": 12, "Wang": 10, "Li": 9, "Zhang": 8, "Liu": 7, "Wong": 9, "Chan": 6, "Huang": 6,
    "Lin": 6, "Wu": 5, "Yang": 5, "Lam": 4, "Ng": 3,
    "Patel": 14, "Shah": 5, "Singh": 8, "Kumar": 5, "Reddy": 3, "Gupta": 3, "Rao": 2, "Sharma": 3,
    "Santos": 6, "Dela Cruz": 4, "Bautista": 3, "Villanueva": 2, "Mendoza": 2, "Aquino": 2,
    "Tanaka": 2, "Nakamura": 2, "Yamamoto": 2, "Sato": 2,
}

_EN_SURNAMES = list(EnUS.last_names.keys())
_EN_SURNAME_W = list(EnUS.last_names.values())
_EN_F = list(EnUS.first_names_female.keys())
_EN_F_W = list(EnUS.first_names_female.values())
_EN_M = list(EnUS.first_names_male.keys())
_EN_M_W = list(EnUS.first_names_male.values())

# Names in Faker's en_US lists that read as off for a parent born ~1975-1995.
_ADULT_SKIP = {"Mildred", "Gertrude", "Ethel", "Bertha", "Edna", "Agnes", "Elmer", "Clarence", "Herbert"}


def _weighted(rng: random.Random, items, weights):
    return rng.choices(items, weights=weights, k=1)[0]


def _ranked(rng: random.Random, items: list[str]) -> str:
    """Pick from a popularity-ordered list, favoring the front (Zipf-ish)."""
    weights = [1.0 / (i + 4) for i in range(len(items))]
    return rng.choices(items, weights=weights, k=1)[0]


class NameBank:
    """Hands out names. Tracks surname use so no surname takes over the district."""

    def __init__(self, rng: random.Random, max_households_per_surname: int = 4):
        self.rng = rng
        self.max_per_surname = max_households_per_surname
        self.surname_households: dict[str, int] = {}

    def load_existing(self, household_surnames: list[str]) -> None:
        for s in household_surnames:
            self.surname_households[s] = self.surname_households.get(s, 0) + 1

    def release(self, surname: str) -> None:
        if self.surname_households.get(surname, 0) > 0:
            self.surname_households[surname] -= 1

    # -- surnames --
    def _draw_surname(self, group: str) -> str:
        rng = self.rng
        if group == "hispanic":
            return _weighted(rng, list(HISPANIC_SURNAMES), list(HISPANIC_SURNAMES.values()))
        if group == "asian":
            return _weighted(rng, list(ASIAN_SURNAMES), list(ASIAN_SURNAMES.values()))
        if group == "multiracial":
            pool = rng.choices(["en", "hispanic", "asian"], weights=[0.6, 0.25, 0.15])[0]
            return self._draw_surname(pool) if pool != "en" else _weighted(rng, _EN_SURNAMES, _EN_SURNAME_W)
        return _weighted(rng, _EN_SURNAMES, _EN_SURNAME_W)

    def surname(self, group: str, claim: bool = True) -> str:
        for _ in range(50):
            s = self._draw_surname(group)
            if self.surname_households.get(s, 0) < self.max_per_surname:
                break
        if claim:
            self.surname_households[s] = self.surname_households.get(s, 0) + 1
        return s

    # -- first names --
    def child_first(self, group: str, gender: str) -> str:
        rng = self.rng
        female = gender == "F" or (gender == "X" and rng.random() < 0.5)
        if group == "hispanic" and rng.random() < 0.7:
            return _ranked(rng, KID_HISPANIC_F if female else KID_HISPANIC_M)
        if group == "asian" and rng.random() < 0.35:
            return rng.choice(KID_ASIAN_HERITAGE_F if female else KID_ASIAN_HERITAGE_M)
        return _ranked(rng, KID_GENERAL_F if female else KID_GENERAL_M)

    def adult_first(self, group: str, female: bool) -> str:
        rng = self.rng
        if group == "hispanic" and rng.random() < 0.8:
            return rng.choice(ADULT_HISPANIC_F if female else ADULT_HISPANIC_M)
        if group == "asian" and rng.random() < 0.7:
            return rng.choice(ADULT_ASIAN_F if female else ADULT_ASIAN_M)
        for _ in range(20):
            n = _weighted(rng, _EN_F, _EN_F_W) if female else _weighted(rng, _EN_M, _EN_M_W)
            if n not in _ADULT_SKIP:
                return n
        return n

    def middle(self, group: str, gender: str) -> str:
        """Middle name: often an initial, sometimes blank, sometimes full."""
        r = self.rng.random()
        if r < 0.25:
            return ""
        name = self.child_first(group, gender)
        return name[0] if r < 0.75 else name
