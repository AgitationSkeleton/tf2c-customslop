"""CustomSlop description fragments (data only; names.py builds descriptions from these).

Slots: {Name} weapon name, {cls} the weapon's class, {other} another class, {kind} plain weapon kind
("rocket launcher"), {Place}, {Team}, {Maker}, {Year}, {First}, {Relation}, {Occupation}, {Animal},
{House}, {Num}. Same character rules as namewords.py (ASCII, no double quotes/%/#/markdown).
"""
from namewords import L

QUIPS = L("""
It's fine. Probably.
Tested on interns. The interns are fine.
Approved by a committee of one.
It was like this when we found it.
Warranty void if used for its intended purpose.
Handle with oven mitts.
Smells faintly of burnt toast and ambition.
Found behind the couch in the {Place} break room.
Contains small parts and large consequences.
Patent pending since {Year}.
As seen on late-night Mann Co. television.
Nobody remembers ordering this.
Comes with a strongly worded instruction manual.
Ages like milk.
Assembled during a lunch break.
Recalled twice. Returned both times.
The receipt is longer than the barrel.
Previously owned by a very nervous {Occupation}.
Ships in a box marked FRAGILE, ironically.
Mostly harmless to the user.
Now with fewer sharp edges than last year.
Even the box looks worried.
Built to last until Thursday.
It hums when nobody is looking.
Polished nightly by someone who cares too much.
Has a name tag. The name has been scratched out.
Still has the price sticker on it.
Was a {House} in a previous life.
Makes a noise like a disappointed {Animal}.
Someone engraved the word MAYBE on the side.
The safety is purely decorative.
Smells like a new car and an old argument.
Shake well before use. Do not shake during use.
Includes one complimentary sense of dread.
Free shipping on orders of three or more regrets.
Got lost in the mail for {Num} years and came back angrier.
Signed by the whole {Place} night shift.
The paint is still wet. It has been wet since {Year}.
Do not leave unattended near a {other}.
Reliable, in the way that weather is reliable.
Recommended by four out of five people who were asked twice.
The serial number is just the word NO.
Squeaks when happy.
Better than nothing. Narrowly.
Cleans up nicely, unlike its victims.
One previous owner. He is fine now.
Fits in most glove compartments and some lunchboxes.
Certified fresh by an uncertified inspector.
It came with a goldfish. Nobody knows why.
Do not feed after midnight.
Has never once lost an argument.
Comes in any colour you like, as long as it is this one.
Holds a grudge against the {Team} team specifically.
The previous model was better. This one is cheaper.
The manual is in a language nobody speaks.
Tastes worse than it looks. Please stop tasting it.
Quietly judges everyone in the respawn room.
Refurbished, in the loosest sense of the word.
If found, please return to the {Place} lost and found.
Will not fit in the resupply cabinet. Do not try.
Sounds expensive. Is not.
Gift-wrapped by someone who did not want to give it.
Waterproof up to roughly a damp afternoon.
Rated E for Eventually.
Every one is hand-inspected by a very tired {Animal}.
Rumoured to be cursed. Confirmed to be sticky.
It was a gift. Nobody admits to giving it.
Do not ask what the third button does.
Discovered at a garage sale in {Place}.
Batteries were included. They have since escaped.
Fully compatible with your bad decisions.
The instructions just say GOOD LUCK.
Smells like victory, and also a little like cabbage.
Bigger on the inside. Do not look inside.
Bought in bulk. Regretted in bulk.
Grandfathered into the rules by a clerical error.
Technically a family heirloom.
Gets along with everyone except the {other}.
The last one is still on back order.
Built from parts of three other, better weapons.
A favourite at birthday parties nobody returns from.
Contains no artificial flavours. Contains other things.
Insert coin to continue.
The handle was redesigned after the incident.
Every scratch has a story. Most stories end badly.
Shipped by mistake. Kept on purpose.
Engineered for excellence, built for budget.
It whistles a tune nobody recognises.
Made in {Place} by people who should know better.
Sold as seen, seen as sold.
Nobody has read the terms and conditions.
""")

