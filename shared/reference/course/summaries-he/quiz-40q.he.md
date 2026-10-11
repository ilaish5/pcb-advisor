# Course quiz - 40 questions with answers and explanations (Hebrew + original English)

> The 40 questions of the Altium Education unit 1-4 quizzes, translated to Hebrew; the English original is under each question. Answers were verified against the course site. Questions marked 'multiple' have more than one correct option. Extracted 2026-10-11 from the interactive page `בוחן-תרגול-מלא.html` (now in `_set-aside/`).

## Unit 1 - Introduction to PCB design

### Q1. איזה מהמסמכים הבאים מכיל רשימה של כל הרכיבים המשמשים בלוח המורכב (PCBA)?
*Which of these documents contains a list of all components used in the PCBA?*

- a) רשימת רכיבים (Bill of materials)
- b) שרטוט הלוח (PCB layout)
- c) סכמה חשמלית (Schematic)
- d) ספריית רכיבים (Component library)

**Answer: a** - ה-BOM (Bill of Materials) הוא רשימת כל הרכיבים בלוח — נוצר אוטומטית ע״י ה-ECAD ומיוצא ל-PDF/Excel. הסכמה מציגה חיבורים, ה-layout מציג מיקום פיזי, והספרייה מכילה נתוני CAD של רכיב בודד. רק ה-BOM הוא הרשימה המלאה.

### Q2. איזה מהמסמכים הבאים מציג את תרשים המעגל והשרטוטים החשמליים עם החיבורים בין הרכיבים?
*Which of these documents shows circuit diagrams and electrical drawings with connections between components?*

- a) סכמה חשמלית (Schematic)
- b) שרטוט הלוח (PCB layout)
- c) רשימת רכיבים (Bill of materials)
- d) ספריית רכיבים (Component library)

**Answer: a** - הסכמה (Schematic) היא השרטוט החשמלי — מציגה רכיבים, nets והחיבורים הלוגיים ביניהם (מה מחובר למה). היא לא מתארת מיקום פיזי או איך הנחושת מנותבת — זה תפקיד ה-layout.

### Q3. איזה מהמסמכים הבאים מכיל reference designators של הרכיבים בלוח המורכב?
*Which of these documents contains reference designators for components in the PCBA?* (multiple)

- a) סכמה חשמלית (Schematic)
- b) שרטוט הלוח (PCB layout)
- c) רשימת רכיבים (Bill of materials)
- d) ספריית רכיבים (Component library)

**Answer: a, b, c** - Reference designator (U33, R4...) הוא המפתח שמקשר symbol ↔ footprint ↔ שורה ב-BOM. לכן הוא מופיע בשלושתם: סכמה, layout ו-BOM. הספרייה מגדירה את הרכיב הכללי אך לא נושאת designator של מופע ספציפי בלוח.

### Q4. איזה מונח מתאר את החיבור החשמלי בין שתי נקודות המשורטט בסכמה?
*Which term describes the electrical connection between two points drawn in a schematic?*

- a) Net
- b) שכבה (Layer)
- c) מוליך (Trace)
- d) חוט (Wire)

**Answer: a** - Net = חיבור חשמלי בסכמה, וכולל את כל ענפי החוט (לא רק קו בודד). לכל net יש שם. ה-Trace הוא המימוש הפיזי בנחושת ב-layout — כלומר ה-net הוא הלוגי וה-trace הוא הפיזי.

### Q5. איזה מונח מתאר את חיבור הנחושת בין שני רכיבים בשרטוט הלוח?
*Which term describes the copper connection between two components in a PCB layout?*

- a) מוליך (Trace)
- b) Net
- c) חוט (Wire)
- d) שכבה (Layer)

**Answer: a** - Trace (track) = חיבור הנחושת הפיזי בין שני רכיבים ב-layout. ה-net הוא המושג הלוגי בסכמה; ה-trace הוא איך הוא מנותב בנחושת בפועל.

