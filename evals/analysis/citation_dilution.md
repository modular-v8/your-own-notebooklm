# Citation dilution diagnosis (Phase 5, T5b.1/T5b.2)

## T5b.1 -- raw material for the 12 citation-precision regressions (12 found)

For each regressed entry: the question, expected answer, the model's actual answer, and every cited chunk that misses all of this entry's gold spans (the ones dragging precision down), with full text -- for a direct read on whether each is load-bearing or merely adjacent context.

### `q-005` (citation_precision 2/5 = 0.40, tags: ['near-duplicate'])

**Question:** Does the shutdown circuit requirement for an EV include an LVMS, the same way the CV shutdown circuit does?

**Expected answer:** No. The CV shutdown circuit definition explicitly includes the LVMS. The EV shutdown circuit definition does not list the LVMS at all — instead it requires at least two master switches, the IMD, and the AMS in addition to components both circuits share, like the BOTS, the inertia switch, and the BSPD.

**Model's answer:** Yes — the LVMS is part of the shutdown circuit requirement for both vehicle types, though it shows up slightly differently in each definition.

- **CV4.1.2** explicitly names the LVMS as a required component: "The shutdown circuit is defined as a series connection of at least the LVMS (see T11.3), the BSPD (see T11.6), three shutdown buttons (see T11.4), the BOTS (see T6.2) and the inertia switch." Since a CV only has one master switch, that master switch is the LVMS.

- **EV6.1.2** instead requires "a series connection of at least two master switches, three shutdown buttons, the BOTS, the IMD, the inertia switch, the BSPD, all required interlocks and the AMS." Per T11.2.1 ("Master switches (see T11.3 and EV6.2)"), the two master-switch types referenced are the LVMS (T11.3) and the TSMS (EV6.2). So the EV shutdown circuit's "two master switches" are the LVMS and the TSMS together, not just the LVMS alone.

So the EV shutdown circuit does include an LVMS, but it's one of two required master switches (LVMS + TSMS), whereas the CV shutdown circuit's only master switch is the LVMS itself.

**Cited, gold-overlapping (counts toward precision):** ['fb_rules.pdf:0298', 'fb_rules.pdf:0250']

**Cited, NOT overlapping any gold span (dragging precision down):**
- `fb_rules.pdf:0196`: '50 V AC RMS.\nT11.1.3\nAll LVS parts must be adequately insulated.\nT11.1.4\n[CV ONLY] The following systems are excluded from the LVS voltage limit (see T11.1.2):\n●\nHigh voltage systems for ignition\n●\nHigh voltage systems for injectors\n●\nVoltages internal to OEM charging systems designed for <60 V DC output.\nT11.1.5\n[EV ONLY] The LVS must not use orange wiring or conduit.\nT11.1.6\n[EV ONLY] The LVS must be grounded to the chassis.\nT11.2\nMaster Switches\nT11.2.1\nMaster switches (see T11.3 and EV6.2) m'
- `fb_rules.pdf:0198`: '.\nT11.2.4\nMaster switches must be rigidly mounted to the vehicle and must not be removed during\nmaintenance.\nT11.2.5\n[EV ONLY] Master switches must be mounted next to each other.\nT11.3\nLow Voltage Master Switch (LVMS)\nT11.3.1\nAn LVMS according to T11.2 must completely disable\n●\n[EV ONLY] power to the LVS\n●\n[CV ONLY] power from the Low Voltage (LV) battery and the alternator to the LVS\nT11.3.2\nThe LVMS must be mounted in the middle of a completely red circular area of ≥50 mm\ndiameter placed on a '
- `fb_rules.pdf:0302`: 'st not act through any\npower stage.\nEV6.1.11\nAll signals influencing the shutdown circuit are SCSs (see T11.9).\nEV6.2\nTractive System Master Switch (TSMS)\nEV6.2.1\nA TSMS according to T11.2 must be part of the shutdown circuit (see EV6.1.2).\nEV6.2.2\nThe TSMS must be fitted with a “lockout/tagout” capability to prevent accidental activation\nof the TS. The ESO must ensure that it is locked in the off position whenever work is done\non the vehicle or no ESO is present.\nEV6.2.3\nThe TSMS must be mounte'

### `q-019` (citation_precision 1/3 = 0.33, tags: ['vocabulary-mismatch'])

**Question:** Do I need to show proof I have health coverage to take part?

**Expected answer:** Yes. Every participant, including faculty advisors and volunteers, must provide proof of valid private liability and individual health insurance for the competition.

