"""CustomSlop word pools for weapon names and descriptions (data only; logic lives in names.py).

Rules for every entry: plain ASCII, no double quotes, no '%', '#', '*', '_', '`', '~', '{' or '}'
outside the {slot} markers, nothing about real people, nothing offensive. Pools are newline- or
'|'-separated strings so they stay easy to extend.
"""


def L(s, sep=None):
    """Split a pool string into a clean list (newline-separated unless sep is given)."""
    parts = s.split(sep) if sep else s.split("\n")
    return [p.strip() for p in parts if p.strip()]


def W(s):
    return s.split()


# ---------------------------------------------------------------------------------------------
# adjectives
ADJ = W("""
Abrasive Absentminded Adequate Aggressive Agreeable Airtight Alarming Ambitious Amphibious Antique
Apologetic Approximate Argumentative Armored Artisanal Assertive Atomic Audacious Austere Awkward
Backhanded Baffling Bargain Bashful Beefy Belligerent Bendy Bespoke Bewildered Bitter Blessed Blistering
Blunt Boisterous Bombastic Bootleg Borrowed Bouncy Brash Brazen Brittle Bubbling Bulletproof Bumbling
Burly Buttered Cantankerous Caramelized Careless Ceremonial Certified Charming Cheeky Chilly Chipper
Chrome Chunky Clammy Clandestine Clanky Classified Clumsy Coarse Collapsible Colossal Compact Competent
Complimentary Concussive Confident Confused Contraband Convenient Cordial Corrugated Cosmic Courteous
Cranky Crispy Crooked Crumbling Crusty Cryptic Curious Customary Dapper Daring Dazzling Decaf Decorative
Defective Defiant Deluxe Demure Dented Devious Diabolical Diligent Discount Disgruntled Dishonest
Disposable Dramatic Drowsy Dubious Dutiful Earnest Eccentric Economy Elastic Electric Elegant Emotional
Encrypted Enormous Ergonomic Erratic Excessive Exotic Expensive Experimental Explosive Fabulous Familiar
Fancy Fearless Feisty Feral Ferocious Festive Fickle Fiddly Fiendish Flaky Flamboyant Flimsy Fluffy
Forgetful Formal Fragrant Frantic Freelance Frosty Frugal Fussy Galvanized Generous Gentle Giddy Gilded
Glamorous Gleaming Glorious Gluttonous Gnarly Gourmet Graceful Grumpy Gullible Hasty Haunted Heirloom
Hefty Heroic Hesitant Hollow Homemade Honorary Hostile Humble Humid Hungry Hydraulic Hysterical Icy
Illegal Immaculate Impatient Impolite Improvised Incredible Indignant Industrial Inflatable Insistent
Insulted Intrepid Irate Irregular Itchy Jagged Jaunty Jittery Jolly Jumbo Kindly Knotty Laminated Lanky
Lavish Lawful Leaky Lethargic Limited Lopsided Loyal Lucky Lumpy Luxurious Magnetic Majestic Malicious
Marinated Meddling Melancholy Mellow Menacing Merciless Mighty Miniature Mischievous Modest Moody
Mysterious Naughty Nervous Nimble Noisy Nostalgic Notorious Novelty Obedient Obnoxious Obsolete
Obstinate Odorless Official Ominous Opinionated Optimistic Ornery Outlandish Overbearing Overcooked
Overdue Overpriced Padded Pampered Paranoid Peculiar Peevish Perfumed Perky Persistent Petty Pickled
Pious Plucky Pneumatic Pocket Polished Polite Pompous Portable Precarious Precious Pristine Probationary
Prodigal Prudent Puny Punctual Questionable Quiet Quirky Radiant Radioactive Raggedy Rambunctious
Rattling Reckless Recycled Refurbished Regal Reluctant Remorseful Rented Resentful Restless Retired
Rickety Righteous Rowdy Rubbery Rugged Rustic Rusty Salty Sarcastic Savage Scalding Scrappy Secondhand
Serene Shabby Sheepish Shifty Shiny Shoddy Silky Sinister Sizzling Skeptical Slippery Sloppy Smug
Sneaky Soggy Solemn Sophisticated Sparkling Spiteful Spooky Sprightly Squeaky Stately Steadfast Sticky
Stoic Stormy Stubborn Stylish Suave Subpar Sulking Surly Suspicious Swanky Tactical Tacky Tangy Tardy
Tasteful Tenacious Tender Testy Thrifty Ticklish Timid Tired Tireless Touchy Tragic Treacherous
Trembling Trusty Turbulent Unbothered Uncanny Undercover Underpaid Unflappable Unhinged Unlicensed
Unruly Unsanctioned Unwashed Upbeat Vengeful Venerable Vicious Vigilant Vindictive Vintage Volatile
Voracious Wary Wasteful Weary Wheezing Whimsical Wicked Wiggly Wistful Witty Wobbly Wonky Worried
Wrathful Zealous Zesty
""")