### Q6. אילו מהפריטים הבאים כלולים בספריית רכיבים?
*Which of these items is included in a component library?* (multiple)

- a) סימבולים סכמטיים של רכיבים
- b) קובץ ה-layout של הפרויקט שלך
- c) מודלי סימולציה של רכיבים
- d) המוליכים והחוטים שמחברים את הרכיבים

**Answer: a, c** - ספריית רכיבים מכילה את נתוני ה-CAD של הרכיב: schematic symbol, footprint, מודל 3D, מודל SPICE (סימולציה) ומידע רכש. קובץ ה-layout וה-traces שייכים לפרויקט הספציפי — לא לספרייה.

### Q7. איזו תכונה בגיליון סכמה משמשת לציון חיבור חשמלי במקום חוט?
*Which feature in a schematic sheet can be used to indicate an electrical connection instead of a wire?*

- a) שם net (Net name)
- b) מוליך (Trace)
- c) שכבה (Layer)
- d) Track

**Answer: a** - net name מאפשר לציין חיבור חשמלי בלי למתוח חוט: שני פינים עם אותו net name מחוברים. זה מנקה את הסכמה ומונע חוטים מצטלבים. trace/track הם אובייקטים של ה-layout, לא של הסכמה.

### Q8. אם צריך לגשת למודל התלת-ממדי של רכיב בתכן שלך, איפה תחפש אותו?
*If you need to access the 3D model for a component in your design, where would you look?*

- a) ספריית רכיבים (Component library)
- b) שרטוט הלוח (PCB layout)
- c) סכמה חשמלית (Schematic)
- d) רשימת רכיבים (Bill of materials)

**Answer: a** - המודל התלת-ממדי הוא חלק מנתוני הרכיב בספרייה (יחד עם symbol ו-footprint). הוא משמש לבדיקת התנגשויות מכניות ולהתאמה לאנקלוז׳ר בזמן ה-layout.

### Q9. באיזה מסמך תכן ישתמש המרכיב (assembler) כדי לאתר את הרכיבים בשרטוט הלוח?
*Which design document will be used by an assembler to locate components in the PCB layout?*

- a) רשימת רכיבים (Bill of materials)
- b) ספריית רכיבים (Component library)
- c) שרטוט הלוח (PCB layout)
- d) סכמה חשמלית (Schematic)

**Answer: a** - ה-BOM מכיל את ה-reference designators והכמויות, ולכן משמש את המרכיב לזהות אילו רכיבים מולחמים והיכן (בשילוב assembly drawing). זו התשובה הרשמית של הקוויז.

### Q10. איזה מהאובייקטים הבאים בשרטוט הלוח מאפשר להעביר אותות בין שכבות?
*Which of the following objects in a PCB layout allows signals to transfer between layers?*

- a) Via
- b) מוליך (Trace)
- c) Net
- d) חוט (Wire)

**Answer: a** - Via = קדח מצופה נחושת שמעביר אות (או מתח/אדמה) בין שכבות. Trace מחבר באותה שכבה; net הוא מושג לוגי בלבד.

## Unit 2 - Schematics and libraries

### Q11. באיזה אובייקט משתמשים כדי להגדיר חיבור חשמלי בין שני גיליונות סכמה שונים?
*Which object would be used to define an electrical connection between two different schematic sheets?*

- a) Port
- b) שם net (Net name)
- c) חוט (Wire)
- d) מחבר (Connector)

**Answer: a** - Port מחבר חשמלית בין גיליונות (sheets) שונים. בתוך אותו גיליון משתמשים ב-net name או wire — אין להשתמש ב-port לחיבור בתוך אותו גיליון.

### Q12. מהו הכיוון המועדף לניתוב חיבורים חשמליים מכניסות אל מוצאים?
*What is the preferred direction to route electrical connections from inputs to outputs?*

