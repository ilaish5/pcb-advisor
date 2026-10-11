# AD20 Essentials - Module 27: PCB Library

> Source: `ad20-essentials-exercises.pdf` (same folder), PDF pages 266-276 (printed page = PDF page; `<!-- p.N -->` marks page starts). Text only: figures are not extracted, only their captions. Altium Designer 20 UI; menu and panel names can differ slightly in newer versions.

<!-- p.266 -->

## 27.1 Purpose

In this exercise, students will learn the steps necessary to create a PCB footprint by
creating a HC49SMD package for the crystal symbol created earlier.

## 27.2 Creating a PCB Library

1. Create a new PCB Library by going to File » New » Library » PCB Library
as shown in Figure 346.

*Figure 346. A new PCB Library*
2. Go to File » Save As and save the library as My_Footprints.PcbLib in the
My_Components folder created in the previous exercise.
3. By default, every new PCB footprint library will contain a default footprint with the name
PCBCOMPONENT_1 as shown in Figure 347. If you do not see the PCB Library panel, go to
View » Panels » PCB Library.

<!-- p.267 -->

*Figure 347. PCB Library panel with default component PCBCOMPONENT_1*
4. Double-click on PCBCOMPONENT_1 and in the pop-up window rename the component to
HC49SMD, set the Height field to 4.5mm and add the Description HC49SMD-RoHS
Compliant as shown in Figure 348. Use the CTRL+Q shortcut keys to toggle between mil
and mm units if needed. Click OK when finished.

*Figure 348. Configuration for the new Footprint*

## 27.3 Footprint Creation

A preview of the footprint we will be creating in this exercise is shown below in Figure 349.

*Figure 349. Crystal footprint that will be created in this exercise*

<!-- p.268 -->

### 27.3.1 Setting the Grid

5. The footprint uses metric dimensions so hit the Q key to toggle the workspace units to mm if
needed. Hit the G key to display the list of preset grid settings and choose a value of 0.5mm
as shown in Figure 350.

*Figure 350. Preset grid*
6. The grid value and the selected unit should now be visible in the lower left corner  as shown
in Figure 351.

*Figure 351. Grid setting in the bottom left corner of editor indicates 0.5mm*
To change the current grid markers and color press CTRL+G to open the Grid Editor.
Select the marker style Lines, Dots, or Do Not Draw and the color you prefer.

<!-- p.269 -->

### 27.3.2 Adding Pads

7. To place a pad, go to Place » Pad, or use the P » P shortcut keys.
8. Hit the Tab key to open its Properties panel before placing it.
9. Change its Designator to 1 and ensure Top Layer is selected in the Layer option.
10. In the Pad Stack region, change Shape to Rectangular the pad dimensions to X: 5.5mm Y:
2mm. You may need to scroll down the Properties panel to enter the pad dimensions, as
shown in Figure 352.

*Figure 352. Pad Properties dialog with parameters for Pad 1*
11. Hit Enter or click the pause symbol  to continue placement.
12. Left-click to place Pad 1 on the origin.
A second pad of the same shape and with Designator 2 is now attached to your cursor .
13. If it is not currently visible, turn on the Heads Up Display (HUD) by hitting Shift + H.
14. Slowly move the position of Pad 2 until the HUD displays an incremental dx value of 9.5mm
and a dy value of 0mm as shown in Figure 353. Left-click to place Pad 2 at that position.

<!-- p.270 -->

*Figure 353. Heads Up Display showing incremental cursor position*
15. Right-click or hit the ESC key to terminate the command. The placed pads and their
properties should then be listed in the PCB Library panel, as shown in Figure 354.

*Figure 354. PCB Library panel showing two pads added for component HC49SMD*

### 27.3.3 Setting Component Origin

There are three options to set an origin for a component: Pin 1, Center or Location as shown in
*Figure 355. *

*Figure 355. Setting Component Origin from the Edit menu*
16. Assign the origin to the center of the existing pads by going to Edit » Set Reference »
Center. The resulting circle and diagonal lines indicating the component origin is shown in
*Figure 356. *

*Figure 356. Component Origin set to Center*

<!-- p.271 -->

### 27.3.4 Adding Top Overlay Outline

17. Switch to the silkscreen layer by clicking on the Top Overlay tab at the bottom of the
workspace.
18. Go to the Place » Line command and hit the Tab key to set the line width to 0.2mm in the
Properties panel. Press Enter or click the pause symbol  to continue the line placement
19. Now that we have a component origin, we can use the HUD to position the component
outline precisely. Move the cursor to the component origin at the center of the component
and note that the HUD reports an x and y value of 0.
The command Edit » Jump » New Location (J-L) with x:0 and y:0 or …Jump »
Reference (Ctrl+END) could help to find the correct position.
20. Using the HUD to guide you, move the cursor to location x: -6.000 y: 2.000 and click to
set the starting point for the line.
21. Move the cursor up and to the right to see the corner angle mode of the line. Press Shift +
Spacebar to change the shape of the corner and Spacebar to change the orientation until
the HUD displays Line 90 StartPlace Line as shown in Figure 357.

