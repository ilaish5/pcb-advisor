# Cheatsheet - Altium Education units 1-4 (Hebrew)

> Compact study summary of the full English course text in `../altium-education/` (118 lessons). Fastest place for a fact or a number; go to the unit files for the explanation.

---

## יחידה 1 — Introduction to PCB Design

### ארבעת מסמכי התכן (חובה לזכור מי מכיל מה)

| מסמך | מה יש בו |
|------|----------|
| **Schematic sheets** | הרכיבים, ה-nets, חיבורי power/ground, שמות nets, ports. "השרטוט החשמלי" |
| **Bill of Materials (BOM)** | רשימת **כל** הרכיבים בלוח. נוצר אוטומטית ע"י ה-ECAD. יוצא כ-PDF/Excel |
| **PCB layout** | המיקום הפיזי של כל אלמנט + ה-**stackup** |
| **PCB libraries** | ה-CAD data של הרכיב: symbol, footprint, 3D model, SPICE, וגם מידע רכש (MPN, ספקים, חלופות) |

**מה *אין* בסכמה:** מיקום פיזי, האם הקשר הוא trace/via/plane/polygon, איך הנחושת מנותבת בפועל.

### מונחי יסוד
- **PCB** — הלוח החשוף, בלי רכיבים. **PCBA** — לוח מורכב (עם רכיבים).
- **PCB fabrication** — הייצור של הלוח החשוף. **PCB assembly** — הלחמת הרכיבים.
- **Trace** (=track) — חיבור נחושת בין שני רכיבים.
- **Plane layer** — שכבה מלאה בנחושת רציפה. **Signal layer** — רק traces.
- **Multilayer PCB** — יותר משתי שכבות נחושת.
- **Stackup** (layer stack) — סידור השכבות.
- **Laminate** — החומר המבודד בין שכבות הנחושת.
- **Reference designator** (U33, R4...) — המפתח שמקשר בין symbol ↔ footprint ↔ שורה ב-BOM.

### סינכרון
שינוי בסכמה חייב להיות מיובא ל-layout ולהפך — **סינכרון דו-כיווני**. ב-Altium: `Design → Update PCB Document`.

### Altium 365
ענן לשיתוף פרויקטים (כמו Google Drive ל-PCB). `Make Available Online` / `Save to Server`.

---

## יחידה 2 — Schematics and Libraries

### Nets ו-Ports
- **Net** = חיבור חשמלי. כולל את *כל* הענפים של החוט, לא רק קו ישר. לכל net יש שם (אוטומטי אם לא נתת).
- **Power/Ground ports** — סמלים ייעודיים. **ברירת מחדל: כל ground מקבל את השם GND** — גם אם בחרת סמל אחר (earth/chassis). אם הם אמורים להיות grounds שונים פיזית — **חייב לתת שמות שונים**.
- **Port** — חיבור בין **גיליונות** (sheets) שונים. **לא** להשתמש ב-port לחיבור בתוך אותו גיליון.
- **Harness** — צרור של כמה ports יחד (אובייקט מתקדם ב-Altium).
- לחיבור בתוך אותו גיליון → **net name** או wire.

### סמלים ורכיבים
- **Pinout** — סידור הפינים; מספרי ושמות הפינים בסמל **חייבים להתאים ל-datasheet**.
- **Multi-part symbol** — רכיב גדול מפוצל לכמה סמלים: U33A, U33B... (אות בסוף ה-designator). עדיין **רכיב אחד עם footprint אחד**.
- סוגי פינים: input / output / bi-directional (משולשים בקצה הפין). **ברירת המחדל: passive**.

### Flat vs. Hierarchical
| | Flat | Hierarchical |
|---|---|---|
| מבנה | אוסף גיליונות ללא היררכיה (ברירת מחדל) | גיליון-על (top-level) עם sub-sheets בתוך קופסאות |
| חיבור בין גיליונות | ports + net names | **ports** |
| יתרון | פשוט | **שכפול מעגלים חוזרים** — תיקון במקום אחד מתעדכן בכל המופעים |