- a) משמאל לימין
- b) מימין לשמאל
- c) מלמעלה למטה
- d) מלמטה למעלה

**Answer: a** - מוסכמת קריאות: inputs משמאל, outputs מימין, זרימה משמאל לימין. זה מקל על מעקב הגיוני אחרי המעגל.

### Q13. באיזה סוג אובייקט יש להשתמש בסכמה במקום חוטים מצטלבים?
*Which type of object should be used in a schematic instead of crossing wires?*

- a) Net names ו-ports
- b) ports בלבד
- c) net names בלבד
- d) אף אחד מאלה

**Answer: a** - כדי להימנע מחוטים מצטלבים משתמשים גם ב-net names וגם ב-ports — שניהם מציינים חיבור בלי קו פיזי מצטלב, ומשפרים קריאות.

### Q14. איזה מהנהגים הבאים יש להימנע ממנו בעת יצירת סכמות?
*Which of the following practices should be avoided when creating schematics?*

- a) לנסות למקם את כל המעגלים בגיליון סכמה יחיד
- b) להשתמש ב-ports ו-net names במקום חוטים מצטלבים
- c) להשתמש ב-ports של מתח ואדמה במקום שנדרש
- d) לנסות לקבץ רכיבים של אותו מעגל באותו גיליון סכמה

**Answer: a** - נוהג טוב הוא לפצל מעגלים לגיליונות לפי פונקציה; דחיסת כל המעגלים לגיליון יחיד פוגעת בקריאות ובתחזוקה. שאר האפשרויות הן דווקא best practices.

### Q15. אילו משימות צריך להשלים לפני העברת הרכיבים ללוח PCB ריק?
*Which tasks need to be completed before transferring components into an unpopulated PCB?* (multiple)

- a) להגדיר את צורת הלוח
- b) ליצור stackup ללוח
- c) להניח מוליכי נחושת עבור הרכיבים
- d) למקם vias בלוח הריק כדי לחבר שכבות שונות

**Answer: a, b** - לפני ייבוא רכיבים ל-PCB ריק: (1) להגדיר צורת/גודל הלוח, (2) להגדיר את ה-stackup. ניתוב traces והצבת vias נעשים אחרי הייבוא — כשכבר יש מה לנתב (ratsnest).

### Q16. איזה מהמידע הבא על חומרי הלמינציה של הלוח אינו נדרש בעת יצירת ה-stackup?
*Which of the following information about PCB laminate materials is not needed when creating the PCB stackup?*

- a) שם היצרן של חומר הלמינציה
- b) קבוע דיאלקטרי (Dk)
- c) משקל הנחושת (copper weight)
- d) עובי השכבה

**Answer: a** - ל-stackup צריך פרמטרים פיזיים: Dk (dielectric constant), עובי שכבה ו-copper weight. שם היצרן של הלמינציה אינו פרמטר תכן הכרחי לבניית ה-stackup.

### Q17. איזה סוג מסמך תכן משתמש ב-sub-sheets המחוברים ביניהם בדומה לרכיבים?
*Which type of design document uses sub-sheets that are wired together similar to components?*

- a) סכמות היררכיות (Hierarchical schematics)
- b) סכמות שטוחות (Flat schematics)
- c) תרשים מלבנים (Block diagram)
- d) PCB footprint

**Answer: a** - בסכמה היררכית יש גיליון-על (top) עם sub-sheets המחוברים דרך ports כמו רכיבים. היתרון: שכפול מעגלים חוזרים — תיקון במקום אחד מתעדכן בכל המופעים.

### Q18. כאשר לרכיב כמו IC יש מספר רב של פינים, הדרך הטובה ביותר למקם את החיבורים החשמליים היא:
*When a component like an IC has a large number of pins, the best way to place electrical connections is to use:*

- a) Ports ו-net names
- b) חוטים בלבד
- c) חוטים ו-ports
- d) net names בלבד