**Model's answer:** Yes. According to the Formula Bharat rules (A4.6.1), each participant — including faculty advisors and volunteers — must provide proof of valid private liability & individual health insurance for the competition (A4.6, "Insurance").

Additionally, at on-site registration the team captain is responsible for submitting each confirmed participant's insurance information and uploading scanned copies of the insurance documents (A5.8.4). Note that if a confirmed participant's insurance information (including the scanned copies) is incorrect or incomplete, their participation status will be revoked on-site (A5.8.5).

**Cited, gold-overlapping (counts toward precision):** ['fb_rules.pdf:0057']

**Cited, NOT overlapping any gold span (dragging precision down):**
- `fb_rules.pdf:0076`: 'ership by Formula Bharat (MFB) platform.\nA5.8.2\nAll team members must provide details towards the Team Member Information (TMI)\nsubmission available on the competition website by the specified deadline. This information\nincludes but is not limited to Full Name, Contact Email, Phone Number, Age, Year of\nStudy, Medical Emergency contact information (which must be next of kin) etc.\nA5.8.3\nThe TMI submission criteria will be made available on the competition website\napproximately two months prior to'
- `fb_rules.pdf:0077`: 'e scans, under 18\nliability waivers’ scans (if any) and for providing driver license information.\nA5.8.5\nConfirmed participants with incorrect or incomplete insurance information (including\nscanned copies) shall have their participation status revoked on-site at the competition.\nA5.8.6\nA maximum of 60 team members may participate on a team.\nA5.8.7\nLate submission fees and extra member fees shall be on the competition website.\nA5.9\nParticipation Certificates\nA5.9.1\nParticipants who are listed on '

### `q-020` (citation_precision 1/2 = 0.50, tags: ['vocabulary-mismatch'])

**Question:** Can I reach the kill switch from outside the car if something goes wrong?

**Expected answer:** Yes. Two of the three required shutdown buttons are mounted on each side of the vehicle, behind the driver's compartment at roughly head height, with a minimum diameter of 40 mm, and they must be easily reachable from outside the vehicle.

**Model's answer:** Yes. According to the Formula Bharat rules booklet (T11.4.3), one shutdown ("kill") button must be located on each side of the vehicle, behind the driver's compartment at approximately head level, with a minimum diameter of 40 mm — and these buttons are explicitly required to be **easily reachable from outside the vehicle**.

This is in addition to a separate cockpit-mounted shutdown button (T11.4.4, min. 24 mm diameter) that must be within easy reach of the belted-in driver, alongside the steering wheel. All shutdown buttons must be marked with the international electrical hazard symbol (red spark on a white-edged blue triangle) nearby (T11.4.5). Pressing any of these buttons opens the shutdown circuit, which immediately stops all accumulator current flow (per EV6.1).

**Cited, gold-overlapping (counts toward precision):** ['fb_rules.pdf:0199']

**Cited, NOT overlapping any gold span (dragging precision down):**
- `fb_rules.pdf:0300`: 'onds.\nAll accumulator current flow must stop immediately.\nThe action of opening the shutdown circuit may be delayed by ≤250 ms to signal the action\nto the motor controllers and reduce the TS current before the AIRs are opened. The AIR\nsupply must be abruptly switched off before reaching the minimum AIR supply voltage.\nFigure 21: Explanatory example schematic of the required shutdown circuit\nEV6.1.6\nIf the shutdown circuit is opened by the AMS or the IMD, it has to be latched open by a\nnon-progra'

### `q-021` (citation_precision 4/5 = 0.80, tags: ['synthesis', 'boundary-spanning'])

**Question:** What are all the dimensional minimums that apply to the impact attenuator, including its mounting?

**Expected answer:** The IA itself must be at least 100 mm high and 200 mm wide for a minimum distance of 200 mm forward of the front bulkhead, with no part of that volume more than 350 mm above the ground. If bolted to the AIP, it needs a minimum of four 8 mm metric grade 8.8 bolts (or adhesive rated to carry 60 kN in any direction). Separately, when tested, the IA assembly must decelerate a 300 kg vehicle impacting at 7 m/s at no more than 20 g average and 40 g peak, absorbing at least 7350 J of energy.

**Model's answer:** Based on the Formula Bharat Rules (T3.17 – Impact Attenuator), the dimensional minimums for the IA assembly (impact attenuator + AIP) and its mounting are:

**Impact Attenuator (IA) itself – T3.17.2**
- At least **100 mm high** and **200 mm wide**, maintained for a minimum distance of **200 mm forward of the front bulkhead** (i.e., a required minimum volume of 100 × 200 × 200 mm³).
- No portion of this required 100 × 200 × 200 mm³ volume may be positioned **more than 350 mm above the ground**.
- Must not be wider or higher than the AIP, must have a closed front section, must not penetrate the front bulkhead on impact, and must be attached securely and directly to the AIP.

**Anti-Intrusion Plate (AIP) – T3.17.3**
- Baseline design: **1.5 mm solid steel** or **4.0 mm solid aluminum** plate.
- If bolted to the front bulkhead, the IA/AIP assembly must be the **same size as the outside dimensions of the front bulkhead**.
- If welded to the front bulkhead, it must **extend at least to the centerline of the front bulkhead tubing** in all directions.
- The AIP must **not extend past the outside edges of the front bulkhead**.

**Mounting/Attachment – T3.17.5**
- IA attached to AIP by a **minimum of four 8 mm metric grade 8.8 bolts** (critical fasteners, must comply with T10).
- Adhesive attachments must carry a load of at least **60 kN** in any direction.

**"Standard" FSAE IA option (if used, to avoid physical testing) – T3.17.7**
- If front bulkhead width > 400 mm and/or height > 350 mm, a diagonal/X-bracing support tube (or approved equivalent) must be included.
- Must use a **1.5 mm solid steel AIP welded along its full perimeter** to a steel bulkhead, or a **4 mm solid aluminum AIP bolted with a minimum of eight 8 mm metric grade 8.8 bolts**.
- If the "standard" honeycomb IA is used, it must be of the **pre-crushed** type.
- Adhesive used to mount the standard IA to the AIP must have a **shear strength of at least 24 MPa** (and must also satisfy T3.2.8).
- If the standard IA is used but doesn't meet T3.17.7 requirements, physical testing must prove the AIP does **not permanently deflect more than 25 mm**.

**General bolted-support reference (T3.16)**
- For general perimeter-mounted brackets/supports (applicable engineering practice referenced near IA rules): for each **200 mm of reference perimeter**, a minimum of one **8 mm metric grade 8.8 bolt** must be used (rounded up), evenly distributed.

**Cited, gold-overlapping (counts toward precision):** ['fb_rules.pdf:0141', 'fb_rules.pdf:0142', 'fb_rules.pdf:0143', 'fb_rules.pdf:0145']

**Cited, NOT overlapping any gold span (dragging precision down):**
- `fb_rules.pdf:0144`: 'must have the segments bonded together to prevent sliding or\nparallelogramming.\nT3.17.7\nA team may use one of the “standard” FSAE IAs, in order to avoid testing, provided that:\n+ Version 1.4 | 05.23.2024 | Adaptation of FS-Rules 2024 v1.1\n52 / 137\n\n\nFORMULA BHARAT\n2025 RULES BOOKLET\n●\nif the front bulkhead width is larger than 400mm and/or its height is larger than 350mm\na diagonal or X-bracing that is a front bulkhead support tube or an approved equivalent\nper T3.2, must be included in the fron'

### `q-024` (citation_precision 2/4 = 0.50, tags: ['boundary-spanning'])

**Question:** If a shoulder harness is mounted to a tube that isn't straight, what analysis must a team perform to justify it, and what happens if they choose not to?

**Expected answer:** The joints between the tube and the structure it's mounted to must be reinforced in the side view by triangulation tubes to prevent torsional rotation. The required analysis method is to use a 7 kN load per attachment and the range of angles from T5.5.5, then calculate that the bent shoulder harness bar triangulation stresses are less than the as-welded yield strength (T3.2.4) for combined bending and shear, and that it does not fail in column buckling. If the team chooses not to perform this strength analysis, rule T3.2.6 applies instead.

**Model's answer:** Now I have all the pieces needed to answer.

**If a shoulder harness is mounted to a tube that isn't straight (T5.5.2):**

The joints between that tube and the structure it's mounted to must be reinforced (in side view) with triangulation tubes, to prevent torsional rotation of the harness-mounting tube. This requires **supporting calculations**, specifically:

- **Analysis method:** Using a 7 kN load per attachment point and the range of harness angles specified in T5.5.5, the team must calculate that the bent shoulder harness bar's triangulation stresses are below the as-welded yield strength (per T3.2.4) for combined bending and shear, and that it does not fail in column buckling.