# joke adjectives used with household objects ("The Load-Bearing Teapot")
JOKE_ADJ = L("""
Load-Bearing|Tax-Deductible|Dishwasher-Safe|Gluten-Free|Family-Sized|Battle-Tested|Unbreakable|
Pre-Owned|Factory-Sealed|Hand-Knitted|Self-Aware|Military-Grade|Doctor-Approved|Union-Built|
Microwave-Safe|Machine-Washable|Sugar-Free|Fully-Insured|Court-Ordered|Award-Winning|
Hypoallergenic|Biodegradable|Child-Proof|Bulletproof|Haunted|Weaponized|Overclocked|Regulation|
Load-Tested|Mail-Order|Kitchen-Tested|Grandma-Certified|Non-Refundable|Gift-Wrapped|Lightly-Salted""", "|")

# ---------------------------------------------------------------------------------------------
# nouns by weapon kind (names.kind_of maps an item class to one of these keys)
KIND_NOUN = {
    "rocket": W("""Launcher Rocketeer Skypiercer Boomtube Rocketry Ordnance Bombard Mortar Howitzer Bazooka
        Stovepipe Payload Airmail Liftoff Countdown Crater-Maker Skyhook Barrage Salvo Detonator Flinger
        Hurler Lobber Bombardier Siege-Tube Blastpipe Missileer Warhead Trebuchet Catapult Deliverer
        Booster Ignition Thrustmaster Flare-Tube Launchpad Rocketbox Rumbler Doomsayer Air-Strike"""),
    "grenade": W("""Lobber Tosser Pitcher Bouncer Grenadier Bomblet Pineapple Mortar Chucker Kegger
        Demolisher Fuse Satchel Firecracker Charge Bundle Powderkeg Pipe-Dream Detonator Bouncebomb
        Rebounder Skipper Ricochet Hand-Cannon Shellshocker Blastcap Tumbler Dropper Roller Plunger
        Sticky-Wicket Trapdoor Doorknocker Wallop Kaboomerang Party-Favor Gift-Box"""),
    "minigun": W("""Minigun Chaingun Gatling Spinner Buzzsaw Lawnmower Shredder Thresher Woodchipper
        Hailstorm Downpour Typewriter Sewing-Machine Bullet-Hose Carousel Turbine Rotary Grinder
        Avalanche Blender Mulcher Tornado Cyclone Whirlwind Gristmill Leadstorm Zipper Rattler
        Juggernaut Locomotive Steamroller Bulldozer Thunder-Wagon Harvester Combine Squall"""),
    "flame": W("""Flamethrower Scorcher Torch Blowtorch Furnace Kiln Bonfire Hearth Inferno Flambe Toaster
        Roaster Broiler Smoker Griller Barbecue Campfire Sizzler Fireplace Boiler Firebrand Pyre
        Dragonbreath Hothouse Heatwave Sauna Wildfire Brazier Crematorium Blaze Ember Tinderbox
        Ignition Sunburn Stove Charcoal"""),
    "flare": W("""Flaregun Signal Beacon Sparkler Firework Lighthouse Distress-Call Flash Starburst Comet
        Shooting-Star Roman-Candle Lantern Matchstick Glowstick Torchlight Nightlight Bottle-Rocket"""),
    "shotgun": W("""Scattergun Boomstick Blunderbuss Shotgun Spreader Peppergun Buckshot Sawed-Off Scatterer
        Double-Barrel Thunderclap Doorbuster Riot-Gun Coach-Gun Street-Sweeper Bird-Gun Duck-Hunter
        Pellet-Pusher Sprayer Hand-Cannon Breacher Trench-Gun Porch-Guard Lever-Action Pump-Action
        Shell-Slinger Persuader Doorknocker Thunderstick Scatterbrain Broadside Grapeshot"""),
    "pistol": W("""Pistol Revolver Six-Shooter Peacemaker Sidearm Derringer Pocket-Rocket Handgun Snub-Nose
        Equalizer Pea-Shooter Popgun Hand-Cannon Holdout Duelist Gunslinger Quickdraw Iron Heater
        Persuader Lead-Pusher Hogleg Ace Wheelgun Smokewagon Shootin'-Iron Mule Pocket-Piece"""),
    "smg": W("""Submachine Chatterbox Typewriter Buzzer Stutterer Burp-Gun Rattletrap Spitfire Sprayer
        Hornet Wasp Woodpecker Jackhammer Riveter Stapler Machine-Pistol Bullet-Hose Hailmaker
        Zipgun Clatterer Tommy Grease-Gun Drumfire Peppermill"""),
    "needle": W("""Syringe-Gun Needler Injector Inoculator Dart-Gun Booster-Shot Hypodermic Prescription
        Vaccinator Pincushion Acupuncturist Porcupine Hedgehog Nailgun Riveter Stapler Tetanus-Shot
        Prickler Sewing-Kit Dispensary Pharmacist"""),
    "rifle": W("""Rifle Longshot Marksman Sharpshooter Bolt-Action Scope Sightline Crosshair Headhunter
        Sniper Eagle-Eye Farsight Telescope Spyglass Longarm Bullseye Long-Distance Range-Finder
        Watchtower Lookout Overwatch Varmint-Gun Elephant-Gun Hunting-Rifle Single-Shot Deadeye"""),
    "bow": W("""Longbow Shortbow Crossbow Recurve Quiver Fletcher Archer Bowstring Arrowhead Yew Bowman
        Toxophilite Twanger Stringer Volley Huntsman Woodsman Hunter Ranger Trapper Outdoorsman"""),
    "blunt": W("""Bat Club Cudgel Bludgeon Mallet Maul Truncheon Shillelagh Billy Knobkerrie Sledge Hammer
        Gavel Paddle Whacker Thumper Bonker Basher Smacker Clobberer Walloper Thwacker Pummeler
        Crowbar Wrench Spanner Shovel Spade Pan Rolling-Pin Baton Nightstick Two-By-Four Plank
        Lead-Pipe Tenderizer Knuckleduster Thumb-Tack Doorstop Paperweight"""),
    "blade": W("""Blade Knife Dagger Stiletto Shiv Kukri Machete Cleaver Hatchet Axe Tomahawk Sabre
        Cutlass Scimitar Katana Claymore Broadsword Rapier Scalpel Bonesaw Hacksaw Letter-Opener
        Butterknife Carver Slicer Dicer Chopper Splitter Whittler Filleter Pruner Sickle Scythe
        Pizza-Cutter Razor"""),
}
KIND_NOUN["generic"] = W("""Contraption Apparatus Device Instrument Implement Mechanism Gadget Gizmo Doohickey
    Whatsit Thingamabob Widget Machine Engine Persuader Negotiator Mediator Diplomat Ambassador Liquidator
    Equalizer Annihilator Obliterator Eraser Rectifier Adjuster Calibrator Regulator Pacifier Clarifier
    Resolver Enforcer Arbiter Convincer Motivator Reminder Notifier Explainer Settler Problem-Solver
    Icebreaker Conversation-Starter Peacekeeper Troublemaker Homewrecker Showstopper Heartbreaker""")