WARN_LABEL = L("""
WARNING:|Caution:|Note:|Disclaimer:|Safety tip:|Reminder:|Legal notice:|Fine print:|Advisory:|Heads up:|
Important:|Please note:|Attention:|Notice:|Mann Co. advises:|Safety first:|
Legal says:|Small print:|PSA:|Friendly reminder:""", "|")
WARNINGS = L("""
do not operate while on fire.
not intended for use as a toothbrush.
keep away from children, pets and {otherP}.
do not point at face, yours or anyone else's.
may cause drowsiness in nearby enemies, permanently.
not responsible for lost hats.
objects in the scope are closer than they appear.
contents may have shifted during respawn.
do not use as a flotation device. We checked.
side effects include winning, losing and mild ringing.
not dishwasher safe, despite what the box says.
avoid prolonged eye contact with the barrel.
do not microwave. Again.
keep upright when not in use. It sulks otherwise.
discontinue use if it starts talking back.
consult a Medic before, during and after use.
not legal tender in {Place}.
the floor is not a holster.
keep out of reach of the {Team} team.
store in a cool, dry place away from Pyros.
remove packaging before firing. Most of it.
do not sit on it. It knows.
never leave it alone with a Spy.
handle may become hot, cold or opinionated.
some settling of contents is normal.
contains traces of nuts, bolts and peanuts.
results not typical. Results not guaranteed. Results not good.
not to be used as a step ladder.
do not shake the box. Something inside is asleep.
wipe feet before entering the barrel.
this is not a toy. It is barely a weapon.
past performance does not guarantee future explosions.
operating noise may frighten livestock and Scouts.
do not lick the trigger. You know who you are.
if it starts beeping, it is already too late.
mind the recoil. It minds you back.
in case of emergency, use it anyway.
not approved for use in the break room.
user assumes all responsibility, and some of the blame.
the manufacturer is not liable for anything, ever.
""")

AD_COPY = L("""
New from {Maker}! The {Name} - because you deserve slightly better.
Tired of losing? Try losing with the {Name}.
Ask your Quartermaster if the {Name} is right for you.
The {Name}. Now in stores, briefly.
{Maker} presents the {Name}: for the {cls} who has everything except this.
Limited time offer! Supplies limited! Quality limited!
Buy one {Name}, get zero free.
Why settle for a {kind} when you could have the {Name}?
Order the {Name} today and receive a free set of steak knives, eventually.
Now available in {Place}, and soon wherever {Place} is not.
Doctors hate it. Medics are undecided.
The {kind} that {Place} could not ban fast enough.
Act now and we will throw in the instructions.
From the makers of yesterday's mistake comes tomorrow's {Name}.
The official {kind} of not reading the reviews.
It slices, it dices, it mostly just {verbs}.
Introducing the {Name}: a {kind} for the modern {cls}.
Trusted by several mercenaries and at least one {Animal}.
Back by popular demand. The demand was from our accountants.
Satisfaction guaranteed or your respawn back.
Part of a balanced breakfast of violence.
Collect all three! There is only one.
{Maker}: making things since {Year}. Making this since Tuesday.
Not sold in stores. Barely sold online.
Upgrade your arsenal. Downgrade your expectations.
""")

AD_VERBS = L("""thuds|bonks|explodes|disappoints|complains|rattles|clanks|whistles|wobbles|smoulders|hums|sulks""", "|")

