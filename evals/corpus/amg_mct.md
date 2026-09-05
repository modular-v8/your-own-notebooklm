# The AMG SpeedShift MCT: The Automatic That Threw Away Its Torque Converter

*How Mercedes-AMG got a Torque Converter automatic gearbox to shift almost as fast as a dual-clutch — by deleting one component.*

---

## The problem AMG was trying to solve

By the mid-2000s the automatic transmission was in the middle of an arms race. Volkswagen and Audi had launched the first DSG dual-clutch boxes, BMW was persisting with its jerky single-clutch SMG, and Ferrari and Lamborghini were running automated single-clutch "F1" units. Everyone was chasing the same thing: a lightning-fast, uninterrupted gear change.

Mercedes-AMG at that time had a good automatic for its regular vehicles, but it was a *torque-converter* automatic, which was traditionally not the sportiest type of gearbox. However, in 2005 AMG introduced **AMG SpeedShift** on the SLK 55 AMG — a performance-tuned version of the then-new 7-speed 7G-Tronic (transmission family **722.9**), sharing its gear ratios but with sharper AMG software. The performance torque-converter version was later branded **SpeedShift TCT** ("Torque Converter Technology") and **7G-Tronic Sport**.

The catch: a torque converter, however well tuned, uses a fluid coupling. That fluid slips, it stores rotational inertia, and it puts a soft, "slushy" layer between the engine and the wheels. It was never going to match a DCT's directness or shift speed.

## The unusual fix: delete the torque converter

Rather than engineer a whole new dual-clutch box, AMG did something more surgical. They took the existing 7-speed **722.9** planetary architecture and **replaced the torque converter and its lock-up clutch with a single compact wet start-off clutch** — in German, a *Nass-Anfahrkupplung* (NAK). The result debuted in **2008** in the **R230 SL 63 AMG**, coupled with the legendary 6.3 litre AMG V8, and was the first transmission of its kind fitted to a production car. It was called **AMG SpeedShift MCT** — Multi-Clutch Technology.

One might assume the "Multi-Clutch" name refers to a dual-clutch box, but that's not the case. The new gearbox had a **single input shaft** and a **single multi-plate wet clutch** doing the job the torque converter used to do — getting the car moving from a standstill and locking up at high speed. Instead, "Multi-Clutch" referred to the multiple internal clutches and brakes of the *planetary* gearset — the same clutches (K1/K2/K3) and brakes (B1/B2/B3/BR) that the standard 722.9 torque-converter gearbox already used to select each of its seven gears.

### Why a wet clutch beat the converter

The start-off clutch ran in an **oil bath** (a sump), which cooled it and protected its service life under repeated hard launches. More importantly for performance, that clutch had a **much lower rotational inertia** than a fluid-filled torque converter — around 60% lower, in fact. Less inertia and no fluid slip means:

- **Sharper throttle response** and a direct, mechanical connection between engine and wheels.
- **No converter slip losses**, which also **helps fuel economy** — an unusual side-benefit for a performance box.
- The clutch engagement could be **fully computer-controlled**, which unlocked aggressive, precisely-metered shifts.

## The numbers that made it matter

- **Shift time: as low as 100 ms (0.1 s)**, depending on the drive mode.
- **Weight: about 80 kg**, roughly **18% lighter** than AMG's torque-converter 7G-Tronic, but more importantly, the **inertia of all the rotating parts was cut by ~30%**.

## The party tricks: RaceStart, rev-matching, and gear-skipping

Because the clutches were electronically orchestrated, the MCT could do things a torque-converter automatic couldn't:

- **Automatic double-declutch (rev-matching) downshifts** — the box blipped the engine to match revs on the way down, exactly like a skilled driver heel-and-toeing a manual. Mercedes marketed this as the *Zwischengas* function.
- **Multiple-gear downshifts in a single move** — it could skip straight from, say, 7th to 4th to grab peak torque without stepping through every intermediate ratio.
- **RaceStart** — a launch-control function that managed torque and traction for a clean, repeatable standing start, coordinated by AMG's new central **AMG DRIVE UNIT** controller.