# household objects for deliberate joke names
HOUSE = W("""Teapot Kettle Toaster Blender Colander Ladle Spatula Whisk Crockpot Waffle-Iron Plunger Vacuum
    Umbrella Coat-Rack Hat-Stand Footstool Ottoman Lampshade Bread-Bin Cheese-Grater Garden-Gnome Birdbath
    Doormat Mailbox Weathervane Accordion Bagpipe Tuba Kazoo Banjo Harmonica Ocarina Glockenspiel Trombone
    Ukulele Metronome Typewriter Rolodex Filing-Cabinet Stapler Hole-Punch Fax-Machine Briefcase Tea-Cozy
    Pepper-Mill Salad-Spinner Gravy-Boat Fondue-Set Butter-Churn Egg-Timer Cuckoo-Clock Grandfather-Clock
    Bathtub Shower-Head Hot-Water-Bottle Rubber-Duck Snow-Globe Lava-Lamp Jukebox Bowling-Ball Croquet-Set
    Pogo-Stick Unicycle Wheelbarrow Mop-Bucket Feather-Duster Fly-Swatter Rocking-Chair Hammock""")

# agent-noun builder parts: "The Shin-Kicker", "The Lunch-Ruiner"
TARGET = W("""Shin Skull Knee Kneecap Elbow Ankle Molar Tooth Spine Rib Collarbone Ego Morale Lunch Weekend
    Picnic Birthday Payday Vacation Nap Hat Mustache Eyebrow Toupee Monocle Sentry Dispenser Teleporter
    Respawn Payload Intel Briefcase Overheal Uber Cloak Disguise Paperwork Pension Mortgage Warranty
    Patience Dignity Pride Composure Confidence Posture Hairdo Sandwich Grudge Rivalry Ceasefire Truce""")
AGENT = W("""Kicker Cracker Rattler Splitter Remover Ruiner Botherer Tickler Polisher Adjuster Inspector
    Auditor Wrecker Breaker Knocker Thumper Crusher Squasher Flattener Mangler Wrangler Tenderizer
    Rearranger Disturber Interrupter Canceller Spoiler Shaker Stirrer Tamer Taker Collector Snatcher
    Botcher Unmaker Undoer Corrector Reviser Editor Reformer Dismisser Persuader Pester""")

# coinages: root + suffix ("Kaboomulator")
ROOT = W("""Boom Bonk Splat Thwack Blast Zap Crunch Smack Whomp Fizz Kablam Clonk Zing Bash Wham Thud Crack
    Pow Zoom Whack Bop Clang Sizzle Fwoosh Thump Rumble Grumble Shred Scorch Smash Wallop Whiz Zork
    Bamf Twang Splorch Kerplunk Snap Bang Dink Plink Bloop Wobble Jolt Spark Fumble Bungle""")
SUFFIX_COIN = W("""inator ulator omatic otron tastic ifier erizer anator zilla ster enator meister ola ington
    tron izer atron ulon icus orama izzle ernaut ifex omancer ophone omobile""")