**If the team chooses not to perform this strength analysis**, then rule **T3.2.6** applies by default instead. Under T3.2.6, since the harness bar is a bent tube (a member of the primary structure), the team must add an additional support tube, which:
- Attaches at the point along the bent tube where it deviates farthest from a straight line connecting both ends,
- Is of the same dimension as the tube it supports,
- Terminates at a node of the chassis, and
- Is angled no more than 30° from the plane of the supported tube.

In short: the team either proves the bent harness-mounting tube's strength via calculation (7 kN/attachment load analysis), or, if they skip that analysis, they must fall back on the generic bent-tube support requirement in T3.2.6.

**Cited, gold-overlapping (counts toward precision):** ['fb_rules.pdf:0170', 'fb_rules.pdf:0171']

**Cited, NOT overlapping any gold span (dragging precision down):**
- `fb_rules.pdf:0114`: 'pt for inspection holes, any holes drilled in any part which is a member of the primary\nstructure must be considered in the SES.\nT3.2.4\nThe steel properties used for the calculations in the SES must be:\nNon-welded strength for continuous material calculations:\n●\nYoung’s Modulus (E) = 200 GPa\n●\nYield Strength (Sy) = 305 MPa\n●\nUltimate Strength (Su) = 365 MPa\nWelded strength for discontinuous material such as joint calculations:\n●\nYield Strength (Sy) = 180 MPa\n●\nUltimate Strength (Su) = 300 MPa\nT3'
- `fb_rules.pdf:0115`: 'f the primary structure (except for the roll hoops) is a bent tube or made from\nmultiple tubes an additional tube must support it. This support tube must:\n+ Version 1.4 | 05.23.2024 | Adaptation of FS-Rules 2024 v1.1\n42 / 137\n\n\nFORMULA BHARAT\n2025 RULES BOOKLET\n●\nHave its attachment point at the position along the bend tube where it deviates farthest\nfrom a straight line connecting both ends.\n●\nBe of the same dimension as the supported tube(s).\n●\nTerminate at a node of the chassis.\n●\nBe angled n'

### `q-028` (citation_precision 1/2 = 0.50, tags: ['lexical-anchor'])

**Question:** How many fire extinguishers must a team have, and what is the minimum firefighting agent capacity required?

**Expected answer:** Each team must have at least two dry chemical/dry powder fire extinguishers, each with a minimum firefighting agent capacity of 0.9 kg.

**Model's answer:** Each team must have at least **two dry chemical/dry powder fire extinguishers**, each with a **minimum firefighting agent capacity of 0.9 kg** (rule T13.4.1). Additional notes:

- Minimum accepted ratings vary by region: USA/Canada/Brazil – 10BC or 1A 10BC; Europe – 34B or 5A 34B; Australia – 20BE or 1A 10BE; India – dry chemical/dry powder ABC extinguishers are acceptable. Larger capacity extinguishers are always acceptable.
- AFFF and Halon extinguishers/systems are prohibited.
- All extinguishers must have a manufacturer-installed pressure/charge gauge.
- One extinguisher must be readily available in the team's paddock area, and the second must accompany the vehicle wherever it is moved; both must be presented at technical inspection.
- Hand-held fire extinguishers may not be mounted on or in the vehicle.

**Cited, gold-overlapping (counts toward precision):** ['fb_rules.pdf:0224']

**Cited, NOT overlapping any gold span (dragging precision down):**
- `fb_rules.pdf:0225`: 'uishers\nand systems are prohibited.\nT13.4.4\nAll extinguishers must be equipped with a manufacturer installed pressure/charge gauge.\nT13.4.5\nExcept for the initial inspection, one extinguisher must readily be available in the team’s\npaddock area, and the second must accompany the vehicle wherever the vehicle is moved.\nBoth extinguishers must be presented with the vehicle at technical inspection.\nT13.4.6\nHand held fire extinguishers are not permitted to be mounted on or in the vehicle.\nT13.5\nCamer'

### `q-031` (citation_precision 1/3 = 0.33, tags: ['follow-up'])

**Question:** What about the lap and anti-submarine belts — is there a similar spacing rule for those?

**Expected answer:** Yes, but it's a conditional load rule rather than a spacing minimum: if the lap belts and anti-submarine belts are attached less than 100 mm apart, those attachment points must together support a total load of 19.5 kN.

**Model's answer:** Not exactly the same kind of rule. There's no explicit min/max width spacing requirement for the lap belt mounting points themselves. However, for the **anti-submarine belts**, the rule (T5.6.1) states that when the belts go vertically down from the groin (or angled up to 20° rearward), their anchorage points **should be approximately 100 mm apart** — a single target figure rather than a range like the shoulder harness's 180–230 mm.

