# AD20 Essentials - Module 23: DRCs on PCBs

> Source: `ad20-essentials-exercises.pdf` (same folder), PDF pages 232-239 (printed page = PDF page; `<!-- p.N -->` marks page starts). Text only: figures are not extracted, only their captions. Altium Designer 20 UI; menu and panel names can differ slightly in newer versions.

<!-- p.232 -->

## 23.1 Purpose

In this exercise, students will run a Design Rule Check. Using the PCB Rules and
Violations panel, students will learn how to properly inspect and resolve violations.

## 23.2 Preparation

1. Close all open projects. For this exercise, we will be using the WCTopping.PrjPcb project
located in the AD20 Essentials Exercises\ Module 23 - DRCs on PCBs folder.
2. Open the WCTopping.PrjPcb project.
3. Navigate to the Projects panel and open WCT.PcbDoc.

## 23.3 Design Rule Check

4. Go to Tools » Design Rule Check to open the Design Rule Checker.
a) Enable Create Report File and Create Violations.
b) Click Run Design Rule Check… button on the bottom left as shown in Figure 297.

*Figure 297. Design Rule Checker*
5. The Design Rule Verification Report should generate, indicating 10 Rule Violations. Scroll
down to the Rule Violations section to see the violated rules as shown in Figure 298.
a) Un-Routed Net Constraint

<!-- p.233 -->
b) Minimum Solder Mask Sliver
c) Silk to Solder Mask
d) Component Clearance Constraint
6. If the Messages panel popped-up, feel free to close it for now.

*Figure 298. Rule violations in the report file*
By default, the Design Rule Verification Report will only show a maximum of 500
violations. This can be changes in the DRC Report Options before running the report.
7. Click on the first violation under the Un-Routed Net Constraint list in the report. It should then
open the PCB document and navigate to the violating area, which is near component IOS2.

<!-- p.234 -->

## 23.4 PCB Rules and Violations Panel

8. Instead of using the report to navigate through the violations, we will use the PCB Rules and
Violations panel while in the PCB. While in the WCTopping.PcbDoc, click the Panels
button on the bottom right, and then select the PCB Rules and Violations panel from the
menu as shown in Figure 299.

*Figure 299. Opening the PCB Rules and Violations panel*
9. This would open the PCB Rules and Violations panel. Dock this panel to the left of the
workspace as shown in Figure 300.

*Figure 300. PCB Rules and Violations panel*

<!-- p.235 -->
10. Click on the Component Clearance Constraint violation, which is the first violation in the
Violations list at the bottom of the PCB Rules and Violations panel. It should then navigate
to the violating area. Instead of just zooming to the violating area, we would also like to
perform a mask of the other objects, to improve clarity.
11. In the PCB Rules and Violations panel, change the highlight options from Normal to Mask
as shown in Figure 301.

*Figure 301. Mask control in the PCB Rules and Violations panel*
12. Left-click on the Component Clearance Constraint violation again from Violations list. The
workspace should zoom to the violating primitives and mask the rest of the board except for
the primitives shown in Figure 302.

*Figure 302. Violating components in the PCB*
13. Enable the Select checkbox from the top of the PCB Rules and Violations panel and repeat
the steps. Notice that the violating primitives will now be selected.
14. To clear all the masks and selection, click the Clear button from the PCB Rules and
Violations panel or hit Shift+C on the keyboard.

<!-- p.236 -->

## 23.5 Resolving Violations

Instead of running all the rules from the Design Rule Check window as described in the previous
section, we can run only selected design rules from the PCB Rules and Violations  panel.
15. Right-click on Un-Routed Net Constraint in the Rule Classes section of the PCB Rules
and Violations as shown in Figure 303, and click Run DRC Rule Class (Un-Routed Net
Constraint) option from the popup menu to run the Design Rule Check.
16. Five violations of this rule type should be highlighted. Find these listed at the bottom of the
PCB Rules and Violations panel in the Violations section as shown in Figure 304.
17. In the Violations pane of the panel, click on the first violation in the list to jump to component
IOS2. One of the pads from IOS2 should be highlighted along with one pad of component
UI1, and the rest of the board is masked similar to Figure 305.

*Figure 303. Rule Classes in the PCB Rules and Violations panel*

*Figure 304. Un-Routed Net violations*

<!-- p.237 -->

*Figure 305. Highlighted violations*
18. Since this is an Un-Routed Net Constraint violation, we will resolve it by routing a trace
from the highlighted pad of UI1 to the highlighted pad of IOS2 with Route » Interactive
Routing.
19. Repeat the previous steps for the other 4 Un-Routed Net Constraint violations in the PCB
Rules and Violations panel. Using Shift+S for Single Layer Mode may help you with
routing.
Although we resolved the first Un-Route Net Constraint violation, it was not removed
from the Violations panel. The Design Rule Check must be ran again for the Violations
to update. You can run the DRC again by going to Tools » Design Rule Check, or
run the DRC for that specific Rule from the PCB Rules and Violations panel.
20. Repour the polygon by going to Tools » Polygon Pours » Repour All. The polygon will
then look similar to Figure 306 .

*Figure 306. Routed nets with the repoured polygons*
21. Go to Tools » Design Rule Check and click Run Design Rule Check.
22. The Design Rule Verification Report should now show five rule violations as shown in
*Figure 307. *

<!-- p.238 -->

*Figure 307. Design Rule report*
23. Open the PCB document and select the [All Rules] in the Rule Class section from the top
of the PCB Rules and Violations panel.
24. Select the Component Clearance Constraint violation from the Violations section at the
bottom of the panel to zoom to the offending primitives, J2 and J3.
25. Select the Component Clearance Constraint class from the Rule Class section to view its
3 rules as shown in Figure 308.

*Figure 308. Component Clearance rule class*
26. Double-click on the rule named “Component Clearance” with the Scope All – All.
27. The Edit PCB Rule – Component Clearance window should open.

<!-- p.239 -->
28. Change the Minimum Horizontal Clearance from 10mil to 5mil as shown in Figure 309.
Click OK.

*Figure 309. Editing the Component Clearance design rule*
29. Run the Design Rule Check again from the Tools menu. The Design Rule Check should
now indicate four violations. Return to the PCB document. Select [All Rules] from the Rule
Class section to view the four violations.
30. Select each of the violation to notice the same pad highlighted. Select the Top Layer tab at
the bottom of the workspace.
31. Click the Clear button from the PCB Rules and Violations panel.
32. Remove the GND tracks from component C8. Move component C8 to the left so that it is no
longer overlapping the violating pad of Reg5. Re-route Pad 2 of component C8 to the
GND via that it was just connected to.
33. Repour all Polygons by going to Tools » Polygon Pours » Repour All.
34. Run the Design Rule Check and ensure there are 0 violations.
35. Save your changes and close the document.