# onomatopoeia ("Ka-Thunk", "The Kerploosh")
ONO = W("""Ka-Thunk Kerploosh Ka-Blam Ker-Splat Bzzzt Fwoomp Thwip Ka-Chunk Kerpow Blammo Ka-Boom Thwump
    Whumpf Ker-Rack Ptang Splut Glorp Kachow Brrrap Thunk Ping Krakoom Ka-Ching Vwoom Shhhk Dooomph
    Clink-Clank Rat-a-Tat Pop-Pop Bonk-Bonk Zwip Fsssh Kerchunk Whirr Clunk Plonk Sproing Boing Ker-Thud""")

# ---------------------------------------------------------------------------------------------
# people / places / companies (fictional TF2 / TF2C universe only)
LORE_OWNER = L("""
The Administrator|Miss Pauling|Saxton Hale|Merasmus|Gray Mann|Blutarch|Redmond|Zepheniah|Radigan Conagher|
Bidwell|Archimedes|Monoculus|The Horseless Headless Horsemann|Barnabus Hale|Elizabeth Mann|Zhanna|
Big Earl|The Bombinomicon|The Civilian|
The Spy's Mother|The Scout's Mom|Sniper's Dad|Soldier's Landlord|Demo's Mum|Medic's Dove|Heavy's Sisters|
Engineer's Grandpappy|Pyro's Imaginary Friend|The Intern|Mister Mercenary|The Night Watchman|
The Quartermaster|The Respawn Technician|The Announcer|The Ammo Clerk|The Resupply Cabinet
""", "|")
FIRST_NAME = W("""Barbara Gary Linda Doug Phil Tony Brenda Clive Nigel Bruce Sheila Mavis Doris Rupert Agnes
    Bernard Cyril Edna Ethel Fergus Gladys Harold Hilda Ignatius Irma Jasper Kermit Lionel Marge Mildred
    Norbert Olive Percival Prudence Quentin Rosalind Stanley Thelma Ulysses Vernon Wilma Winifred Yolanda
    Zelda Bartholomew Cornelius Dolores Eugene Florence Gertrude Horace Imogen Jebediah Lorna Montgomery
    Nadine Oswald Penelope Reginald Sybil Theodore Ursula Wendell Archibald Beatrice Clarence Desmond""")
RELATION = W("""Uncle Aunt Cousin Grandma Grandpa Landlord Neighbor Dentist Accountant Barber Godmother
    Stepbrother Roommate Pen-Pal Babysitter Mailman Optometrist Chiropractor Bowling-Coach Probation-Officer
    Tax-Advisor Therapist Ex-Partner Stunt-Double Understudy Biographer Nemesis""")
OCCUPATION = W("""Dentist Lumberjack Accountant Mime Plumber Locksmith Beekeeper Librarian Auctioneer Tailor
    Chimney-Sweep Notary Butcher Cobbler Fishmonger Lighthouse-Keeper Taxidermist Clockmaker Milkman
    Undertaker Bellhop Dogcatcher Sommelier Ventriloquist Zookeeper Stagehand Lifeguard Crossing-Guard
    Hall-Monitor Bailiff Pharmacist Groundskeeper Projectionist""")
PLACE = L("""
Badwater|Teufort|Dustbowl|Gravel Pit|Granary|Well|Hydro|Upward|Thunder Mountain|Frontier|Sawmill|
Harvest|Coldfront|Gorge|Mann Manor|Mannhattan|Hightower|Doomsday|Junction|Cactus Canyon|Ashville|
Badlands|Lumberyard|Viaduct|Powerhouse|Barnblitz|Gold Rush|Hoodoo|Turbine|Steel|Egypt|Fastlane|
Freight|Yukon|Nucleus|Swiftwater|Borneo|Snowycoast|Mountain Lab|Foundry|Process|Snakewater|
Brickyard|Mossrock|Sunshine|Cascade|Mercenary Park|Brimstone|Bigrock|Hellstone|Teufort Bay|
New Mexico|Mann Co. HQ|the Gravel Wars|the Respawn Room|the Supply Closet|the Spawn Gate|the Sewers|
the Payload Cart|the Intel Room|the Basement|the Lost and Found|the Break Room|the Mess Hall""", "|")
TEAM = W("RED BLU GRN YLW")
CLASSES_ALL = W("Scout Soldier Pyro Demoman Heavy Engineer Medic Sniper Spy Civilian")

MANUFACTURER = L("""
Mann Co.|Mann Co. Discount Division|Builders League United|Reliable Excavation Demolition|
TF Industries|Gray Gravel Co.|Gray Mann Robotics|Hale's Own|Saxton Outdoor Supply|Conagher Mechanics|
Merasmus Magic Shoppe|Teufort Tin Works|Badwater Hardware|Dustbowl Defense|Upward Ballistics|
Coldfront Cutlery|Mannhattan Manufacturing|Sawmill Sundries|Gravel Pit Gunsmiths|Hydro Hydraulics|
Frontier Fabrication|Thunder Mountain Tooling|Granary Goods|Hightower Holdings|Ashville Armaments|
Lumberyard Logistics|Viaduct Victuals|Powerhouse Products|Cactus Canyon Consumables|Egypt Engineering|
Bonk! Beverages|Mann Co. Labs|Mann Co. Clearance Bin|Respawn Supply Co.|Resupply Cabinet Inc.|
Payload Freight Lines|Intel Briefcase Corp.|Overtime Overstock|Sudden Death Supply|Setup Time Systems
""", "|")
BRAND_WORD = W("""Thermo Aero Hydro Electro Mega Ultra Hyper Turbo Omni Tri Mono Kilo Giga Robo Auto
    Dyna Astro Chrono Pyro Cryo Sono Magna Vibra Accu Opti Flexi Dura Strato Volt Atomo Tele Rapido""")