There's also a related structural note (T4.5.4): if the lap belts and anti-submarine belts are attached **less than 100 mm apart** from each other, that combined attachment must support a total load of 19.5 kN (versus the individual 13 kN for lap/shoulder and 6.5 kN for anti-submarine belts).

**Cited, gold-overlapping (counts toward precision):** ['fb_rules.pdf:0156']

**Cited, NOT overlapping any gold span (dragging precision down):**
- `fb_rules.pdf:0172`: ' the horizontal as\nin Figure 14.\nFigure 15: Lap belt and shoulder harness mounting\nT5.6\nAnti-Submarine Belt Mounting\nT5.6.1\nThe anti-submarine belts of a 6 point harness should be mounted in one of the following\nsetups:\n●\nWith the belts going vertically down from the groin, or angled up to 20° rearwards.\nThe anchorage points should be approximately 100 mm apart.\n●\nWith the anchorage points on the primary structure at or near the lap belt anchorages,\nthe driver sitting on the anti-submarine belts'
- `fb_rules.pdf:0171`: 'ed. Analysis method: Use 7 kN load per attachment and the range of angles in T5.5.5,\ncalculate that the bent shoulder harness bar triangulation stresses are less than as welded\nyield strength T3.2.4 for combined bending and shear and does not fail in column buckling.\nIf the team chooses not to perform the strength analysis T3.2.6 will apply.\nT5.5.3\nThe strength of any shoulder harness bar and bracing tubes must be proven in the relevant\ntab of the team’s SES submission.\nT5.5.4\nThe shoulder harne'

### `q-034` (citation_precision 2/3 = 0.67, tags: ['follow-up'])

**Question:** Is that the same for the Gallardo's version?

**Expected answer:** No — the Gallardo's e-gear does not use ISR at all. Lamborghini claimed ISR cut shift times by roughly 40% versus a conventional single-rod automated manual, which is the same core mechanism the Gallardo's e-gear uses, just without ISR's second set of shifting rods to hide the gap between gears. So the Gallardo is meaningfully slower than the Aventador's 50 ms figure, though the document does not give an exact millisecond number for it.

**Model's answer:** No — the 50 ms "less than the blink of an eye" figure is specific to the Aventador's ISR gearbox, not the Gallardo's e-gear. The corpus doesn't give a specific millisecond shift-time claim for the Gallardo's e-gear itself. What it does say is that ISR (used on the Aventador) improved on the older single-rod design used in e-gear (Gallardo/Murciélago) by roughly 40% in shift time, since e-gear uses a single shifting rod that has to fully disengage one gear before engaging the next, whereas ISR uses four independent rods to overlap that process. So the Gallardo's e-gear was slower to shift than the Aventador's ISR — no exact millisecond figure is given for it in the source material.

**Cited, gold-overlapping (counts toward precision):** ['egear.md:0009', 'egear.md:0010']

**Cited, NOT overlapping any gold span (dragging precision down):**
- `egear.md:0008`: "m |\n|---|---|---|\n| Murciélago | 2001 to 2010 | e-gear (single clutch automated manual) |\n| Gallardo | 2003 to 2013 | e-gear (single clutch automated manual) |\n| Aventador | 2011 to 2021 | ISR (Independent Shifting Rod) |\n\nThe two cars did not get identical systems. The Murciélago, notably, has no automatic mode at all, only manual paddle operation, while the Gallardo will happily shift for itself if asked. That difference matters more than it sounds, because a large share of e-gear's bad reputa"

### `q-035` (citation_precision 2/3 = 0.67, tags: ['follow-up'])

**Question:** Does the Cayenne's version have the same kind of trade-off?

**Expected answer:** Not in the same sense — the document doesn't give a weight figure for the Cayenne's Tiptronic S. Instead it describes a different trade-off: Porsche kept the torque-converter Tiptronic S alive in the Cayenne specifically because torque converters handle sustained towing loads better than a dual-clutch box does, which is part of why the Cayenne is rated to tow 7,700 lb while the PDK-only Macan tops out under 5,000 lb.

**Model's answer:** Based on what I found, the corpus doesn't give a weight-difference figure for the Cayenne comparable to the 996's ~31 kg gap. In fact, the Cayenne doesn't really have a manual-vs-Tiptronic trade-off to compare in the same way — the excerpts explain that Porsche has kept the torque-converter Tiptronic S alive specifically in the Cayenne (even though PDK now covers the rest of the lineup) because torque converters handle sustained towing loads better than a dual-clutch box does. That's reflected in the tow ratings: the Cayenne is rated to tow 7,700 lb versus under 5,000 lb for the PDK-only Macan.