REVIEW_TEXT = L("""
Would get hit by it again.
Arrived broken. Still works better than my old one.
My {Relation} bought me this. We no longer speak.
Exactly as described, which was the problem.
Five stars for the box alone.
Does what it says on the tin. The tin said OUCH.
Too heavy, too loud, perfect.
I have used it every day and I am still not sure what it does.
Not as advertised. Better, somehow. Worse, also.
It fired. That is more than I expected.
Changed my life. My life did not want to be changed.
I would recommend it to my enemies.
Smaller than in the pictures. Angrier, too.
Took three respawns to figure out the safety.
Ordered a toaster. Got this. Kept it.
The {other} on my team keeps stealing it.
Great value, terrible values.
My dog is afraid of it, and so am I.
Bought it for the colour. Stayed for the screaming.
Would be ten stars if it stopped humming at night.
Comes with a smell. The smell does not leave.
Not for beginners. Not for experts. Possibly for nobody.
I lost my eyebrows and found my calling.
Works great until it does not.
Better than the last three, worse than a stick.
""")
REVIEWER = L("""
a satisfied {Team} {cls}|a {Team} {other} who wishes to remain anonymous|an unverified buyer from {Place}|
the {Place} Gazette|a {Relation} of the developer|someone named {First}|{First} from accounting|
a very tired {Occupation}|a former {Team} {cls}|a {Team} {other}, under protest|
Mann Co. Monthly|the {Place} Weekly Shopper|a mercenary who asked us not to print this|
{First}, aged {Num}|a respawn room regular|
a {Team} {cls} with a lot of free time|a Mann Co. shareholder|the {Place} Courier|a disgruntled former owner|
a {Team} {other} who misread the question|a verified purchaser, unverified human|the night janitor|
a critic from {Place}|{First} the {Occupation}|a {Relation} who saw it once|Gun Enthusiast Quarterly|
a {Team} {cls}, posthumously|an anonymous {Animal} owner""", "|")
RATING = L("""Five stars.|Four stars.|Three stars.|Two stars.|One star.|Half a star.|Ten out of ten.|
Seven out of ten.|Six out of ten.|Two thumbs up.|One thumb up.|Would buy again.|Would not buy again.""", "|")

CLASS_LORE = {
    "Scout": L("""
Ma says it's the best thing I ever bought. Ma has never seen it.
Faster than a pitch down the middle, and twice as rude.
Eight brothers fought over this. I won. I always win.
Got it for a bottle of Bonk and a handshake. Sucker.
Fits right in a baseball glove if you don't need the glove.
"""),
    "Soldier": L("""
Every great general in history carried one of these. Possibly two.
Field-tested in the Battle of {Place}, which I won single-handedly.
Regulation issue, according to regulations I wrote myself.
Ate my breakfast off it for a week. Seasoned to perfection.
America did not invent it, but America would have.
"""),
    "Pyro": L("""
Mmmph mmph mmmmph. (It makes the bad men into rainbows.)
In Pyroland it shoots lollipops. Out here, it does not.
Hugged it until it purred. It does not purr.
Mmph! Mmmph mmph! (Smells like birthday cake!)
The balloons told me to name it. The balloons were right.
"""),
    "Demoman": L("""
Tested in the Highlands. The Highlands lost.
Me mum built the first one out of a kettle and spite.
Ye wouldnae believe what it does to a sentry, lad.
One eye was plenty to aim it. Two would be showing off.
Smells of blackpowder and good decisions made badly.
"""),
    "Heavy": L("""
Small weapon for small man. Heavy is joking. Heavy uses it too.
Heavy named it after his sister. She does not know.
This one costs less than Sandvich. Is still worth more.
Babushka could lift this. Babushka could lift Heavy.
Is not as good as gun. Nothing is as good as gun.
"""),
    "Engineer": L("""
Built it over a weekend with a hacksaw and a stern talking-to.
Grandpappy would be proud, then confused, then proud again.
Eleven doctorates and I still could not tell you what that dial does.
If it ain't broke, I ain't finished with it yet.
Runs on elbow grease and the tears of BLU Spies.
"""),
    "Medic": L("""
I replaced the safety with a second, larger safety. It is still not safe.
The patient survived. The weapon did not. We rebuilt the weapon.
Archimedes nested in it for a week. It has never been better.
Hippocratic oath? I signed something. It was mostly crayon.
Seventh prototype. The first six are in the walls.
"""),
    "Sniper": L("""
Tested it on the van. The van is fine. The van is always fine.
A professional keeps it clean. This one is a little bit sticky.
Mum and Dad say it's a respectable job. They are wrong.
Patience, mate. It'll go off when it's good and ready.
Smells like a campervan at the end of a long week.
"""),
    "Spy": L("""
Elegant, discreet, and almost entirely made of lies.
I have one in every colour. You will never see any of them.
It once disguised itself as a lesser weapon. It was very convincing.
A gentleman never reveals where he got his {kind}.
It goes with everything, especially your back.
"""),
    "Civilian": L("""
Expensed to the Mann Co. account under miscellaneous umbrellas.
A gentleman does not fight. A gentleman expenses someone who does.
Approved by the board, fourteen votes to one abstention.
Fits neatly in a briefcase next to the shareholder report.
Paid for with a cheque that is still clearing.
"""),
}

