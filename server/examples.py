"""Original demo texts (no real monologues: copyright, and nobody gets mocked) and audience presets.
Each example has references that split by age and place, so switching rooms visibly changes the result."""

TWO_ROOMS = [
    {"name": "Under 25s in London", "age": "24_and_younger", "gender": None, "location": "London"},
    {"name": "55+ in St. Louis", "age": "55_and_older", "gender": None, "location": "St. Louis"},
]

MARKETS = [
    {"name": "US, under 25", "age": "24_and_younger", "gender": None, "location": "United States"},
    {"name": "US, 55+", "age": "55_and_older", "gender": None, "location": "United States"},
    {"name": "UK, 45 to 54", "age": "45_to_54", "gender": None, "location": "United Kingdom"},
    {"name": "Texas, 35 to 44", "age": "35_to_44", "gender": None, "location": "Texas"},
    {"name": "India, 25 to 29", "age": "25_to_29", "gender": None, "location": "India"},
    {"name": "Brazil, 30 to 34", "age": "30_to_34", "gender": None, "location": "Brazil"},
]

TOUR = [
    {"name": "Leeds", "age": "25_to_29", "gender": None, "location": "Leeds"},
    {"name": "Glasgow", "age": "25_to_29", "gender": None, "location": "Glasgow"},
    {"name": "New York", "age": "25_to_29", "gender": None, "location": "New York"},
    {"name": "Atlanta", "age": "25_to_29", "gender": None, "location": "Atlanta"},
    {"name": "Austin", "age": "25_to_29", "gender": None, "location": "Austin"},
    {"name": "Toronto", "age": "25_to_29", "gender": None, "location": "Toronto"},
]

PRESETS = {
    "two_rooms": {"title": "Two rooms", "audiences": TWO_ROOMS},
    "markets": {"title": "Six markets", "audiences": MARKETS},
    "tour": {"title": "Tour: six cities, 25 to 29", "audiences": TOUR},
}

EXAMPLES = [
    {
        "id": "standup",
        "title": "Stand-up bit: moving back home",
        "kind": "comedy",
        "audience": {"age": "24_and_younger", "gender": None, "location": "London"},
        "matrix": TWO_ROOMS,
        "text": (
            "So I moved back in with my parents. Their Wi-Fi password is still the name of the dog that died when I was nine.\n"
            "My dad watches Seinfeld every night like it's the news. He laughs before the joke, like he's reminding the TV how it goes.\n"
            "My mum's idea of a wild Friday is a Blockbuster card she never returned. She keeps it in her purse like a medal.\n"
            "I tried to explain Fortnite to them and my dad asked if it was 'one of those MySpace things'.\n"
            "Meanwhile my little cousin has never heard a dial tone. She thinks a Nokia is a type of pasta.\n"
            "We compromised and watched Friends. Ninety minutes of six people who can afford a Manhattan flat with no visible jobs. Fantasy genre."
        ),
    },
    {
        "id": "ad",
        "title": "Ad script: budget airline, 30 seconds",
        "kind": "ad",
        "audience": {"age": "45_to_54", "gender": None, "location": "Texas"},
        "matrix": MARKETS,
        "text": (
            "You remember when flying felt like a Taylor Swift tour: expensive, loud, and somehow still sold out.\n"
            "We think flying should feel more like Minecraft. You build the trip you want, block by block.\n"
            "No hidden fees. No drama. Just you, a window seat, and a playlist that isn't Coldplay for once.\n"
            "Skyline Air. Less Succession, more Ted Lasso."
        ),
    },
    {
        "id": "tour",
        "title": "Touring comic: one opener, six cities",
        "kind": "tour",
        "audience": {"age": "25_to_29", "gender": None, "location": "Leeds"},
        "matrix": TOUR,
        "text": (
            "Good to be back on the road. I've been living off Greggs and service-station coffee for a week.\n"
            "My tour manager plans everything on Google Maps and still got us lost looking for a Wetherspoons.\n"
            "Last night the whole crowd sang Mr. Brightside louder than I could do my closer.\n"
            "Tonight I'm told this room only goes quiet for The Great British Bake Off."
        ),
    },
    {
        "id": "speech",
        "title": "Toast: best man speech",
        "kind": "speech",
        "audience": {"age": "55_and_older", "gender": None, "location": None},
        "text": (
            "I met Dan in 2009. He was wearing a Hollister hoodie and quoting The Hangover like scripture.\n"
            "Sixteen years later he has a mortgage, a Peloton he uses as a coat rack, and a Spotify Wrapped he refuses to show anyone.\n"
            "Emma, you've turned a man who once ate a Domino's in a Lidl car park into someone who owns a Le Creuset.\n"
            "To Dan and Emma: may your love last longer than Game of Thrones stayed good."
        ),
    },
]