So the trade-off for the Cayenne isn't framed as "extra weight vs. a manual" the way it was for the 996 (the Cayenne doesn't have a manual to compare against in these excerpts) — it's framed as "torque-converter durability/towing capability vs. the quicker-shifting PDK." No specific kg figure is given for that comparison in the material I retrieved.

**Cited, gold-overlapping (counts toward precision):** ['tiptronic.md:0010', 'tiptronic.md:0009']

**Cited, NOT overlapping any gold span (dragging precision down):**
- `tiptronic.md:0005`: 'ated for up to 300 Nm of torque (370 Nm in the beefier versions) and built with a design life around 300,000 km. The extra clutch packs, torque-converter fluid, and solenoid-laden valve body it carried over a simple manual gearbox added real weight too, making a Tiptronic-equipped 996 roughly 31 kg heavier than the same car with a stick. It turned up under the Boxster, Cayman, and 911 as easily as it did under a BMW 5 Series, an Audi A6, a Jaguar S-Type, or a Skoda Superb between 1994 and 2008. '

### `q-047` (citation_precision 1/2 = 0.50, tags: ['vocabulary-mismatch'])

**Question:** Can I just top up my own car's tank in the pits, or does someone else have to handle that?

**Expected answer:** Someone else has to handle it. Fueling may only take place at the fuel station and must be conducted by officials only.

**Model's answer:** According to the Formula Bharat rules booklet, no — you cannot fuel your own car in the pits. Rule A6.9.1 states: **"Fueling may only take place at the fuel station and must be conducted by officials only."** So refueling is restricted to a designated fuel station, and only competition officials are permitted to actually handle the fueling — not team members or drivers.

Additionally, during endurance events specifically, D7.7.1 notes that teams are prohibited from working on or fueling their vehicle during the run at all.

**Cited, gold-overlapping (counts toward precision):** ['fb_rules.pdf:0089']

**Cited, NOT overlapping any gold span (dragging precision down):**
- `fb_rules.pdf:0390`: 'ange area under its own power without external assistance.\nD7.6.7\nThe wheel will be inspected by the officials. If the deflation was not caused by external\nfactors, the vehicle will be scored DNF.\n+ Version 1.4 | 05.23.2024 | Adaptation of FS-Rules 2024 v1.1\n133 / 137\n\n\nFORMULA BHARAT\n2025 RULES BOOKLET\nD7.6.8\nDeflation caused by running off course or impacting barriers or other objects due to driver\nerror will not be regarded as external factors.\nD7.7\nEndurance Specific Regulations\nD7.7.1\nTeams'

### `q-051` (citation_precision 1/4 = 0.25, tags: ['vocabulary-mismatch'])

**Question:** Could I build a brake system that's entirely wires and a computer, with no physical hydraulic backup?

**Expected answer:** No. "Brake-by-wire" systems are prohibited.

**Model's answer:** No — according to the Formula Bharat rules booklet, this is explicitly prohibited.

Rule **T6.1.1** requires the vehicle to be equipped with a **hydraulic** brake system acting on all four wheels, operated by a single control, and **T6.1.5** states plainly: **"Brake-by-wire" systems are prohibited.**

Additional relevant requirements reinforce that hydraulics must be the real actuation mechanism, not just electronics:

- **T6.1.2**: The brake system must have two independent hydraulic circuits, each with its own fluid reserve, so that a leak/failure at any point still leaves effective braking on at least two wheels.
- **T6.1.3**: The system must be sealed to prevent leakage.
- **T6.1.12 (EV only)**: Even where electronic regenerative braking is used, only the *first 90%* of brake pedal travel may regenerate energy without hydraulic actuation — the remaining pedal travel **must directly actuate the hydraulic brake system**, so regen can supplement but never fully replace hydraulics.
- **T6.3.1**: The brake light must be tied to actuation of the hydraulic brake system (or, for EVs, the electric brake system as a secondary condition) — again showing hydraulics as the base requirement.

So under these rules, a fully electronic (wire-and-computer-only) brake system with no hydraulic backup would not be legal — a genuine hydraulic circuit acting on all four wheels is mandatory, and brake-by-wire is specifically banned.

**Cited, gold-overlapping (counts toward precision):** ['fb_rules.pdf:0175']