**Answer: a** - ל-IC עם הרבה פינים עדיף net names ו-ports במקום עשרות חוטים — זה מונע צלחת ספגטי ומשאיר את הסכמה קריאה.

### Q19. אילו בעיות ייווצרו אם לא תקצה שם net ל-net בסכמה?
*What problems will arise if you do not assign a net name to a net in a schematic?*

- a) כלום; התוכנה תקצה שם אוטומטית
- b) ה-net לא ייובא לשרטוט הלוח
- c) ה-net ייחשב כמעגל פתוח
- d) ה-net ייחשב כקצר חשמלי

**Answer: a** - אם לא נותנים שם ל-net, התוכנה מקצה שם אוטומטית — לא נגרמת שגיאה. עדיין מומלץ לתת שמות משמעותיים ל-nets חשובים (למשל power/clock) לקריאות.

### Q20. נניח שצריך למקם 8 עותקים של מעגל מורכב בסכמות. באילו סוגי סכמות כדאי להשתמש?
*Suppose we need to place 8 copies of a complex circuit into schematics. What types of schematics should be used?*

- a) סכמה היררכית אחת וסכמה שטוחה אחת
- b) סכמה היררכית אחת ו-8 סכמות שטוחות
- c) 8 סכמות שטוחות
- d) 8 סכמות היררכיות

**Answer: a** - מעגל חוזר → סכמה היררכית אחת (top) + גיליון flat אחד של תת-המעגל, שמופנה 8 פעמים. כך יש עותק מקור יחיד — תיקון בו מתעדכן בכל 8 המופעים.

## Unit 3 - PCB layout

### Q21. מה כדאי לקבל מהיצרן כדי שיעזור לך לבנות את מערך השכבות (layer stack)?
*What should you get from your fabricator that will help you build a layer stack?*

- a) טבלת stackup (Stackup table)
- b) הצהרת יכולות ייצור (Fabrication capabilities statement)
- c) דוח בדיקת כללי תכן (Design Rules Check report)
- d) שרטוט הרכבה (Assembly drawing)

**Answer: a** - ה-stackup table מהיצרן מפרט הרכבי שכבות מומלצים ובני-ייצור — זה מה שעוזר לבנות layer stack תקין. ה-capabilities statement נותן מגבלות כלליות (מינימום trace/via) אך לא את ההרכב עצמו.

### Q22. איזה מהחומרים הבאים משמש להדפסת reference designators וסימונים אחרים על שכבות פני הלוח?
*Which of these materials is used to place reference designators and other markings on the surface layers of a PCB?*

- a) Silkscreen
- b) Solder mask
- c) נחושת (Copper)
- d) ציפוי נחושת (Copper plating)

**Answer: a** - Silkscreen הוא ההדפס (אותיות, designators, לוגו) על פני הלוח. אסור שיודפס על נחושת חשופה. Solder mask נותן צבע/הגנה, נחושת היא המוליך.

### Q23. מהי איננה סיבה להחלת חומר ציפוי (plating) על לוח נחושת חשוף?
*Which of the following is not a reason that a plating material would be applied to a bare circuit board?*

- a) הוא מאפשר הלחמה בטמפרטורה נמוכה יותר
- b) הוא מספק משטח לחיבורי הלחמה חזקים
- c) הוא מגן מפני קורוזיה
- d) הוא מגן מפני שריטות ופגיעות אחרות

**Answer: a** - לציפוי (surface finish — זהב/בדיל/ניקל/כסף) שתי מטרות עיקריות: קבלת הלחמה טובה + הגנה מקורוזיה. הוא אינו מוריד את טמפרטורת ההלחמה — לכן זו התשובה ל״מה שאינו סיבה״.

### Q24. מה תפקידן של שכבות ה-prepreg ב-stackup של הלוח?
*What is the role of prepreg layers in a PCB stackup?*