PRODUCT_WORD = W("""caster blaster matic master tron jet flex pulse line star force works lite plex wave
    beam core drive max shot fire pro sonic stream sphere vector""")
MODEL_TAG = W("""3000 9000 XL GT LX Pro Max Plus Deluxe Classic Supreme Turbo Lite Mini Jr. Sr. Ultra
    Prime Elite Custom Special SE Gold 2000 500 64 7 11 99""")
MIL_PREFIX = W("M XM Mk. Type Model Pattern No. MkII T Model-A Ordnance-QF Series")
ROMAN = W("II III IV V VI VII VIII IX X XI XII XIV XX")
YEAR = [str(y) for y in range(1850, 1975, 3)]

NICKNAME = W("""Housewarmer Peacemaker Widowmaker Doorbell Lullaby Alarm-Clock Wake-Up-Call Goodnight
    Handshake Welcome-Mat Farewell Last-Word Small-Talk Pep-Talk Lecture Sermon Eulogy Toast Pardon
    Rebuttal Footnote Postscript Encore Intermission Curtain-Call Overture Finale Punchline Plot-Twist
    Cliffhanger Spoiler Rerun Sequel Prequel Recap Epilogue Prologue Fine-Print Small-Print""")

# ---------------------------------------------------------------------------------------------
# curated whole names (each usable once ever; names.py checks history)
PUN_NAMES = L("""
The Shell Game|The Bonk Statement|The Cease and Desist|The Hostile Takeover|The Severance Package|
The Exit Interview|The Performance Review|The Second Opinion|The Last Resort|The Rude Awakening|
The Cold Shoulder|The Hot Take|The Pep Rally|The Plot Armor|The Loose Cannon|The Short Fuse|
The Final Notice|The Brute Force|The Blunt Instrument|The Pointed Remark|The Hard Bargain|
The Soft Launch|The Grand Opening|The Closing Argument|The Opening Statement|The Fine Print|
The Small Print|The Fire Sale|The Clearance Item|The Floor Model|The Open Box|The Return Policy|
The Buyer's Remorse|The Sunk Cost|The Burn Notice|The Tough Love|The Mixed Signal|
The Sore Loser|The Bad Influence|The Party Pooper|The Wet Blanket|The Dead Ringer|The Cheap Shot|
The Parting Gift|The Door Prize|The Booby Prize|The Consolation Prize|The Participation Trophy|
The Overtime Clause|The Setup Phase|The Cap Rate|The Point Blank|The Hard Counter|The Spawn Camper|
The Uber Driver|The Crit Happens|The Airblast From the Past|The Rocket Surgeon|The Sticky Situation|
The Pipe Dreamer|The Gun Show|The Shot in the Dark|The Spray and Pray|The Hit and Miss|
The Trigger Warning|The Barrel of Laughs|The Recoil Spring|The Hammer Time|The Nail Biter|
The Axe to Grind|The Bone to Pick|The Cut Above|The Edge Case|The Splitting Headache|
The Saw Loser|The Knife to Meet You|The Stab Wound Up|The Club Sandwich|The Bat Signal|
The Wrench in the Works|The Shovel Ready|The Grave Mistake|The Dig Deal|
The Flame War|The Heat Check|The Hot Potato|The Smoke Break|The Burnt Offering|The Toast of the Town|
The Flash in the Pan|The Rocket Science|The Blast Radius|The Boom Operator|The Fallout Shelter|
The Splash Zone|The Fuse Box|The Bang for Your Buck|The Lead Balloon|
The Bullet Point|The Bullet Journal|The Caliber of Excellence|The Magazine Subscription|
The Clip Show|The Reload Screen|The Ammo Dump|The Hail Mary|The Drive-By Compliment|
The Friendly Fire Drill|The Ceasefire Sale|The Truce Breaker|The Peace Offering|The Olive Branch|
The White Flag|The Neutral Party|The Conscientious Objector|The Draft Dodger|The Mercenary Spirit|
The Sudden Death|The Overtime Pay|The Respawn Wave|The Spawn Point|The Capture Point|The Control Point|
The Intelligence Test|The Payload Bearing|The Cart Before the Horse|The Medic Alert|The Doctor's Note|
The Sick Day|The House Call|The Bedside Manner|The Insurance Claim|The Co-Pay|The Deductible|
The Tax Bracket|The Write-Off|The Audit Trail|The Paper Trail|The Red Tape|The Blue Ribbon|
The Green Light|The Yellow Card|The Pink Slip|The Black Mark|The Grey Area|The Purple Prose
""", "|")