**Cited, NOT overlapping any gold span (dragging precision down):**
- `fb_rules.pdf:0176`: 'ed plastic brake lines are prohibited.\nT6.1.7\nThe brake system must be protected from failure of the drivetrain (see T7.3.2) from\ntouching any movable part and from minor collisions.\nT6.1.8\nIn the side view any portion of the brake system that is mounted on the sprung part of the\nvehicle must not project below the lower surface of the chassis.\nT6.1.9\nAny part of the brake system must be within the surface envelope, see T1.1.18.\nT6.1.10\nThe brake pedal and its mounting must be designed to withsta'
- `fb_rules.pdf:0177`: 'fabricated from steel or aluminum or\nmachined from steel, aluminum or titanium.\nT6.1.12\n[EV ONLY] The first 90% of the brake pedal travel may be used to regenerate brake energy\nwithout actuating the hydraulic brake system. The remaining brake pedal travel must\ndirectly actuate the hydraulic brake system, but brake energy regeneration may remain\nactive.\nT6.2\nBrake Over-Travel Switch (BOTS)\nT6.2.1\nA brake pedal over-travel switch must be installed on the vehicle as part of the shutdown\ncircuit, as'
- `fb_rules.pdf:0178`: 'brake balance\nsettings without damaging any part of the vehicle.\nT6.2.2\nRepeated actuation of the switch must not close the shutdown circuit, and it must be\ndesigned so that the driver cannot reset it.\nT6.2.3\nThe BOTS must be a push-pull, push-rotate or flip type mechanical switch. It may consist\nof a series connection of switches.\nT6.3\nBrake Light\nT6.3.1\nThe vehicle must be equipped with one brake light that is illuminated if and only if\n●\nthe hydraulic brake system is actuated\n●\n[EV ONLY] or t'

### `q-056` (citation_precision 2/4 = 0.50, tags: ['cross-document', 'synthesis'])

**Question:** Both the Formula Bharat rulebook's IMD requirement and the egear document describe a system that shuts things down when it can't confirm everything is working correctly. What triggers each one?

**Expected answer:** The Insulation Monitoring Device (IMD) must open the EV shutdown circuit if it detects either an insulation failure or a failure of the IMD itself, and this must happen without any programmable logic involved. In Lamborghini's e-gear, if the two Hall-effect position sensors don't confirm that a commanded gear was actually reached, the system can disable the car outright as a safety measure. Both intervene by cutting the system off entirely once a monitoring or confirmation signal comes back wrong, rather than letting the vehicle keep operating in an unverified state.

**Model's answer:** I have enough information to answer both.

## Formula Bharat rulebook — IMD (Insulation Monitoring Device)

Per **EV6.3.6**: the IMD opens the shutdown circuit **"in case of an insulation failure or an IMD failure"** — i.e., either the IMD detects an actual insulation fault in the tractive system, or the IMD itself fails/can't function properly. This action happens without any programmable-logic involvement, and once triggered, the shutdown must stay latched open (only manually resettable by someone other than the driver, per EV6.1.6) with a red "IMD" indicator lit in the cockpit until the fault is cleared.

## egear document — gear/clutch position confirmation

The e-gear (electro-hydraulic gearbox) system uses two position sensors (one on the selection stroke, one on the engagement stroke) plus a potentiometer, which all report back to the TCU to confirm that a commanded gear was actually reached. **If that confirmation signal doesn't arrive** — i.e., the system can't verify the mechanism physically reached the commanded position — **the system can disable the car outright as a safety measure.** (This is also the same signal path driving the dash gear indicator, which is why a car refusing to move and a blank gear display often share the same root fault.)

**In short:** the FB rulebook's IMD trips on an actual/possible insulation fault or its own self-failure, while e-gear trips on a missing position-confirmation signal from its gear-position sensors — both are "fail-safe if I can't confirm success" designs, but one guards electrical isolation and the other guards mechanical gear-position confirmation.

**Cited, gold-overlapping (counts toward precision):** ['fb_rules.pdf:0304', 'egear.md:0006']

**Cited, NOT overlapping any gold span (dragging precision down):**
- `fb_rules.pdf:0303`: ').\nEV6.3\nInsulation Monitoring Device (IMD)\nEV6.3.1\nEvery vehicle must have an IMD installed in the TS system.\nEV6.3.2\nThe IMD must be a Bender A-ISOMETER® iso-F1 IR155-3203, -3204, -4203, or -4204, or\na Bender ISOMETER® iso165C-1, or equivalent IMD approved for automotive use.\nEquivalency may be approved by the officials’ based on the following criteria: robustness\nto vibration, operating temperature range, IP rating, availability of a direct output, a self-test\nfacility and must not be powered'
- `fb_rules.pdf:0305`: 'rly marked with the lettering “IMD” must light up if the\nIMD opens the shutdown circuit. It must stay illuminated until the error state has been\nmanually reset (see EV6.1.6). Signals controlling this indicator are SCS (see T11.9).\n+ Version 1.4 | 05.23.2024 | Adaptation of FS-Rules 2024 v1.1\n103 / 137\n\n\nFORMULA BHARAT\n2025 RULES BOOKLET\nEV7\nCHARGERS\nEV7.1\nChargers General Requirements\nEV7.1.1\nOnly chargers presented and sealed at technical inspection are allowed. All connections of\nthe charger(s'


