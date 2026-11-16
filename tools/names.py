"""CustomSlop name + description library (prototype). Deterministic per RNG; ~10^6 combinations."""

ADJ = """Epic Cursed Haunted Discount Questionable Illegal Soggy Volcanic Feral Unlicensed Bootleg Deluxe
Rusty Gilded Spicy Moist Ancient Overclocked Underpaid Sentient Tactical Ceremonial Experimental
Forbidden Homemade Patriotic Suspicious Industrial Artisanal Prototype Refurbished Radioactive Lukewarm
Unstable Overcooked Damp Gnarly Righteous Wobbly Electric Expired Bargain Premium Sacred Profane
Crunchy Smoky Glorious Mediocre Unholy Holy Dubious Frantic Lazy Polite Rude Furious Cozy Grim Jolly
Mysterious Notorious Infamous Legendary Mythical Disposable Reusable Collapsible Inflatable Ergonomic
Vintage Futuristic Retro Medieval Cosmic Atomic Thermal Arctic Tropical Swampy Dusty Greasy Shiny Dull
Loud Silent Screaming Whispering Weeping Laughing Sleepy Caffeinated Decaf Organic Synthetic Mechanical
Hydraulic Pneumatic Steam-Powered Diesel Clockwork Counterfeit Certified Uncertified Probationary
Honorary Tenured Freelance Corporate Municipal Federal Provincial Regional Bespoke Mass-Produced""".split()

NOUN = """Gun Blaster Boomstick Peashooter Cannon Launcher Shooter Thumper Popper Splatter Rifle Repeater
Musket Blunderbuss Sprayer Spitter Hose Mangler Masher Basher Bonker Whacker Thwacker Slapper Swatter
Persuader Negotiator Mediator Diplomat Ambassador Liquidator Equalizer Annihilator Obliterator Eraser
Rectifier Adjuster Calibrator Regulator Compressor Distributor Dispenser Delivery Solution Argument
Opinion Grievance Complaint Lawsuit Invoice Receipt Warranty Refund Rebate Coupon Voucher Subpoena
Kettle Teapot Toaster Blender Vacuum Plunger Spatula Ladle Whisk Colander Crockpot Waffle-Iron
Trombone Kazoo Accordion Bagpipe Tuba Banjo Harmonica Ocarina Didgeridoo Glockenspiel
Hammer Wrench Spanner Crowbar Shovel Rake Hoe Pitchfork Mallet Gavel Scepter Baton Truncheon Cudgel
Contraption Gizmo Gadget Doohickey Thingamajig Whatsit Apparatus Device Machine Engine Reactor""".split()

OWNER = """Uncle Shooter|Grandma|The Administrator|Merasmus|Saxton|Gray Mann|Blutarch|Redmond|Big Earl|Dell|
Miss Pauling|Zhanna|Sniper's Dad|Archimedes|Bombinomicon|The Civilian|Mister Mercenary|The Intern|
Accounting|Legal|HR|Quality Assurance|The Night Shift|Sergeant Pepper|Doctor Pain|Professor Boom|
Captain Obvious|Old Man Jenkins|Little Timmy|Cousin Greg|Aunt Mildred|The Mailman|The Plumber|
Dave from Marketing|Steve|Kevin|Barbara|Gary|Linda|Doug|Phil|Tony|Brenda|Clive|Nigel|Bruce|Sheila""".replace("\n", "").split("|")

SUFFIX = """Mk. II|Deluxe|Supreme|Lite|Pro|Max|Ultra|Jr.|Sr.|of Doom|of Mild Inconvenience|of Destiny|
of the Damned|of Questionable Origin|2: Electric Boogaloo|(Unrated)|(Director's Cut)|XL|9000|Classic|
Remastered|Turbo|Plus|Gold Edition|Prototype|Beta|v0.1|Final Final|Redux|Reloaded""".replace("\n", "").split("|")

PATTERNS = ["The {Adj} {Noun}", "{Owner}'s {Noun}", "The {Adj} {Noun} {Suffix}", "{Owner}'s {Adj} {Noun}",
            "The {Noun}-{Noun2}", "The {Adj} {Noun}-{Noun2}", "{Adj} {Noun} {Suffix}", "The {Noun} {Suffix}"]

QUIPS = ["It's fine.", "Do not taste.", "Tested on interns.", "No refunds.", "Assembled by committee.",
         "Some assembly required.", "Batteries not included.", "Now with 40% more regret.",
         "Approved by nobody.", "Smells faintly of {smell}.", "Found it behind the {place}.",
         "Contains small parts.", "Do not operate while {state}.", "Patent pending.", "As seen on TV.",
         "The {Owner} special.", "Forged in a {place}.", "It was like this when I got here.",
         "Warranty void if used.", "Handle with oven mitts.", "Previously owned by {Owner}."]
SMELL = ["burnt toast", "gunpowder", "wet dog", "pennies", "regret", "cheap cologne", "ozone", "cabbage"]
PLACE = ["fridge", "couch", "respawn room", "dumpster", "volcano", "gift shop", "sewer", "sawmill"]
STATE = ["sleepy", "on fire", "underwater", "a Scout", "in love", "taxed", "airborne"]

TRAIT_LINES = {
    "self_ignite": ["Sets you on fire. On purpose.", "Comes pre-ignited.", "Runs hot."],
    "ignite": ["Sets enemies on fire, which is the point.", "Spicy on contact."],
    "tiny_clip": ["One bullet. Make it count.", "Clip sold separately."],
    "slow_reload": ["Takes forever to reload.", "Reloading is more of a lifestyle."],
    "fast": ["Fires faster than it should.", "Trigger discipline not included."],
    "slow": ["Fires whenever it feels like it.", "Patience is a virtue."],
    "big_damage": ["Hits like a truck.", "Overkill is underrated."],
    "weak": ["Mostly decorative.", "Hurts feelings, mostly."],
    "low_reserve": ["Ammo is a luxury.", "Bring your own ammo."],
    "odd_projectile": ["Fires {proj}.", "Ammunition: {proj}. Don't ask."],
    "wrong_class": ["Not meant for {cls}. Don't tell anyone.", "{cls}-compatible (allegedly)."],
}


def make_name(rng, used):
    for _ in range(200):
        p = rng.choice(PATTERNS)
        n2 = rng.choice(NOUN)
        nm = p.format(Adj=rng.choice(ADJ), Noun=rng.choice(NOUN), Noun2=n2, Owner=rng.choice(OWNER).strip(),
                      Suffix=rng.choice(SUFFIX).strip())
        if nm.lower() not in used and len(nm) <= 40:
            used.add(nm.lower())
            return nm
    raise RuntimeError("name space exhausted")


def make_description(rng, traits, ctx):
    lines = []
    for t in traits:
        if t in TRAIT_LINES:
            lines.append(rng.choice(TRAIT_LINES[t]).format(**ctx))
    q = rng.choice(QUIPS).format(Owner=rng.choice(OWNER).strip(), smell=rng.choice(SMELL),
                                 place=rng.choice(PLACE), state=rng.choice(STATE))
    rng.shuffle(lines)
    out = " ".join(lines[:2] + [q])
    return out[:200]


def combinations():
    return len(PATTERNS) * len(ADJ) * len(NOUN) * max(len(OWNER), len(SUFFIX))