RHYME_NAMES = L("""
Hurty Gerty|Boom Broom|Smack Attack|Clang Thang|Thump Pump|Fright Light|Bash Stash|Whack Pack|
Pain Train|Ouch Pouch|Blam Clam|Zap Trap|Drill Thrill|Blight Kite|Crunch Lunch|Splat Hat|Bop Shop|
Gloom Loom|Shock Clock|Wreck Deck|Rattle Battle|Smash Cache|Bonk Honk|Spark Lark|Gash Sash|
Thwack Shack|Blast Mast|Flame Frame|Scorch Porch|Sting Ring|Woe Bow|Dread Sled|Rumble Bumble|
Tumble Rumble|Nifty Shifty|Hokey Smokey|Slammer Hammer|Clobber Cobbler|Whomper Stomper|
Rocket Pocket|Fuse Muse|Ember Remember|Doom Room|Kaboom Groom|Chop Shop|Slice Price|Hack Snack|
Bludgeon Smudgeon|Mangle Tangle|Squash Gosh|Bang Gang|Fizzle Drizzle|Sizzle Swizzle|
Ruckus Buckus|Ruffle Scuffle|Hustle Muscle|Wallop Dollop|Tickle Pickle|Wobble Gobble
""", "|")

PHRASE_NAMES = L("""
Not My Fault|Ask Me Later|Who Packed This|Nobody Told Me|Probably Fine|Worth a Shot|Just Visiting|
Hold My Hat|Trust Me|Back in Five|No Comment|Read the Manual|Mind the Gap|Sign Here|Seen Better Days|
Some Assembly|Pardon the Mess|Out of Office|Reply All|Per My Last Email|Do Not Disturb|
Wet Paint|Watch Your Step|Exact Change Only|Employees Must Wash Hands|Closed for Repairs|Under New Management|
Beyond Repair|One Careful Owner|As Is|Final Sale|Past Due|Return to Sender|Handle With Care|
This Side Up|Contents Under Pressure|Keep Out|Staff Only|Last Call|Lights Out|Doors Closing|
Mind Your Head|Thank You Come Again|Now Boarding|Running Late|Bless You|Gesundheit|Long Story|
Good Question|Fair Enough|Close Enough|Not Again|Nice Try|Oh Dear|Well Then|Fine Then|Big If True
""", "|")

PERSONA = L("""
The Tax Man|The Headmaster|The Landlord|The Auctioneer|The Referee|The Bouncer|The Undertaker|
The Notary|The Plumber|The Mortician|The Dentist|The Exterminator|The Bill Collector|The Repo Man|
The Hall Monitor|The Night Shift|The Substitute Teacher|The Middle Manager|The Shift Supervisor|
The Health Inspector|The Building Inspector|The Meter Maid|The Parking Ticket|The Jury Duty|
The Second Cousin|The Wedding Crasher|The Uninvited Guest|The Party Animal|The Life of the Party|
The Usual Suspect|The Prime Suspect|The Key Witness|The Expert Witness|The Character Witness|
The Understudy|The Stunt Double|The Body Double|The Opening Act|The Headliner|The Roadie|
The Lifeguard|The Crossing Guard|The Lollipop Lady|The Ice Cream Man|The Paperboy|The Milkman
""", "|")

ACRONYM_NAMES = L("""
The S.L.A.P.|The B.O.N.K.|The W.H.A.M.|The O.U.C.H.|The P.O.W.|The T.H.U.D.|The C.L.A.N.G.|
The B.L.A.M.|The Z.A.P.|The S.M.A.C.K.|The K.N.O.C.K.|The B.A.S.H.|The O.O.F.|The Y.E.O.W.|
The D.U.C.K.|The R.U.N.|The N.O.P.E.|The W.H.Y.|The H.U.H.|The O.H.N.O.|The G.U.L.P.|The E.E.K.
""", "|")

SEQUEL_FORM = L("""
Son of the {N}|Bride of the {N}|Return of the {N}|Revenge of the {N}|The {N} Strikes Back|
The {N} Returns|Curse of the {N}|Rise of the {N}|Night of the {N}|Attack of the {N}|
The {N} Reloaded|The {N} Begins|Beyond the {N}|The {N}: Director's Cut|The {N} Unrated|
The {N} Holiday Special|Escape From the {N}|The {N} Goes West|The {N} Abroad|Planet of the {N}""", "|")

OF_PHRASE = L("""
of Mild Inconvenience|of Questionable Origin|of Diminishing Returns|of Unreasonable Force|of Last Resort|
of Poor Decisions|of Lingering Regret|of Brief Glory|of Second Chances|of No Return|of Many Uses|
of the Fine Print|of the Third Shift|of the Lost and Found|of Overtime|of Sudden Death|
of Respawn|of Paperwork|of Polite Disagreement|of Strongly Worded Letters|of Accidental Heroism|
of Unpaid Leave|of Minor Prophecy|of the Ancients (Allegedly)|of the Bargain Bin|of Hurt Feelings|
of Bad Timing|of Good Intentions|of the Long Weekend|of Sincere Apology|of Hasty Exits|
of Loud Noises|of Small Victories|of Heated Debate|of Total Nonsense|of Hidden Fees|of the Damned (Lite)|
of Destiny (Pending)|of Plausible Deniability|of Collateral Damage""", "|")