## T5b.2 -- citation precision vs. accumulated-set size (n=52)

Pearson r = -0.380 between `len(retrieved)` and `citation_precision` across every `agentic-v1` entry with both values defined.

**Reading: negative and non-trivial (r=-0.380)** -- consistent with the dilution hypothesis: a larger accumulated chunk set predicts lower citation precision.

## Verdict (T5b.1): predominantly load-bearing, not swept-in noise -- 15 of 20 extra citations

Read every one of the 20 non-gold-overlapping citations across the 12 regressions against the model's own answer text, checking whether the cited chunk's content actually appears in the reasoning (load-bearing) or never surfaces there at all (adjacent, swept in unused):

| entry | extra citations | load-bearing | adjacent/unused |
|---|---|---|---|
| q-005 | 0196, 0198, 0302 | all 3 (master-switch/TSMS reasoning explicitly walks through T11.2.1, T11.3, EV6.2) | none |
| q-019 | 0076, 0077 | 0077 (A5.8.5 revocation policy, named in the answer) | 0076 (TMI submission fields -- never mentioned) |
| q-020 | 0300 | none | 0300 (accumulator current timing -- never mentioned) |
| q-021 | 0144 | 0144 ("standard FSAE IA" section, quoted at length) | none |
| q-024 | 0114, 0115 | both (T3.2.4 yield strength and T3.2.6 support-tube rule, both quoted) | none |
| q-028 | 0225 | 0225 (gauge/paddock/hand-held rules, all three paraphrased in the answer) | none |
| q-031 | 0171, 0172 | 0172 (T5.6.1 anti-submarine anchorage, quoted) | 0171 (shoulder-harness T5.5.2 analysis -- carried over from the prior turn's own topic, never used in this answer) |
| q-034 | 0008 | 0008 (model/year table, directly informs the Gallardo-vs-Aventador comparison) | none |
| q-035 | 0005 | 0005 (the 996's 31 kg figure, explicitly referenced as the comparison point) -- but this is prior-turn content the *current* turn's gold span structurally can't credit | none |
| q-047 | 0390 | 0390 (D7.7.1 endurance fueling ban, named in the answer) | none |
| q-051 | 0176, 0177, 0178 | 0177, 0178 (T6.1.12 regen braking and T6.3.1 brake light, both quoted) | 0176 (T6.1.7-10 general mounting rules -- never mentioned) |
| q-056 | 0303, 0305 | 0305 (IMD indicator light behavior, named in the answer) | 0303 (IMD hardware model/certification -- never mentioned) |
| **total** | **20** | **15 (75%)** | **5 (25%)** |

**This revises Phase 4's own diagnosis, not just confirms it.** The majority of what drags precision down is not the model citing material it never used -- it's the model giving a *more complete* answer than the narrow gold span credits, and correctly citing the real supporting rules that completeness rests on (q-005's master-switch aside, q-021/q-024/q-028/q-051's fuller rule enumerations, q-034/q-035's cross-turn reasoning). T5b.2's negative correlation is real, but it is at least partly explained by "harder questions accumulate more chunks *and* warrant fuller, more-cited answers" rather than purely "more context makes the model cite carelessly." 5 of 20 (`q-019`/0076, `q-020`/0300, `q-031`/0171, `q-051`/0176, `q-056`/0303) look like genuine adjacent noise never referenced in the answer at all -- that's the actual, narrower target a citation-discipline prompt could plausibly hit.

**Implication for M6:** a "cite tightly" instruction has a real but narrow target -- roughly a quarter of the extra citations, not the bulk of them. Suppressing the load-bearing 75% would mean asking the model to give *less complete, less transparent* answers, not tighter ones. Expect the cheap 20-entry subset run (T6.2) to move citation precision modestly if at all, not dramatically -- this is a data-grounded expectation to check the subset result against, not a reason to skip it, since the ~250K cost is cheap insurance against being wrong about the split either way.