- a) הן משמשות כדבק בין שאר השכבות
- b) היא משמשת להפרדת שתי שכבות משטח (plane layers)
- c) היא משמשת להפרדת שתי שכבות אותות (signal layers)
- d) היא משמשת להדבקת שתי שכבות prepreg אחרות

**Answer: a** - Prepreg הוא שכבת ״דבק״ שמחברת cores יחד ב-stackup. Core הוא הלמינציה הקשיחה מצופת נחושת משני צדדיה; ה-prepreg מלכד אותם לחבילה אחת.

### Q25. איזה מסמך מתוך תקני IPC-4101 משמש את יצרן הלוח לזיהוי חומרים תואמים ל-stackup?
*What document from the IPC-4101 standards will be used by a board fabricator to identify compatible materials for a PCB stackup?* (multiple)

- a) Slash sheets
- b) שרטוט ייצור (Fabrication drawing)
- c) טבלת stackup (Stackup table)
- d) שרטוט הרכבה (Assembly drawing)

**Answer: a, b** - ה-slash sheets של IPC-4101 מגדירים אילו קריטריונים חומר למינציה חייב לקיים ומתי שני חומרים תואמים לאותו תהליך ייצור (למשל הערה: ALL STACKUP MATERIALS SHALL CONFORM TO IPC-4101 /24). הקוויז מסמן גם fabrication drawing כנכון, כי בו רושמים את דרישת החומר.

### Q26. בתכנון מיקום הרכיבים בשרטוט הלוח, אילו רכיבים מומלץ למקם ראשונים?
*When planning component placement in a PCB layout, which components are recommended to be placed first?*

- a) מעבדים גדולים
- b) נגדים וקבלים קטנים
- c) מעגלים משולבים קטנים
- d) vias ומוליכים לניתוב

**Answer: a** - סדר הצבה: קודם הרכיבים הגדולים (מעבדים) במרכז, אחריהם כניסות מתח, מחברים על הקצה (לפי האנקלוז׳ר), ולבסוף רכיבי RF באזור מבודד. המטרה: למזער הצטלבות nets (כל הצטלבות = מעבר שכבה).

### Q27. איזה מידע מהרשימה הבאה צריך להיכלל בשרטוט הייצור (fabrication drawing) של הלוח?
*What information from the following list should be included in a PCB fabrication drawing?*

- a) שרטוט קידוח (Drill drawing)
- b) רשימת רכיבים (Bill of materials)
- c) שרטוט פאנל (Panel drawing)
- d) שרטוט אנקלוז׳ר (Enclosure drawing)

**Answer: a** - שרטוט הייצור (fabrication drawing) כולל drill drawing — מיקומי וגדלי החורים, סדר שכבות ומידות. BOM שייך להרכבה, panel/enclosure הם מסמכים אחרים.

### Q28. איזה מקבצי הייצור הבאים משמש להפיכת מיקום הרכיבים בהרכבה לאוטומטי?
*Which of these manufacturing files is to automate placement of components during assembly?*

- a) קובץ Pick-and-place
- b) קובץ NC drill
- c) קבצי Gerber
- d) שרטוט פאנל (Panel drawing)

**Answer: a** - קובץ ה-pick-and-place נותן קואורדינטות רכיבים למכונת השיבוץ בהרכבה. Gerber = איפה נחושת/מסכות; NC drill = קואורדינטות חורים; panel = סידור לוחות על הפאנל.

### Q29. איזו מהשכבות הבאות מכילה את רכיבי ה-silkscreen בשרטוט הלוח?
*Which of these layers contains silkscreen elements in a PCB layout?*

- a) שכבת Overlay
- b) שכבת אותות (Signal layer)
- c) שכבת משטח (Plane layer)
- d) שכבה מכנית (Mechanical layer)

**Answer: a** - ב-Altium שכבת ה-silkscreen נקראת Overlay. שם מודפסים ה-designators והסימונים. Signal/Plane הן שכבות נחושת, Mechanical משמשת למידות ומבנה.