MAKER_NOTE = L("""
{Maker} reminds you that all sales are final, and so are you.
{Maker} is not responsible for anything that happens after you pick it up.
{Maker} thanks you for choosing the cheapest option.
{Maker} would like to apologise in advance.
A {Maker} product. Mostly. Some parts are from a {House}.
{Maker} quality control has looked at it from across the room.
Produced under licence from {Maker}, who did not read the licence.
{Maker} recommends a second, better weapon.
Every unit leaves the {Maker} factory in {Place} with a firm handshake.
{Maker} engineers worked tirelessly on this for nearly an afternoon.
Manufactured by {Maker} in {Year}. Inspected by {Maker} never.
{Maker} has no comment at this time.
{Maker} customer service hours: Tuesdays, when it rains.
From the {Maker} Winter Catalogue, page {Num}, between the saws and the shame.
""")

STAT_LINES = {
    "damage": L("""Hits like a payload cart going downhill.|Overkill is just regular kill with ambition.|
Leaves a mark. Leaves several.|Built for the {cls} who solves problems once.|They will feel this in their next respawn.""", "|"),
    "firerate": L("""Fires faster than it should. Nobody has slowed it down.|The trigger has a mind of its own, and it is in a hurry.|
Trigger discipline sold separately.|Built for impatient people by impatient people.|Each shot arrives before you finish deciding.""", "|"),
    "clip": L("""Holds more than its pockets suggest.|The magazine goes on for a while. Then a while longer.|
Reloading is for people with plans.|Somebody overpacked.""", "|"),
    "reload": L("""Reloading is less an action and more a lifestyle.|Bring a book for the reload.|
Reloads in its own sweet time.|The reload has an intermission.""", "|"),
    "ammo": L("""Ammo is a luxury. Spend it like one.|Every bullet is personally counted by an accountant.|
Bring your own ammo, and maybe a snack.|Eats ammunition like a {Animal} eats sandwiches.""", "|"),
    "fire": L("""Comes pre-heated.|Runs hot. Runs very hot. Runs, mostly, on fire.|
Pyros consider it a little much.|Keep a bucket nearby, preferably full.|Spicy on contact.""", "|"),
    "speed": L("""Your legs will notice the difference before you do.|Built for running, toward or away.|
Changes how fast you go somewhere you should not be.|The Scout wants one. Do not let him.""", "|"),
    "health": L("""Good for what ails you, bad for what ails them.|A Medic would approve. A doctor would not.|
Contains essential vitamins and inessential shrapnel.|Health benefits not reviewed by anyone.""", "|"),
    "explosive": L("""Rearranges scenery and opinions.|The blast radius has a blast radius.|
Loud enough to be heard in {Place}.|Do not hug after firing.""", "|"),
    "crit": L("""Luck is a skill if you say it confidently.|Some days the dice roll themselves.|
Feeling lucky is mandatory.""", "|"),
    "knockback": L("""Excellent for personal space.|Sends people places. Not good places.|
Good for removing guests who overstay.""", "|"),
    "defense": L("""Bullets politely decline to hurt you as much.|Like a hug from a brick wall.|
Toughens the skin and the attitude.""", "|"),
    "accuracy": L("""Aiming is more of a suggestion.|Goes roughly where you point it, on a good day.|
Every shot is a surprise, for everyone.""", "|"),
    "mechanic": L("""Some of its features belong to another class entirely. Nobody can explain it.|
It came with stats meant for a {other}. Keep the receipt.|Half of these features are for somebody else's job.""", "|"),
    "plain": L("""Thoroughly average in every measurable way.|Does the job, if the job is small.|
The most unremarkable thing in the armoury, and proud of it.""", "|"),
}

NAME_LINES = L("""
Nobody remembers who named it the {Name}, and nobody will admit it.
The {Name} was named after the sound it makes when dropped.
It says {Name} on the side, in somebody else's handwriting.
They tried calling it something else. It would not answer.
The {Name} was the third choice of name. The first two were taken by lawyers.
Legend says the {Name} names itself. Legend is not a reliable source.
The name {Name} tested well with focus groups of one.
Engraved {Name} because the engraver misheard.
""")

