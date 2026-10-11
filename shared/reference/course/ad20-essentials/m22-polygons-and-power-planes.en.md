# AD20 Essentials - Module 22: Polygon Pours

> Source: `ad20-essentials-exercises.pdf` (same folder), PDF pages 218-231 (printed page = PDF page; `<!-- p.N -->` marks page starts). Text only: figures are not extracted, only their captions. Altium Designer 20 UI; menu and panel names can differ slightly in newer versions.

<!-- p.218 -->

## 22.1 Purpose

In this exercise, students will learn to place and edit polygons pours and power
planes.

## 22.2 Preparation

1. Close all open projects. For this exercise, we will be using the WCTopping.PrjPcb project
located in the Module 22 - Polygons and Power Planes folder.
2. Open the WCTopping.PrjPcb project.
3. From the Projects panel double click on the file WCTopping.PcbDoc to open the PCB
document.
4. Open  Preferences and navigate to PCB Editor - General. Enable Repour Polygons
After Modification under Polygon Rebuild. This removes the need to manually repour the
polygons after every change. Click OK to close the Preferences dialog.

## 22.3 Placing a Polygon Pour

5. We will be placing a polygon on the bottom layer. Click on the Bottom Layer tab at the
bottom of the PCB editor workspace to make it the active layer.
6. View the entire board area using the V - D hot keys.
7. Set the origin in the lower left corner of the PCB using the commands Edit » Origin » Set .
Your cursor turns to a cross-hair. Zoom in to the lower left corner of the PCB and click to
place the origin.
8. Set the grid spacing to 10mil by pressing G and select 10mil. Ensure to be on imperial
units, as indicated on the status bar – else, hit the Q key to toggle units from metric.
9. If it is not visible, enable the Heads Up Display (HUD) by pressing Shift + H as shown in
Figure 276 below. You can change HUD window opacity and options in  Preferences,
PCB Editor branch, Board Insight Modes page.

*Figure 276. Heads Up Display toggled with the Shift+H keys*
10. Access the command Place » Polygon Pour (hot keys P - G).
11. Press Tab to pause the command and open the Properties panel to access the Polygon
Pour dialog as shown in Figure 277.
12. Be sure to assign it to the 5V net and ensure the option is selected in the pull-down for
Pour Over All Same Net Objects.

<!-- p.219 -->

*Figure 277. Polygon Pour dialog*
13. Click on the pause symbol  to continue placing the polygon. Your cursor will turn into a
cross-hair indicating that you may begin drawing the polygon. Click on the board origin in
the bottom left corner and the HUD should indicate co-ordinates (0,0) as shown in Figure
278.

*Figure 278. Heads-Up Display (HUD) showing (0,0) coordinates*
14. Hit Shift + Spacebar until the HUD indicates Line 90/90 Horizontal Start to provide a right
angle for the polygon. Explore changing the corner mode by pressing Shift + Spacebar
until the HUD indicates Line 90/90 Vertical Start with Arc (radius: 100mil). While in this
mode, use the comma ‘,’ and period ‘.’ keys to increase/decrease the radius value.

15. If necessary, hit Spacebar to change from vertical to horizontal if necessary.
16. Complete the rectangular polygon as shown in Figure 279.

<!-- p.220 -->

*Figure 279. Polygon Pour added to the PCB*

## 22.4 Polygon Properties

17. Double-click on the newly created polygon on the Bottom Layer to open its Properties
panel.
18. Ensure that the post-selection filter in the Properties panel is reset to have all objects
selected, as shown in Figure 280.

*Figure 280. All Objects selected in the selection filter*
19. Change the Fill Mode to Hatched as shown in Figure 281. After changing it to Hatched, the
polygon should then repoured by clicking the “Repour” action at the top of the Properties
panel.
If your Preferences are set to Repour Polygons After Modification, the Repour
dialog shown below in the Properties panel will not be present, since the polygon will
repour automatically.

<!-- p.221 -->

*Figure 281. Changing the Polygon fill mode*
20. From the Place menu, select Polygon Pour Cutout.
21. Using Figure 282 as a reference, draw a rectangular Polygon Pour Cutout on the existing
Bottom Layer polygon we just created.
22. Once defined, right click to terminate the polygon outline and right-click once more to exit
polygon pour cutout placement mode.
23. You should now see that once the polygon repours, there is a cutout and absence of copper
within the cutout region similar to Figure 282. If your polygon does not repour automatically,
make sure you go to Tools » Polygon Pours » Repour All.

<!-- p.222 -->

*Figure 282. Polygon Pour Cutout*

## 22.5 Polygon Pour Manager

24. Click on the Top Layer tab at the bottom of the PCB editor to set it as the active layer.
Notice the multiple polygon pours on this layer and the specific clearances as shown in
*Figure 283. With multiple polygons overlapping, pour order or priority must be defined.*

*Figure 283. Polygon Pours on Top Layer*
25. Open the polygon pour manager by going to Tools » Polygon Pours » Polygon Manager .
26. Within the Pour Order pane, we can change the pour order of the polygons. Select
12V_Top polygon and click Move Down until it is moved all the way down to the bottom of
the Pour Order list seen in Figure 284. Click OK.
The polygon that is higher in the pour order will pour first, and the polygons lower in
the list will then pour around existing polygons with necessary clearance.

<!-- p.223 -->

*Figure 284. Polygon Pour Manager*
27. In the PCB, notice that the 12V_Top polygon is no longer visible when repoured since the
GND_Top polygon which floods the entire board is higher in the pour order. This is a
deliberate error and we should revert it back to the original order.
28. Open the Polygon Pour Manager again by going to Tools » Polygon Pours » Polygon
Manager and set the 12V_Top polygon back to the top of the pour order. Click OK to return
to the PCB and ensure to see the 12V_Top polygon poured on the board.