### Q30. מהי סיבה אחת להחלת סגנון thermal relief על via המתחבר לפוליגון או למשטח גדול?
*What is one reason a thermal relief style would be applied to a via connecting to a large polygon or plane?*

- a) למנוע מהחום לחמוק בזמן ההלחמה
- b) לפזר חום אל המשטח בזמן הפעולה
- c) להגדיל את כושר נשיאת הזרם של ה-via
- d) להקטין את כושר נשיאת הזרם של ה-via

**Answer: a** - thermal relief מחבר את ה-pad ל-plane בעזרת ״חישורים״ צרים, כדי שהחום לא יתפזר מהר מדי ל-plane בזמן ההלחמה — כך אפשר להלחים כראוי. חיבור נחושת מלא ל-plane היה מבריח את החום ומקשה על ההלחמה.

## Unit 4 - Routing and signal integrity

### Q31. אילו מהמבנים הבאים משמשים להבטיח ש-vias יהיו אמינים יותר בהרכבה ובפעולה?
*Which of these structures is used to ensure vias are more reliable during assembly and in operation?* (multiple)

- a) Teardrops
- b) פדים רחבים יותר
- c) קדח בקוטר גדול יותר עם פדים דקים יותר
- d) מוליכים צרים יותר

**Answer: a, b** - Teardrops (הרחבה מעוגלת במעבר trace→pad) ו-pads רחבים יותר (annular ring גדול) — שניהם מגבירים אמינות מול drill wander (סטיית קדח): טבעת/פד רחב מקטין סיכון שהקדח יחרוג מהפד. קדח גדול עם פד דק דווקא מקטין את הטבעת ופוגע באמינות.

### Q32. מהי סיבה אחת לאכיפת מרווח גדול יותר בין מוליכים שכנים?
*What is one reason to enforce larger spacing between neighboring traces?*

- a) לסייע בהקטנת crosstalk
- b) להקטין קרינה מהמוליך
- c) להגדיל את מהירות האות בשני המוליכים
- d) זה מאפשר להשתמש במוליכים דקים יותר

**Answer: a** - מרווח גדול יותר בין traces מקטין צימוד (crosstalk) בין aggressor ל-victim. כלל 3W: מרווח = פי 3 מרוחב ה-trace, למניעת crosstalk.

### Q33. איזה מסוגי ה-vias הבאים אינו ממולא ומכוסה ב-solder mask?
*Which of these types of vias is un-filled and covered with solder mask?*

- a) Tented vias
- b) Via-in-pad
- c) Via-in-pad plated over (VIPPO)
- d) Plugged vias

**Answer: a** - Tented via מכוסה ב-solder mask ואינו ממולא (״אוהל״ מעל הקדח). Via-in-pad ממוקם בתוך פד, VIPPO ממולא ומצופה נחושת, Plugged ממולא באפוקסי לא מוליך.

### Q34. איזה מהגורמים הבאים קובע אם אות דיגיטלי נחשב "high speed"?
*Which of these factors determines whether a digital signal is considered "high speed"?*

- a) זמן עלייה (Rise time)
- b) מחזור השעון (Clock period)
- c) מהירות ההתפשטות שלו
- d) המרחק ממישור האדמה הקרוב

**Answer: a** - מה שהופך אות ל-high-speed הוא זמן העלייה (rise time), לא תדר השעון — שעון איטי יכול לשאת מעברים מהירים. rise time נמדד 10%→90%; מ-~10ns ומטה מתחילות בעיות signal integrity.

### Q35. איזה מהבאסים הדיגיטליים הבאים משתמש בנגדי pull-up כדי לקבוע את זמן העלייה של הרכיב?
*Which of these digital buses uses pull-up resistors to set the rise time of the device?*

- a) I2C
- b) SPI
- c) UART
- d) כל אלה