HAIKU5 = L("""
the cart moves forward|a sentry beeping|morning in {Place}|respawn timer ticks|
smoke over the bridge|the intel is gone|a hat in the dust|the payload whistles|
crits fall like the rain|the Medic is near|one hit, then silence|the resupply hums|
a Scout runs past me|the overtime bell|spies in the long grass|a quiet shotgun""", "|")
HAIKU7 = L("""
this {kind} does not care at all|nobody reads the warning label|
the {cls} has done this before|a hat flies over the chimney|
someone forgot the fine print again|the warranty expires today|
the Engineer sighs and builds again|the enemy forgot to duck|
an old grudge travels at great speed|the receipt blows away in wind|
the Pyro hums a happy song|the Heavy laughs and eats a sandwich""", "|")

COUPLETS = L("""
Roses are red, the BLU team is too, and so is the {Name} after it's through.
It's not the size, it's the swing; it's not the swing, it's the thing.
Point it east, point it west, the {Name} does the rest.
One for the money, two for the show, three for the {other} it flattened below.
Shoot it high or shoot it low, where it lands, nobody knows.
Early to bed and early to rise, keeps the {Name} out of your eyes.
Bought on a Tuesday, fired on a Wednesday, returned on a Thursday, hidden by Friday.
Sticks and stones may break your bones, but this will also do it.
""")

HISTORY = L("""
Recovered from a crate in {Place} in {Year}, still ticking.
First issued to {Team} {clsP} during the Gravel Wars, then quickly un-issued.
Dug up behind the {Place} control point by a confused {Occupation}.
Lost in a card game in {Year}. Won back in {Year2}. Lost again on purpose.
The original was melted down in {Year}. This is the copy of the copy.
Smuggled out of {Place} in a crate labelled SOCKS.
Saxton Hale once wrestled one into submission. This is the survivor.
Banned in {Place} in {Year} for reasons the court would not say aloud.
Found in the Mann Co. vault between a bear and a bigger bear.
Rediscovered in the {Place} archives, filed under MISTAKES.
Spent {Num} years as a doorstop at the {Place} train station.
Commissioned by {First} Mann, who immediately regretted it.
""")

CLASSIFIED = L("""
For sale: one {Name}, lightly used, slightly haunted. Serious offers only.
For sale: {kind}, good condition, bad attitude. Will trade for a sandvich.
Free to a good home: one {Name}. Bad homes also considered.
Wanted: someone, anyone, to take this {kind} off my hands. Ask for {First}.
Lost: one {Name}. If found, do not return it.
Swap: one {Name} for one working conscience. No time-wasters.
""")

STEPS = L("""
point the dangerous end away from you|say something cool|wait for the noise|apologise to the wall|
check that it is loaded|check again|pretend you meant that|blame the {other}|read the manual|
lose the manual|press the big button|ignore the small button|stand very still|run|call your {Relation}|
fill out form 27-B|hold firmly by the handle|look surprised|respawn|try again with confidence|
wipe off whatever that was|tell nobody|
take a deep breath|count to three, or two|aim somewhere near the enemy|close your eyes|open your eyes|
find a Medic|hide behind the Heavy|consult the warranty|duck|stretch first|remove the sticker|
put on a helmet|ask the Engineer|ignore the Engineer|shout something inspirational|file a complaint|
fill in the incident report|take the rest of the day off|polish it|put it down gently|walk away slowly""", "|")

INGREDIENTS = L("""
scrap metal|leftover sandvich|three springs|one mystery spring|duct tape|a bad feeling|Australium dust|
spare sentry parts|a {House}|recycled hats|old receipts|a sense of purpose|gravel|questionable wiring|
a single bolt|one bowling pin|bottled rage|lightly used rockets|a pinch of salt|stolen Intel|
paint from {Place}|a teaspoon of chaos|the left half of a {House}|wishful thinking|
two coffee cans|a broken compass|leftover Bonk|half a sandvich|the springs from a mattress|
melted toy soldiers|a stolen hubcap|loose change|a jar of pickles|fishing line|a coat hanger|
the handle of an umbrella|cardboard|an old boot|three bottle caps|a very small sentry|
someone else's homework|a medal of questionable origin|a bent spoon|bubblegum|rubber bands""", "|")