MATERIAL = L("""
Brass|Tin|Cardboard|Porcelain|Bronze|Australium|Gold-Plated|Lead|Copper|Pewter|Cast-Iron|Wrought-Iron|
Balsa|Oak|Mahogany|Bamboo|Rubber|Plywood|Papier-Mache|Chrome|Nickel-Plated|Silver-Plated|Tungsten|
Ceramic|Wicker|Concrete|Granite|Marble|Obsidian|Cork|Duct-Taped|Glued-Together|Stitched|Laminated""", "|")

NUMBER_PART = L("""
Three-Barrel|Twelve-Gauge|Half-Pound|Two-Handed|Five-Alarm|Nine-Lives|Seven-League|Four-Star|
Ten-Gallon|Hundred-Proof|Single-Use|Double-Dipped|Triple-Threat|Quarter-Ton|Six-Pack|Eight-Ball|
One-Way|Zero-Tolerance|Eleventh-Hour|Thousand-Yard|Two-Faced|Four-Leaf|Second-Hand|Third-Rate""", "|")

ANIMAL = W("""Wombat Badger Mongoose Ferret Weasel Bandicoot Platypus Possum Raccoon Moose Walrus Goose
    Pelican Vulture Buzzard Hyena Jackal Warthog Armadillo Porcupine Hedgehog Beaver Otter Lynx Wolverine
    Bison Yak Ox Mule Donkey Rooster Turkey Emu Ostrich Kookaburra Dingo Koala Kangaroo Narwhal Squid
    Lobster Crab Mackerel Barracuda Piranha Eel Hornet Wasp Beetle Scorpion Tarantula Gecko Iguana
    Komodo Rattlesnake Cobra Mamba Bullfrog Toad Salamander Bear Grizzly Panda Gorilla Baboon Llama""")

# class dialect / flavour: prefix words and whole-name forms per TF2 class
CLASS_FLAVOR = {
    "Scout": dict(adj=W("Wicked Speedy Atomic Fast-Talking Bonk-Powered Boston Hustlin' Mouthy Double-Jumping Baseball"),
                  forms=L("The Wicked {N}|Ma's {N}|The Southie {N}|The Fenway {N}|The Big League {N}|The Home-Run {N}|The Bonk-a-{N}", "|")),
    "Soldier": dict(adj=W("Patriotic Freedom-Loving Regulation Drill-Sergeant Star-Spangled Decorated Honorable Shovel-Ready Liberty Eagle-Eyed"),
                    forms=L("The Freedom {N}|The Liberty {N}|Old Glory's {N}|The Medal of {N}|The Boot Camp {N}|General Issue {N}|The Purple Heart {N}", "|")),
    "Pyro": dict(adj=W("Mmmphing Rainbow Sparkly Cuddly Lollipop Bubblegum Giggling Candy-Coated Puffy Toasty"),
                 forms=L("The Mmmph {N}|The Rainbow {N}|The Pyroland {N}|The Lollichop {N}|Mister Sparkles' {N}|The Happy Little {N}|The Balloon {N}", "|")),
    "Demoman": dict(adj=W("Wee Braw Bonnie Canny Highland Tartan Glaswegian Kilted Blackpowder One-Eyed"),
                    forms=L("The Wee {N}|Ye Olde {N}|The Highland {N}|Bonnie Prince {N}|The Ullapool {N}|The Tartan {N}|The Loch {N}", "|")),
    "Heavy": dict(adj=W("Big Tiny Siberian Sandvich-Fed Hungry Mighty Bear-Sized Bear-Wrestling Borscht-Powered Tractor-Grade"),
                  forms=L("Little {F}|Big {F}|Cousin {F}|Babushka {F}|Comrade {N}|The Siberian {N}|The Sandvich {N}", "|")),
    "Engineer": dict(adj=W("Texas Ol' Lil' Darn Gol-Durn Hootenanny Grease-Stained Hard-Hat Frontier Homespun"),
                     forms=L("Ol' {N}|The Lil' {N}|The Texas {N}|The Hoedown {N}|Grandpappy's {N}|The Rodeo {N}|The Ranch {N}", "|")),
    "Medic": dict(adj=W("Clinical Sterile Uber Experimental Surgical Unlicensed Malpractice Teutonic Anesthetic Stitched"),
                  forms=L("Das {N}|Der {N}meister|The Uber-{N}|Doktor's {N}|The Kur {N}|The Sanitorium {N}|The Malpractice {N}", "|")),
    "Sniper": dict(adj=W("Fair-Dinkum Outback Strewth Bush-Bred Dinky-Di Jarate-Soaked Campervan Crikey Professional Billabong"),
                   forms=L("The Outback {N}|The Fair Dinkum {N}|The Billabong {N}|The Bush {N}|The Campervan {N}|The Kookaburra {N}|The Dingo {N}", "|")),
    "Spy": dict(adj=W("Elegant Disguised Cloaked Suave Debonair Duplicitous Parisian Two-Faced Silent Gentlemanly"),
                forms=L("Le {N}|L'Ami {N}|Monsieur {N}|The Parisian {N}|Le {N} Magnifique|The Cafe {N}|The Rendezvous {N}", "|")),
    "Civilian": dict(adj=W("Executive Gentleman's Tax-Exempt Expensive Pinstriped Bureaucratic Stockholder Board-Approved VIP Escorted"),
                     forms=L("The Executive {N}|The Gentleman's {N}|The Stockholder {N}|The VIP {N}|The Board Meeting {N}|The Briefcase {N}|The Umbrella {N}", "|")),
}
HEAVY_FEMALE = W("Olga Svetlana Tanya Katya Ludmila Irina Masha Galina Nadia Vera Oksana Zoya Yelena Raisa Dasha")