<!-- p.224 -->

## 22.6 Flooding a Layer

29. We will now create a polygon which floods an entire layer of the board. Go back to Tools »
Polygon Pours » Polygon Manager.
30. Click on New Polygon from… then Board Outline as seen in Figure 285. A new Polygon
will be added in the Polygon Pour Manager.

*Figure 285. Creating a polygon from the board outline in the Polygon Manager*
31. Match the settings of the newly created Polygon to what is shown in Figure 286. The shape
of this polygon will be dependent on the first, Bottom Layer polygon that we created in a
previous step. Your polygon may vary from what is shown below.

<!-- p.225 -->

*Figure 286. Polygon Pour dialog*
32. Ensure that this newly created polygon is last in the pour order and click OK to close the
Polygon Manager.
33. If you received green highlights showing a Violation, rebuild the polygon by going to Tools
» Polygon Pours » Repour All

<!-- p.226 -->

## 22.7 Editing Polygons

### 22.7.1 Editing an Edge

34. In the PCB editor, click on Bottom Layer from the layers tab to make it the active layer.
35. Navigate to the bottom of the board where you manually created the polygon earlier in this
exercise.
36. Left-click on the polygon to select it. If the first click selects the Polygon for the entire board,
click again.
37. Hover over the right vertical edge of the polygon (not at a vertex). The edge will be
highlighted by a thick white line and the cursor will turn into a 2-way arrow as shown in
*Figure 287. *

*Figure 287. Hovering over the right edge of the polygon*
38. Now click and hold the left mouse button; the cursor will become a crosshair and the HUD
will show that the Sliding Edge mode is active as shown in Figure 288.

*Figure 288. Moving the right edge of a polygon using the Sliding Edge mode*
39. Slowly move the cursor to the left and the polygon edge slides to the left, becoming
narrower. Release the mouse button. Notice that you are constrained to only the x -direction
ensuring that the height of the polygon is unchanged.

<!-- p.227 -->

### 22.7.2 Adding a Vertex

You can add a center vertex at any point on the edge of the polygon. Center vertices are also
automatically added or removed as changes are made.
40. Select the same polygon as in Section 22.7.1 that we just modified. Hold Ctrl, position the
cursor at the desired location for the center vertex.
41. Left-click and move the mouse button while holding Ctrl. The new vertex will appear in the
desired location as a white square as shown in Figure 289.

*Figure 289. Adding a vertex to a polygon*

### 22.7.3 Deleting a Vertex

42. Select the same polygon as in Section 22.7.1. Click and hold a corner vertex then press
Delete. The cursor will turn into a crosshair, and the vertex will be removed reshaping the
polygon as shown in Figure 290.

*Figure 290. Deleting a vertex*

<!-- p.228 -->

## 22.8 Controlling the Connection Style - Polygon

43. As of right now, all polygons are connected with a relief connect style as shown between
the pads of the headers on the top left of the board, and the GND polygon shown in Figure
291.

*Figure 291. Relief connect style*
44. We would like to change the connections from relief connect to direct connect. In the PCB,
go to Design » Rules.
45. Click on Polygon Connect Style under Plane and select Polygon Connect to open the rule.
46. Set the Connection Style to Direct Connect as shown in Figure 292. Click OK to return to
the board.

*Figure 292. Polygon Connect Style rule*
47. Go to Tools » Polygon Pours » Repour All. Note that the pads are now direct connected
to the pour as shown in Figure 293.

<!-- p.229 -->

*Figure 293. Repoured polygon*
The design rule can be configured as both a simple and advanced mode. In Advanced
mode, you can set the connection styles for through hole, surface mount and via
connection.
48. To avoid design rule violations or automatic repour of polygons when routing on top of
existing polygons, polygons should be shelved. Polygons can be shelved through a couple
of different ways, e.g., by right-clicking on a polygon » Polygon Actions » Shelve All, or
Tools » Polygon Pours » Shelve Polygons or in Polygon Manager window.
49. Go to Tools » Polygon Pours » Shelve 6 Polygon(s). Note the number will vary
depending on the number of polygons on the board. Observe that all the polygons have
disappeared.
50. Restore using Tools » Polygon Pours » Restore 6 Shelved Polygon(s).

<!-- p.230 -->

## 22.9 Power Planes

51. Select GND from the layers tab, which is an internal plane. Hit Shift+S to go into Single
Layer Mode.
52. Double-click in the board area to open the Split Plane dialog appears as shown in Figure
294. Assign the net GND to the Power Plane.

*Figure 294. Changing the Power Plane net to GND*
53. Now, click on 5V from the layers tab and repeat the previous step to assign net 5V to the
plane as shown in Figure 295.

*Figure 295. Changing the Power Plane net to 5V*

<!-- p.231 -->

### 22.9.1 Controlling the Connection Style – Power Plane

54. Like for the polygons, we can also control the connection style of pads/vias for a Plane. Go
to Design » Rules, navigate to Plane and open the page Power Plane Connect Style. Open
the default PlaneConnect rule. Ensure the fields in this dialog are set as the following:
- Constraint: Simple
- Connect Style: Relief Connect
- Conductors: 4
- Conductor Width: 10 mil
- Air-Gap: 10 mil
- Expansion: 10 mil
55. Click OK to close the window.
56. Note that the pads connected to 5V on the top left of the board should be connected with a
relief connect to the power plane as shown in Figure 296.

*Figure 296. Relief Connect style for the 5V plane*
If any additional rules are added for this category, ensure that the new rule has a
higher priority than the ALL scoped rule. Otherwise, the new rule will be ignored. Once
the ALL scoping query is encountered, it overrides lower priority rules for that
category.

57. Save and close all files.