*Figure 357. HUD displaying current line mode of 90 degrees*
21. Move the cursor to the following positions and left click to set the vertices at each location:
a) (-6.0, 3.5)
b) ( 6.0, 3.5)
c) ( 6.0, 2.0)
22. Right-click to terminate the line and right click again to terminate the command. The line
should now appear as in Figure 358.

*Figure 358. The top portion of the Overlay added to the component*
23. We will Copy and Paste to add the lower silkscreen shape. In the PCB editor, Altium
Designer requires a reference point for the copied object so that it can assign a local origin.
a) Drag a selection rectangle around the yellow lines
b) Press Ctrl + C to copy it to the clipboard.
c) The cursor becomes a crosshair and a message is displayed at the bottom of the screen:
Select a reference point as shown in Figure 359.
d) Click on the Origin to set it as a reference point.

<!-- p.272 -->

*Figure 359. Copy the upper outline and set a reference point in preparation for pasting*
e) Hit Ctrl + V to paste a copy of the outline. Notice that the cursor is attached outside of the
horizontal line – the reference point you just selected.
f) Hit the Spacebar twice to rotate the objects, left-click to position the cursor on the origin
so that the line is now symmetrically below the pads as shown in Figure 360. Left-click to
place the lines.

*Figure 360. Copied outline*

### 27.3.5 Add Pin 1 Marker

24. For soldering and debugging purposes, Pad 1 should also be visually marked. Use the
command Place » Full Circle to add a circle near Pad 1. Click at (-7.0, 2.0) then move one
grid unit to the right and click again to set the radius. Right-click to end the command once
the circle is placed.
25. Double-click on the circle to open the Properties panel. Set the Radius to 0.12mm and hit
Enter. The component should now look like shown in Figure 361.

*Figure 361. Footprint HC49SMD*
26. Go to File » Save to save the library.

<!-- p.273 -->

### 27.3.6 3D Crystal Body

29. Go to Place » 3D Body from the menu as shown in Figure 362.

*Figure 362. Extruded 3D Body*
30. Hit the Tab key to open the Properties panel. Make the following changes as shown in
*Figure 363. *
a) Set 3D Model Type to Extruded.
b) In the Identifier field, enter: HC49SMD
c) Choose a color for the extruded shape and change the opacity in the Display settings.
d) Set Overall Height = 6mm, Standoff Height = 1mm.
e) Press Enter or the Pause icon  to start drawing the body.

<!-- p.274 -->

*Figure 363. 3D Body Dialog for Crystal*
31. Draw a rectangle to match the silkscreen outline in the editor.
a) Similar to the placement of a polygon, click on each of the corner vertices.
b) Right-click or hit the ESC key twice to finish the drawing of the body.
32. The 2D footprint should now look like Figure 364 in 2D, with the purple hatched lines
indicating the 3D body.

<!-- p.275 -->

*Figure 364. 2D Crystal Footprint*
33. Hit the 3 key to view the body in 3D mode as shown in Figure 365. Hit the 2 key to go back
into 2D mode.

*Figure 365. 3D Crystal Body and Footprint*
34. Go to File » Save to save the library.

## 27.4 Use the Footprint

### 27.4.1 Installing the Footprint Library

35. To install your new PCB Library, open the Components panel by selecting Components
from the Panels button in the bottom right corner of Altium Designer, or from View » Panels
» Components.
36. Click the Hamburger button  and choose File-based Libraries Preferences….
37. Choose the Installed tab.
38. Click the Install button.
39. Navigate to the My_Components folder that you created and select the
My_Footprints.PcbLib library.
40. Click the Open button. Your footprint library will now appear in the window as shown in
*Figure 366. *

<!-- p.276 -->

*Figure 366. Available File-based Libraries dialog with My_Footprints.PcbLib added*
41. Close the Available File-based Libraries dialog.

### 27.4.2 Adding Crystal Footprint to PCB Document

42. In the Components panel, click on the Hamburger icon  and enable the Footprints
checkbox as shown in Figure 367. left.
43. Select My_Footprints.PcbLib from the drop-down list as shown in as shown in Figure
367 right.

*Figure 367. Enabling Footprints in the Components panel*
44. Create a new PCB document by going to File » New » PCB.
45. From the Components panel, right-click on HC49SMD and place the footprint into the PCB.
46. Hit the 3 key to view the component in 3D and ensure that the 3D body is visible.
47. Close the PCB document without saving it.