## How close did it actually get to a DCT?

Based on the consensus from long-term MBWorld owners:

- A DCT can shift a *sequential* change (next gear pre-selected) in roughly **50 ms** — still faster than the MCT's ~100 ms for a single shift. **On a track, where shifts are predictable, a DCT wins.**
- But a DCT is only that fast when the *next* gear is pre-armed. Ask it for an **out-of-sequence** change (a big multi-gear downshift) and it slows right down. The **MCT shifts an out-of-sequence, multi-gear change as fast as a single one** — which is why several owners prefer it on the road.
- The trade-off for that directness is refinement. Because there's a real clutch and a relatively light flywheel instead of a fluid coupling, the box is **more direct and, at light throttle, occasionally jerky** — owners describe small jolts between gears in normal driving, and note it rewards deliberate throttle inputs. That's the physics of a direct connection, not a fault.

## Servicing: it behaves like a clutch, not a converter

One practical consequence of deleting the torque converter shows up at service time. On a normal 722.9 / 7G-Tronic, fluid is trapped inside the converter and needs its own drain. **The MCT has no converter, so effectively all the fluid drains through the main plug.** As with the 722.9 it's based on, the fill is temperature-critical and procedure-critical — Mercedes' own 722.9 training material specifies filling to an overflow level with the fluid brought to a defined temperature window, and MCT owners echo that the box needs proper warm-up cycles and an exact fill or it will misbehave. Do it wrong and you get the slipping and shudder complaints that populate the AMG forums.

## The sequel: the 9-speed MCT

The concept outlived the 7-speed. From 2017 onwards, starting with the **W213 E63**, AMG applied the same idea to the newer **9G-Tronic** (transmission generation **NAG3 / 725.0**), again swapping the torque converter for a wet start-off clutch, to create the **world's first 9-speed multi-clutch automatic**, rated to handle around **900 N·m**. It kept the double-declutch and RaceStart features, added a fuel-saving **coasting** function that opened the clutch when cruising off-throttle, and — according to owners — communicated far more directly over the car's CAN bus than the older 7-speed, which had a laggier control path and noticeably delayed paddle response. 

This concept was so successful that today, in the world of rapid DCTs and equally rapid traditional Torque Converter Gearboxes, you can still buy a brand new AMG with a modern, polished version of **9G-Tronic**, which traces its roots back to the **7G Tronic Speedshift**

---

## Bottom line

I secretly love the imperfect automatic gearboxes that surfaced in the 2000s, because they were the stepping stones that eventually led to the current, *perfect* auto-boxes. Many such gearboxes have their own quirks and uniqueness. The AMG SpeedShift MCT is just one of them. It is a lovely piece of lateral thinking: instead of adopting the industry's fashionable DCT, AMG kept the proven, torque-tolerant planetary gearset of the 722.9 and attacked the *one* component holding it back — the torque converter. Swapping it for a computer-controlled wet clutch bought most of a DCT's directness and speed, added rev-matched multi-gear downshifts a DCT struggles with, saved weight and fuel, and did it all through a single input shaft. It's the automatic that got fast by giving up the thing that made it an automatic.

---

## Sources