**כלל אצבע לבוחן:** מעגל שחוזר על עצמו כמה פעמים → **hierarchical**.

### Best practices בהצבת רכיבים בסכמה
- לקרוא **משמאל לימין** (inputs משמאל, outputs מימין).
- לקבץ רכיבים של אותו מעגל; להימנע מחוטים מצטלבים; להשתמש ב-net names במקום להצליב.
- להשתמש ב-**power/ground ports** ולא ב-I/O ports עבור מתח/אדמה.
- ב-IC גדולים — net names ו-ports במקום המון חוטים.

### שרשרת האספקה (Supply chain)
לבדוק לפני שמכניסים רכיב: **Stock, Authorized distributor** (לא reseller/מזויף), **MOQ**, **Lifecycle** (obsolescence), **Price**.
כלים: **Manufacturer Part Search** (בתוך Altium — רכיב שנבחר יורד אוטומטית ל-Components panel), **Components panel** (רק מה שמותקן מקומית), **Octopart** (מרכז נתוני מלאי ומחיר ממספר מפיצים).

### מעבר ל-Layout
1. יצירת PCB ריק → 2. הגדרת **צורה וגודל הלוח** → 3. הגדרת **stackup** → 4. ייבוא רכיבים.
- **Engineering Change Order (ECO)** — הדיאלוג שמראה שגיאות לפני הייבוא; שגיאה נפוצה: **Footprint Not Found**. מסיימים ב-`Execute Changes`.
- אחרי הייבוא רואים **קווים לבנים (ratsnest)** = החיבורים שצריך לנתב.
- **עובי לוח סטנדרטי: 1.57 mm = 62 mil** (נפוץ גם 1 mm / 40 mil).
- **Copper weight**: 0.5 oz/ft² או 1.0 oz/ft². **1.0 oz/ft² ≈ 35 µm** נחושת.
- **Dk** (dielectric constant) ו-**Df** (loss tangent) — קובעים איך אותות מתפשטים.
- צורת לוח: נחתכת ב-**CNC router** — **לא ניתן לייצר פינה פנימית חדה של 90°**; יישאר רדיוס בגודל מקדח הראוטר (עד ~0.1 mm). פינה **חיצונית** 90° — אין בעיה.

---

## יחידה 3 — PCB Layout