QUOTES = L("""
I have no idea what it does, but I like it.|Point it at the problem. Problem solved.|
They told me it was impossible. I did not listen. Nobody ever listens.|
It is not stealing if it is already broken.|Do not ask me how. Ask me why. Actually, do not ask me that either.|
Every great weapon starts as a bad idea.|I will allow it.|That is going in my report.|
Somebody get a mop.|Well, that happened.|You call that a {kind}? Actually, yes. Fair enough.|
I have seen worse. I have built worse.""", "|")
SPEAKER = L("""
the {Team} {cls}|the {Team} {other}|Miss Pauling|the Administrator|Saxton Hale|a passing {Occupation}|
{First} from {Place}|the {Place} night watchman|the {cls}'s {Relation}|the Quartermaster""", "|")

# lines for the traits pipeline.py already detects (kept: they explain real mechanics)
TRAIT_LINES = {
    "self_ignite": L("""Sets you on fire. On purpose.|Comes pre-ignited, for your inconvenience.|
Warms the hands, the arms and eventually everything else.|The user is also a fuel source.|
Self-heating. Self-burning. Self-explanatory.|Bring a fire extinguisher, ideally yours.|
Lights you up like a birthday cake.|You will be on fire. That is the deal.|
Doubles as a personal heater, whether you want one or not.|Fireproof gloves recommended. Fireproof everything recommended.|
The flames are a feature. The screaming is optional.|Smoulders quietly, mostly on you.|
Comes with its own little bonfire, located on you.|Hot to the touch. Hot to the everything.|
Ignites the user for free. Enemies cost extra.|Self-roasting, like a good coffee bean.""", "|"),
    "odd_projectile": L("""Fires {proj}.|Ammunition: {proj}. Do not ask.|Loaded with {proj}, for reasons.|
Instead of rockets: {proj}.|Launches {proj} at alarming speeds.|Now firing {proj}, as requested by nobody.|
Payload: {proj}. Dignity: none.|Shoots {proj}. The {proj} did not consent.|
Projectile of choice: {proj}. Choice made by nobody.|Fires {proj} with confidence it has not earned.|
Somebody loaded it with {proj} and nobody stopped them.|Ammunition has been replaced with {proj}.|
Expect {proj} where the rockets used to be.|Now delivering {proj}, express.|
Fires {proj}. Results vary wildly.|Each shot is {proj}. Each impact is a mystery.""", "|"),
    "wrong_class": L("""Not meant for the {wcls}. Do not tell anyone.|{wcls}-compatible (allegedly).|
Somehow ended up in the {wcls}'s locker.|Designed for someone else. The {wcls} took it anyway.|
The {wcls} signed for this delivery by mistake.|Issued to the {wcls} due to a paperwork error.|
The {wcls} insists this is theirs now.|Mis-shelved in the {wcls} section and never moved.|
Built for one class, delivered to the {wcls}. Close enough.|The {wcls} found it in lost property and kept it.|
Nobody checked whether the {wcls} was qualified.|Quartermaster's note: {wcls} gets this one, apparently.|
The {wcls} won it in a raffle nobody else entered.|Arrived in a crate addressed to the {wcls}, smudged.|
Officially on loan to the {wcls}. The loan has no end date.|The {wcls} is not trained for this. Nobody is.|
Wrong locker, right attitude, says the {wcls}.|The {wcls} claims it was always theirs. The paperwork disagrees.|
A {wcls} exclusive, by accident.|Reassigned to the {wcls} by a coin toss.|
The {wcls} signed the requisition form in crayon.|Retrained for the {wcls}, over a long weekend.|
The {wcls} has been told twice to give it back.|Approved for {wcls} use by a confused clerk.""", "|"),
}

KIND_WORD = {
    "rocket": "rocket launcher", "grenade": "grenade launcher", "minigun": "minigun", "flame": "flamethrower",
    "flare": "flare gun", "shotgun": "shotgun", "pistol": "pistol", "smg": "submachine gun",
    "needle": "syringe gun", "rifle": "rifle", "bow": "bow", "blunt": "blunt instrument",
    "blade": "blade", "generic": "weapon",
}