1. Mercedes-Benz 7G-Tronic transmission — Wikipedia (TCT / AMG SpeedShift, SLK 55 AMG 2005, 722.9 family, magnesium casing, emergency modes). https://en.wikipedia.org/wiki/Mercedes-Benz_7G-Tronic_transmission
2. "Mercedes-AMG's MCT Transmission Explained In Layman's Terms" — autoevolution (wet start-off clutch, single input shaft, mode percentages, 100 ms, not a DCT, 9-speed). https://www.autoevolution.com/news/mercedes-amg-s-mct-transmission-explained-in-layman-s-terms-112461.html
3. "Mercedes-AMG's MCT Transmission: Design Peculiarities and Principle of Operation" — go4trans (80 kg, ~18% lighter, ~30% lower inertia, 7,200 rpm, oil-bath clutch, fuel economy). https://go4trans.com/technical-transmission-general-articles/mercedes-amgs-mct-transmission-design-peculiarities-and-principle-of-operation/
4. Mercedes-Benz 9G-Tronic transmission — Wikipedia (NAK / Nass-Anfahrkupplung, computer-controlled double-clutching, AMG Drive Unit, RaceStart, 900 N·m, first in E63 4Matic+). https://en.wikipedia.org/wiki/Mercedes-Benz_9G-Tronic_transmission
5. "New 7-speed AMG SPEEDSHIFT MCT" — paultan.org, 11 Feb 2008 (debut on SL 63 AMG, wet start-up clutch replacing converter, four drive modes, single clutch — not a DCT). https://paultan.org/2008/02/11/new-7-speed-amg-speedshift-mct-debuts/ (archived: https://web.archive.org/web/20090131170842/http://paultan.org/archives/2008/02/11/new-7-speed-amg-speedshift-mct-debuts/)
6. 2008 Mercedes-Benz SL 63 AMG (R230) — autoevolution (MCT debut car, 100 ms shifts, four modes, RaceStart, M156 engine). https://www.autoevolution.com/cars/mercedes-benz-sl-63-amg-r230-2008.html
7. "Getriebe fragen c55/c63" — mercedes-forum.com (C63 W204 uses SpeedShift PLUS 7G-Tronic with torque converter + Zwischengas; NAK/MCT was in the SL 63, not the early C-Class). https://www.mercedes-forum.com/threads/getriebe-fragen-c55-c63.61223/
8. "2016 Mercedes-Benz E 63 S AMG SPEEDSHIFT MCT Transmission" — MB of Scottsdale blog (wet clutch, lower rotational inertia vs converter, smoother/more responsive). https://www.mbscottsdale.com/blog/2016-mercedes-benz-e-63-s-amg-speedshift-mct-transmission/
9. "AMG SPEEDSHIFT MCT 9G Automatic Transmission" — MBWorld.org forum (single multi-plate clutch vs converter, DCT ~50 ms vs MCT <100 ms, out-of-sequence shift advantage, CAN-bus directness, fluid-drain difference, MCT introduced with 2008 SL63, C63 got it at facelift; owner impressions of direct feel, occasional low-throttle jolts, light flywheel, throttle-modulation needed). https://mbworld.org/forums/c63-c63s-amg/923640-amg-speedshift-mct-9g-automatic-transmission.html
10. "AMG Speedshift-Getriebe?" — Motor-Talk (MCT debut 2008 in SL 63 AMG; wet start-off clutch in oil bath, low inertia, fuel saving). https://www.motor-talk.de/forum/amg-speedshift-getriebe-t6536718.html
11. Mercedes-Benz 722.9 Automatic Transmission — Technical Training (Tech 331), attached PDF (base 722.9 architecture, magnesium housing, temperature-critical overflow fill procedure, drain/fill via oil pan). Also cross-referenced: "Getriebe rutscht kurz e63 AMG m157" — stern-freunde.de (NAK diagnosis, slip/hotspot discussion). https://stern-freunde.de/forum/thread/9299-getriebe-rutscht-kurz-e63-amg-m157-oder-auch-nicht/
12. PistonHeads — C63 AMG buying guide, powertrain section. https://www.pistonheads.com/news/ph-buying-guide-contents/c63-amg-buying-guide-powertrain/31870
13. YouTube video (clutch vs. torque-converter inertia comparison, ~60% lower inertia figure). https://youtu.be/NVBmUNqs30g?si=sZWFOqCrkkuXMIMg