**Answer: a** - I2C משתמש ב-pull-up resistors: הקווים (SCL/SDA) הם open-drain, וה-pull-up יחד עם הקיבול הכולל קובע את זמן העלייה. SPI הוא push-pull CMOS ולא צריך pull-ups.

### Q36. איזה מנהגי הניתוב הבאים עלול לגרום לקרינת EMI במידה הרבה ביותר?
*Which of these routing practices is most likely to cause radiated EMI?*

- a) ניתוב מעל מישור אדמה מפוצל (split ground plane)
- b) ניתוב מעל מישור אדמה אחיד
- c) הצבת vias מוארקים בעת החלפת שכבת ייחוס
- d) שימוש ב-tented vias לניתוב

**Answer: a** - ניתוב מעל פיצול (split) ב-ground plane יוצר אי-רציפות בנתיב החזרה → לולאת זרם גדולה → קרינת EMI והפרשי פוטנציאל. מעל plane רציף נתיב החזרה קצר ושקט. כלל זהב: לנתב אותות מהירים תמיד מעל ground plane רציף.

### Q37. איזו סיומת משמשת בשם ה-net של הצד החיובי בזוג דיפרנציאלי?
*What suffix is used on the net name for the positive side of a differential pair?*

- a) _P
- b) _N
- c) _+
- d) _-

**Answer: a** - בזוג דיפרנציאלי הצד החיובי מקבל סיומת _P והשלילי _N. זו המוסכמה שבה כלים מזהים אוטומטית זוגות לניתוב differential.

### Q38. מהי הדרך היעילה ביותר להבטיח שמוליכים ינותבו עם עכבה מסוימת?
*What is the most effective way to ensure traces are routed with specific impedance?*

- a) ליצור design rule המגביל את רוחב המוליך
- b) ליצור design rule המגביל את עובי המוליך
- c) להגדיר ידנית את רוחב המוליך בזמן הניתוב
- d) להסיר מישורי אדמה מתחת למוליכים עם עכבה מבוקרת

**Answer: a** - הדרך היעילה ביותר לעכבה מבוקרת: design rule (מתוך impedance profile) שכופה את רוחב ה-trace על ה-net, במקום הגדרה ידנית לכל trace. העכבה נקבעת ע״י רוחב ה-trace + מרחק ממישור הייחוס (H) + Dk — לכן קובעים stackup לפני רוחב.

### Q39. אילו מהפריטים הבאים הם סיבות להחלת מבני length matching על מוליכים בזוג דיפרנציאלי?
*Which of these items are reasons length matching structures are applied to traces in a differential pair?*

- a) מבטיח ששני האותות יגיעו למקבל באותו זמן
- b) מבטיח ששני האותות יהיו באותה מהירות התפשטות
- c) מבטיח ששני האותות יהיו באותה עכבה
- d) מבטיח ששני האותות יהיו באותו זמן עלייה

**Answer: a** - length matching (meanders) מוסיף אורך ל-trace הקצר כדי ששני האותות יגיעו בו-זמנית לקצה המקבל — כך מבוטל רעש מצב-משותף (common-mode). נדרש גם לבאסים מקבילים כמו DDR.

### Q40. אילו מהשיטות הבאות יכולות לשמש להקטנת inductive crosstalk?
*Which of these methods can be used to reduce inductive crosstalk?*

- a) לנסות להשתמש במוליכים רחבים יותר
- b) לנסות להשתמש בלמינציות דקות יותר
- c) לנתב קבוצות של מוליכים קרוב יותר זו לזו
- d) לתכנן מוליכים בעלי עכבה גבוהה יותר

**Answer: a** - לפי הקוויז, traces רחבים יותר מפחיתים inductive crosstalk (צימוד מגנטי, הדומיננטי בתדרים נמוכים). ניתוב traces קרוב יותר זה בזה דווקא מגביר crosstalk. זו התשובה הרשמית של האתר.