### אנטומיה של לוח
- **Solder mask** — השכבה שנותנת את הצבע (בד"כ ירוק), מגדירה איפה יש הלחמה.
- **Silkscreen** — האותיות/לוגו המודפסים. אסור שיודפס על נחושת חשופה (פגם ייצור); מותר מעל נחושת מכוסת solder mask.
- **Plating / surface finish** — זהב, בדיל, ניקל, כסף. שתי מטרות: **קבלת הלחמה** + **הגנה מקורוזיה**.
- **Core** — למינציה קשיחה מצופה נחושת משני צדדים. **Prepreg** — שכבת "דבק" שמחברת cores.
- רכיבים: **Through-hole** (רגליים דרך חורים) מול **SMD/SMT** (פדים שטוחים על פני השטח).

### Stackup תקני (4 שכבות)
מאפיינים: **core ו-prepreg לסירוגין**, **סימטרי** סביב המרכז, **מספר זוגי** של שכבות נחושת, עובי כולל ~**1.57 mm**.

### תפקידי Ground plane (למה כמעט תמיד צריך)
- מיסוך מרעש RF חיצוני
- נתיב לפינוי חום
- ביחד עם power plane צמוד — מתנהג כמו **קבל גדול** → מתח DC יציב
- השראות נמוכה במוליכים → פחות EMI
- **מבטיח שהעכבה (impedance) של ה-traces תהיה אחידה בכל הלוח** ← הכי חשוב לניתוב USB/HDMI/Ethernet

**מוסכמת שמות שכבות:** GND (AGND/DGND), PWR, SIG_1/SIG_2...
**שים לב:** קריאת שכבה בשם "GND" **לא** מחברת אותה אוטומטית ל-net GND — זה נעשה בשלב ה-routing.
רוצים כמה מתחים באותה שכבה / polygon עם חיתוכים? → מגדירים אותה כ-**signal layer** ומציירים polygons.

### בחירת חומרים
- **Dk** — משפיע על התפשטות אותות ועל עכבת ה-traces.
- **Tg** (glass transition temperature) — 130 °C לחומר זול, **150/170 °C** לאמינות גבוהה.
- **IPC-4101 slash sheets** — מסמכים שמגדירים אילו קריטריונים חומר למינציה חייב לקיים, ומתי שני חומרים תואמים לאותו תהליך ייצור. דוגמה להערה בשרטוט: `ALL STACKUP MATERIALS SHALL CONFORM TO IPC-4101 /24`.

### מה מבקשים מהיצרן (fabricator) — לפני התכן
- **Fabrication capabilities statement** — המגבלות שלו.
- **Stackup table** — הרכבי שכבות מומלצים ← זה מה שעוזר לבנות layer stack.

### קבצי ייצור
| קובץ | מה הוא |
|------|--------|
| **Gerber** | איפה נחושת, solder mask, silkscreen, solder paste |
| **Drill file** | קואורדינטות וגדלים של כל החורים |
| **Pick-and-place** | קואורדינטות רכיבים למכונת השיבוץ |
| **Panel drawing** | איך הלוחות מסודרים על הפאנל |
| **Fab & assembly drawings** | מיקום רכיבים, drill hits, סדר שכבות |

לפני שליחה: **DRC (Design Rule Check)** ידני (`Tools → Design Rules Check`) + Functional / Supply chain / Mechanical / Application review. אחר כך היצרן עושה **DFM review** משלו.

### קטגוריות Design Rules (`Design → Rules`)
| קטגוריה | מה קובעת |
|---------|----------|
| **Electrical** | clearances, short circuit, unrouted net, creepage |
| **Routing** | רוחב trace, טופולוגיה, פינות |
| **SMT** | פדי SMD, **SMT entry** (מאיזה כיוון trace נכנס לפד) |
| **Mask** | solder mask expansion, paste mask expansion (SMD מול NSMD) |
| **Plane** | clearance של planes/polygons מ-vias, **thermal reliefs** |
| **Testpoint** | נקודות מדידה (pad או via) |
| **Manufacturing** | גדלי חורים, copper-to-edge, silkscreen clearances, slivers |
| **High Speed** | אותות דיגיטליים מהירים |
| **Placement** | clearance תלת-ממדי, גבהים |
| **Signal Integrity** | גבולות עיוות אות |

**חשוב:** clearance של via ל-plane מוגדר ב-**Plane rules**, לא ב-Electrical (planes/polygons הם אובייקטים אחרים).

### ערכי clearance בטוחים (אם אין נתונים מהיצרן)
- **copper-to-copper מינימלי: 4 mil**
- **via hole-to-via hole: 8 mil** (גדול יותר בגלל **drill wander**)
- **solder mask sliver: 5 mil**

### סדר עבודה ב-Layout
1. Design rules → 2. board outline → 3. stackup → 4. הצבת רכיבים → 5. ניתוב.
**סדר הצבה:** מעבדים גדולים (במרכז) → כניסות מתח → מחברים (על הקצה, לפי האנקלוז'ר) → רכיבי **RF** (באזור מבודד משלהם).
המטרה בהצבה: **למזער הצטלבות nets** (כל הצטלבות = מעבר שכבה).

### ניווט ב-PCB Editor
- **Shift+S** — מצב שכבה בודדת. **`*` / Shift+`*`** — מעבר בין שכבות signal בלבד.
- **View Configuration panel** — הדלקה/כיבוי שכבות, שקיפות.
- **Shift + hover** — **net highlighting**: כל האובייקטים באותו net מקבלים מתאר לבן.
- **Selection filter** (Properties panel) — לבחור רק סוג אובייקט מסוים.

---

## יחידה 4 — Routing and Basic Signal Integrity

### Traces
- **Microstrip** — על שכבת שטח. **Stripline** — בשכבה פנימית.

| | Microstrip | Stripline |
|---|---|---|
| הפסדים | **נמוכים יותר** | גבוהים יותר |
| מיסוך EMI | חלש (אפשר לשפר עם ground pour) | **טוב** (planes משני צדדים) |
| רוחב לאותה עכבה | **רחב יותר** | צר יותר |
| מהירות אות | **מהיר יותר** | איטי יותר |
| קרינה/crosstalk | חזקה יותר | נמוכה יותר |

- **כלל 3W** — מרווח בין traces = פי 3 מהרוחב, למניעת **crosstalk**.
- רוחב טיפוסי ללא בקרת עכבה: **7–12 mil**. עכבה נפוצה: **50 Ω** (זוג דיפרנציאלי: **100 Ω**).
- מה קובע רוחב: (1) יעד עכבה, (2) יכולת נשיאת זרם — מעל ~**1 A** עדיף **polygon**, (3) צפיפות.
- **זוויות:** ברירת מחדל 45°; פנייה של 90° נעשית משתי פניות 45°. הטענה ש-90° יוצר רעש היא **מיתוס** — רלוונטי רק בעשרות GHz.
- **Polygons** — לזרם גבוה, מישורי מתח, ground, ומבנים ל-RF (אנטנה/מסנן).

### Vias
- שני מרכיבים: **drilled hole** + **pad / annular ring**.
- **קדח מינימלי לייצור אוניברסלי: 8 mil** (נפוץ 10–12 mil). קטן מזה → **laser drilling**. אחרי ציפוי הקדח קטן ב-1–2 mil.
- סוגים: **Through-hole** (כל העובי) / **Blind** (שטח→פנימית) / **Buried** (פנימית→פנימית) / **Microvia** (לייזר, עד 3 mil, **שכבה אחת בלבד**).
- וריאציות: **Tented** (מכוסה solder mask), **Via in pad**, **VIPPO** (ממולא ומצופה נחושת), **Plugged** (אפוקסי לא מוליך), **Filled** (משחה מוליכה — זרם גבוה).
- **Teardrops** — הרחבה מעוגלת במעבר trace→pad, מגבירה **אמינות** מול **drill wander**. לא נחוצים אם ה-trace והטבעת באותו גודל.
- ה-trace צריך להיכנס ל-annular ring **ישר**, לא בזווית.

### IPC-6012 — מחלקות ביצועים (annular ring)
| Class | שימוש | דרישת טבעת |
|-------|-------|------------|
| **1** | מוצרים חד-פעמיים | אין דרישה |
| **2** | מוצרים לשימוש ארוך/אמין | **≥ 4 mil** → קוטר pad ≥ קדח **+ 8 mil** |
| **3** | כשל מסכן חיי אדם | **≥ 5 mil** → קוטר pad ≥ קדח **+ 10 mil** |

הפרת דרישת annular ring היא סיבה נפוצה לכישלון ב-DFM review.

### Single-ended מול Differential
- **Single-ended** — מתח נמדד בין ה-trace ל-**ground plane**.
- **Differential pair** — שני traces, אותות שווים והפוכים; המתח הוא ההפרש. דוגמה: +350 mV ו-−350 mV → **700 mV** בקצה המקבל.
- שמות: `NetName_P` / `NetName_N`.
- כללי ניתוב: **אורך שווה** (בתוך סבילות), **מרווח קבוע לאורך כל הנתיב** (הוא שקובע את העכבה), נתיב קצר וישיר, **שני הצדדים על אותה שכבה** (כדי שהמהירות תהיה זהה).
- **Length matching / meanders** — מוסיפים ל-trace הקצר כדי שהאותות יגיעו **בו-זמנית** → ביטול רעש מצב-משותף בקצה המקבל. נדרש גם ל-**באסים מקבילים single-ended** (למשל **DDR**).
- הרכיב/הפרוטוקול קובע **אם** צריך זוג דיפרנציאלי; המתכנן קובע **איפה** לנתב (פנימי/חיצוני).

### עכבה
- נקבעת ע"י גאומטריית ה-trace + **מרחק ממישור הייחוס (H)** + Dk. לכן **קובעים stackup לפני שקובעים רוחב**.
- נוסחאות **IPC-2141** (microstrip/stripline, single-ended בלבד); מדויקות יותר: משוואות **Waddel**. לזוגות דיפרנציאליים אין נוסחה סגורה טובה → משתמשים במחשבון/**impedance solver** ב-**Layer Stack Manager** (טאב Impedance).
- **Impedance Profile** → מוקצה ל-nets דרך `Routing → Width` / `Routing → Differential Pairs Routing`.
- **Net Class** — קיבוץ nets לפי ממשק (USB עם USB, Ethernet עם Ethernet) כדי להחיל חוק אחד על קבוצה.

**טבלת המרה — Copper weight:**

| משקל | mil | µm |
|------|-----|-----|
| 0.5 oz/ft² | 0.671 | 17.05 |
| 1.0 oz/ft² | 1.34 | 34.1 |
| 2.0 oz/ft² | 2.68 | 68.1 |
| 3.0 oz/ft² | 4.02 | 102.2 |

### שני כללי הזהב של מישור הייחוס
1. **תמיד לנתב אותות משתני-זמן (דיגיטלי/אנלוגי) מעל ground plane רציף.**
2. **לחבר את כל אזורי ה-ground זה לזה** ב-vias/נחושת.
מעבר מעל **פיצול (split)** במישור → **אי-רציפות עכבה** + הפרשי פוטנציאל ⇒ האות שנמדד ב-load שונה מהמקור.

מתי בכל זאת מותר לעבור מעל split: אות **DC**; אות שמשנה מצב לעיתים רחוקות (פין קונפיגורציה). **אסור** ב-bitstream דיגיטלי, ב-PWM של רגולטור מיתוג, וב-RF.
**מעבר שכבות:** להצמיד **ground via** ליד ה-signal via (רצוי S ≈ H).

### באסים דיגיטליים

| | **I2C** | **SPI** | **UART** |
|---|---|---|---|
| מספר קווים | 2 (SCL, SDA) | ≥3 (SDO/SDI/SCK + CS) | 2 |
| קצב | עד **3.4 Mbit/s** | עד **60 Mbit/s** | עד **1.5 Mbit/s** |
| עכבה מבוקרת | לא | לא | לא |
| שעון | source synchronous | source synchronous | **אין** (אסינכרוני) |
| טופולוגיה | serial bus | serial bus | serial bus |

**I2C — מספרים לזכור:** זרם כולל בבאס **≤ 3 mA**; לוגי-0 מוגדר 0–0.4 V; **קיבול כולל ≤ 400 pF** בקצב 3.4 Mbit/s (כל רכיב ~10 pF); נדרשים **pull-up resistors ≥ 1 kΩ**; אורך מסלול מומלץ **≤ 10 cm** עם traces ~10 mil.
**ESD:** נהוג לשים **TVS diode** על באס שמגיע למחבר חשוף.
**SPI:** מוצא push-pull CMOS ⇒ **לא צריך pull-ups**. שמות ישנים MISO/MOSI/SS ⇒ חדשים SDI/SDO/CS. סיום קו ארוך: נגד טורי ~**22 Ω** במקור + trace ל-**50 Ω** + נגד מקביל ל-GND בסוף.
**UART:** אסינכרוני, שני קווים single-ended + ground משותף.

### מה הופך תכן ל-"High Speed"
- **לא** קצב השעון — אלא **זמן העלייה (rise time)**. שעון איטי יכול בהחלט לשאת מעברים מהירים.
- rise time נמדד **10%→90%**. ערך טיפוסי: **~5 ns**. מ-**~10 ns ומטה** מתחילות בעיות signal integrity.
- ממשקים "איטיים" (<~100 Mbps): SPI, UART, I2C, I2S, CAN, Ethernet 10/100Base.
  ממשקים מהירים: USB, LVDS, HDMI, MIPI, Ethernet 1G+, DDR, PCIe, SATA.

### מתי צריך התאמת עכבה (termination)
משווים את **אורך ה-trace** למרחק שהאות עובר בזמן המעבר: **L = v·T**, כאשר `v = c/√Dk`.
- FR4 עם **Dk = 4** → `v = 3·10⁸/2 = 1.5·10⁸ m/s`.
- rise time **5 ns** → L = **0.75 m** (750 mm) → כמעט כל trace קצר בהרבה ⇒ **אין צורך בבקרת עכבה** (ה-load שולט).
- rise time **0.25 ns** → L = **3.75 cm** → trace ארוך מזה **חייב** עכבה מבוקרת (50 Ω, או 100 Ω לזוג).

**עכבות בפועל:** כניסת CMOS ~**1 MΩ** (גבוהה), מוצא CMOS ~**0.1 Ω** (נמוכה), trace ~**50 Ω** ⇒ אי-התאמה.
פתרון: **נגד טורי במקור** + **נגד מקבילי ל-GND ב-load**. ברכיבים מודרניים זה נעשה ע"י **on-die termination**.

### Crosstalk
- **Aggressor** — ה-trace שמשרה. **Victim** — זה שקולט.
- **Inductive coupling** (שדה מגנטי) — דומיננטי בתדרים **נמוכים** ⇒ זה מה שרלוונטי ברוב הלוחות.
- **Capacitive coupling** (שדה חשמלי) — דומיננטי בתדרים **גבוהים מאוד** (RF, Gbit/s).
- ככל שה-rise time **מהיר יותר**, ה-crosstalk **חזק יותר**.
- שלוש דרכים להקטין: (1) נגד טורי קטן במקור שמאט את ה-rise time — **הכי פחות רצוי** כי מחליש את האות, (2) ניתוב **מאונך** בין שכבות סמוכות, (3) **ground plane + דיאלקטרי דק → יחס w/h גדול** — **הדרך היעילה ביותר**.

### EMI / EMC
- למה אכפת לנו: **דרישה חוקית**. מוצר חייב לעבור בדיקות EMC לפני שיווק.
- **Radiated EMI** — קרינה. רגולציה: **FCC** (ארה"ב), **CISPR** (אירופה).
  - **Intentional radiators** — מכשירים אלחוטיים; מותר להם לקרון רק בפס שלהם.
  - **Unintentional radiators** — **Class A** = סביבה תעשייתית, **Class B** = סביבה ביתית.
- **Conducted EMI** — זרמים שעוברים בכבל/traces. שני סוגים: **common-mode** ו-**differential-mode**. **common-mode מסוכן פי ~100** מבחינת עוצמת הקרינה.
- **ESD** — פולס זרם גדול; מגיע דרך **מוליכים חשופים** (מעטפות מחברים). פתרון: לחבר לשלדה/earth, ואם אי אפשר — ל-ground plane; ומעגלי הגנה (TVS).
- **מסננים בכניסת/יציאת מתח:** **Ferrite choke** (סביב הכבל; מסנן common וגם differential; **לא** לשים במוצא רגולטור DC), **Common-mode choke coil** (סליל זוגי; מטפל בסוג אחד בכל פעם), **LC filter** (low-pass).
- **הימנע מ-split ground plane** אלא אם חייבים. חריגים לגיטימיים: בידוד גלווני במערכות הספק, מערכות אודיו/אנלוגי בתדר נמוך, ניתוב עם שנאי (Ethernet).
- מתכת באנקלוז'ר / גוף קירור — **לא להשאיר צף**, לחבר לאדמה; אך השלדה **לא** תהיה מוליך נושא זרם (סכנת התחשמלות).

### כללי ניתוב מסכמים
- להשתמש ב-ground plane ולחבר אליו דרך vias במקום לנתב GND על פני השטח.
- לתכנן קבוצות nets על אותה שכבה. **כלל 90-10**: 10% האחרונים של הניתוב לוקחים 90% מהזמן — לפתור קודם את הקל.
- לא לנתב הלוך-ושוב לרוחב הלוח — אם קורה, **להזיז רכיבים**.
- **Autorouter** — רוב המתכננים המקצועיים **לא** משתמשים: פותר רק לוחות פשוטים ודורש ניקוי ידני.