FOREIGN_FORMS = L("""
Der {G}macher|Das {G}werk|Le {N} Terrible|El {N} Grande|Il {N}ino|{L}us Maximus|{L}ium Ultimatum|
{L}a Magna|Herr {G}|La {N} Fantastique|El Gran {N}|Don {N}o|{G}enschlag|{G}hammer Deluxe|Mon Petit {N}""", "|")
GERMAN_ROOT = W("Knall Blitz Donner Schmerz Bumm Krach Schlag Feuer Wumms Klopf Rumpel Zisch Puff Stoss Kawumm")
LATIN_ROOT = W("Bonk Smack Thwack Whack Bash Splat Clang Thump Boom Wallop Crunch Wham Kablam Clonk Zapp")

TITLE = W("Sir Lord Lady Doctor Professor Captain Admiral Baron Duchess Count Colonel Reverend Judge Madam Major")
SURNAME_TAIL = W("worth ington bottom shire ley ton field ham wick by stone bury more brook hurst")

STAT_ADJ = {
    "damage": W("Bone-Rattling Heavy-Handed Overkill Skull-Splitting Wallop-Grade Devastating Brutal Punishing Hard-Hitting"),
    "firerate": W("Rapid Chattering Hasty Twitchy Hair-Trigger Caffeinated Restless Impatient Frenzied"),
    "clip": W("Bottomless Generous Overstuffed Well-Fed Roomy Hoarding Spacious Capacious"),
    "reload": W("Lethargic Leisurely Slowpoke Quick-Change Nimble-Fingered Sluggish Unhurried"),
    "ammo": W("Thrifty Stockpiling Bulk-Buy Rationed Frugal Prepper"),
    "fire": W("Toasty Smouldering Scorched Self-Immolating Kindling Sizzling Ember-Kissed Blistering"),
    "speed": W("Sprinting Fleet-Footed Jogging Zoomy Ambling Dawdling Brisk"),
    "health": W("Hearty Wholesome Vitamin-Enriched Nourishing Bandaged Convalescent Restorative"),
    "explosive": W("Volatile Blast-Happy Combustible Unstable Fizzing Megaton Earth-Shaking"),
    "crit": W("Critical Lucky Fortunate Jackpot Four-Leaf Charmed"),
    "knockback": W("Shoving Pushy Bouncy Repulsive Launching Assertive"),
    "defense": W("Armored Stalwart Thick-Skinned Padded Sturdy Unbudging"),
    "accuracy": W("Wobbly Precise Dead-Eyed Approximately-Aimed Scattered Pinpoint"),
    "mechanic": W("Misfiled Off-Brand Borrowed Misdelivered Repurposed Confused"),
    "plain": W("Ordinary Unremarkable Regulation Standard-Issue Factory-Default Middling"),
}
STAT_OF = {
    "damage": L("of Unreasonable Force|of Excessive Wallop|of Bad News|of Blunt Honesty", "|"),
    "firerate": L("of Too Many Bullets|of Short Attention Spans|of Itchy Trigger Fingers", "|"),
    "clip": L("of Endless Supply|of Overflowing Pockets|of Bottomless Magazines", "|"),
    "reload": L("of Eventual Readiness|of Fumbling Fingers|of Patient Waiting", "|"),
    "ammo": L("of the Ammo Crate|of Careful Rationing|of Bulk Purchases", "|"),
    "fire": L("of Third-Degree Burns|of the Burn Ward|of Spontaneous Combustion", "|"),
    "speed": L("of Hasty Exits|of the Fast Lane|of Leisurely Strolls", "|"),
    "health": L("of Good Health|of the Clinic|of the Second Wind", "|"),
    "explosive": L("of Big Booms|of Collateral Damage|of Rearranged Scenery", "|"),
    "crit": L("of Fortune|of Rolled Dice|of Lucky Breaks", "|"),
    "knockback": L("of Personal Space|of Sudden Departures|of Unplanned Flights", "|"),
    "defense": L("of Thick Skin|of Stubborn Survival|of Ignored Bullets", "|"),
    "accuracy": L("of Loose Aim|of Careful Aim|of Wild Guesses", "|"),
    "mechanic": L("of Somebody Else's Job|of Crossed Wires|of Misplaced Features", "|"),
    "plain": L("of the Usual|of Business as Usual|of Standard Procedure", "|"),
}
