# AD20 Essentials - Module 20: PCB Placement

> Source: `ad20-essentials-exercises.pdf` (same folder), PDF pages 198-207 (printed page = PDF page; `<!-- p.N -->` marks page starts). Text only: figures are not extracted, only their captions. Altium Designer 20 UI; menu and panel names can differ slightly in newer versions.

<!-- p.198 -->

## 20.1 Purpose

This exercise will allow you to practice different techniques for component placement.
Component placement directly determines the degree of difficulty for routing and the
performance of the final product.

## 20.2 Preparation

1. Close all open projects. For this exercise, we will be using the WCTopping.PrjPcb project
located in the Module 20 - PCB Placement folder.
2. Open WCTopping.PrjPcb from the Module 20 - PCB Placement folder.

## 20.3 Shortcuts

Rotate Counter Clockwise (shortcut SPACE)
Flip Layer (shortcut L)
Change Pushing Mode (shortcut R)
Net Line Connect Mode (shortcut N)
Reposition selected Components (shortcut T » O » C)
Arrange within rectangle (shortcut T » O » l)
Edit » Move » Move (shortcut M » M)
Edit » Move » Component (shortcut M » C)

<!-- p.199 -->

## 20.4 Placement of Components Within Rooms

3. Open the PCB file WCTopping.PcbDoc.
Notice all components are within the rooms placed outside of the board towards the right.
4. Test out the component behavior when a Room is moved using Figure 248 below as a
reference.
a) Drag one of the Rooms, such as Relay_IO. Notice the behavior of all components being
moved simultaneously when the room is moved.
b) Repeat for other rooms that have not yet been moved and notice the behavior.

*Figure 248. Moving Rooms and Footprints*
5. Set the Pre-selection filter from the Active Bar to only activate Rooms as shown in Figure
249.
6. Then, draw a selection rectangle around all the rooms. Hit the Delete key to delete all of
them, leaving the components remaining on the PCB document.

<!-- p.200 -->

*Figure 249. Set Pre-Selection filter to Rooms only*

### 20.4.1 Placing within an Area

7. Enable All-On in the Pre-selection filter on the Active Bar shown in Figure 250.

*Figure 250. Enable All Objects in the Selection Filter*
8. Select all the components in the design by drawing a rectangle around them.
9. Use the command Tools » Component Placement » Arrange within Rectangle .
a) Define a rectangle of the entire board outline by:
i) First click in the upper left corner of the board.
ii) Next, click towards the bottom right corner.
iii) Right Click to exit command.
b) Compare your result with Figure 251 below. This illustrates how you can get any selected
group of components within a specific area of your board to begin placement. It is not
necessary for the drawn box to be large enough for components, a small box would do.

<!-- p.201 -->

*Figure 251. Component Placement within the board area*
10. We’ll now position all the components outside of the board.
a) With all the components still selected, click Tools » Component Placement » Arrange
Outside Board.
b) Shift+C to clear component selection. See Figure 252 to see the end result.

*Figure 252. Components Arranged Outside of the board*

<!-- p.202 -->

### 20.4.2 Placing Individual Components

11. Click on the 40-pin header, component J4, and drag it to the position shown in Figure 253.

*Figure 253. Manually place J4 within the board area*
12. Continue placing components using the drag method.
a) Use the Move command using the Edit » Move » Move (M, M hotkeys) and left-click on
component UI1 and move to its new position as shown in Figure 254.
b) During component movement, release your left mouse. The component remains on the
cursor.
c) Left-click to position the component – no hold and drag required.

<!-- p.203 -->

*Figure 254. Placing other components with Edit » Move » Move*
While moving a component, press Spacebar to rotate the component counter-
clockwise and press Shift + Spacebar to rotate the component clockwise.
13. Position components RLY1, RLY2, RLY3 and RLY4 so that the result looks similar to
*Figure 254. *
Connection lines will appear when dragging a component to show the same net
connections between the footprints. While dragging a component, press N to toggle
the visible component net connections ON/OFF. To hide all connection lines, use
View » Connections » Hide All.

### 20.4.3 Cross Select Mode

Tools » Cross Select Mode used in conjunction with the PCB Editor’s Tools »
Component Placement » Reposition Selected Components command is a very
effective way to place components by selecting them from the schematic.
14. Open  Preferences, in the upper right corner of Altium Designer.
15. Navigate to the section System - Navigation and verify that the Cross Selection checkbox
is enabled under Cross Select Mode.
16. Enable Cross Select Mode from Tools » Cross Select Mode. If the icon of this menu item
already has a blue outline around it, then Cross Select Mode is already enabled as shown
in Figure 255.

*Figure 255. Blue highlighted icon indicating Cross Select mode is enabled*

<!-- p.204 -->
17. In Processor_Interface.SchDoc, select capacitors C5 and C6 sequentially.
a) Hold down Shift while left-clicking on the component bodies as shown in Figure 256
below.
b) The order you select them is important as this will determine the placement order in the
PCB.
Be sure to click on the body of the capacitor rather than just the designator or
comment. The component will not be selected in the PCB if the body of the symbol is
not selected.
Change the Grid (G key) if it is difficult to select the body from the capacitor.

*Figure 256. Selecting Capacitor symbol bodies*
18. Bring into focus the WCTopping.PcbDoc. In the PCB Editor, make sure the corresponding
footprints are currently selected. Access the command Tools » Component Placement »
Reposition Selected Components. Component C5 should automatically jump to your
cursor for placement.
19. Click to place C5 in the bottom left corner as shown in Figure 257, using the Spacebar to
rotate.
20. Component C6 should now automatically jump to your cursor. Place it in accordance with
*Figure 257. *

*Figure 257. Positioning components C5 and C6 loosely*

<!-- p.205 -->
21. Now we will position the leftmost capacitor exactly in the position we want.
a) Double click the capacitor, C5, to open its Properties panel dialog.
b) Change the (x, y) position to (200mil, 100mil) as shown in Figure 258.
c) Press Enter to accept the change.

*Figure 258. Placing C5 at a specific location on the board*
22. We will now position the component C6 using the Move command.
a) Invoke the Object Move command by pressing M » M hotkeys.
b) Click on C6
c) With the component now attached to the cursor, use the Jump » New Location
command.
i) Press the J » L hotkeys and enter (X, Y) values of (500mil, 300mil) as shown in
Figure 259 below.
ii) Select the OK button with the TAB key, press Enter to accept the jump values and
press Enter again WITHOUT MOVING THE MOUSE to fix the position. Right click
to exit the Move command

*Figure 259. Jump to Location dialog*
23. Place UI1 outside of the board.
24. Align the Relay Components:
a) Select components RLY1, RLY2, RLY3, and RLY4.
b) Use the command Edit » Align » Distribute Horizontally. The components should be
placed approximately as shown in Figure 260.

<!-- p.206 -->

*Figure 260. Components distributed evenly horizontally*
25. With the components still selected, use Edit » Align » Align Vertical Centers then choose
the component at either end as the primitive reference. Be sure to click between the pads.
See Figure 261. Right-click to exit the ‘Align’ command.

*Figure 261. Components aligned with vertical centers*
Alignment and move commands can be performed on component properties, such as
Designators. Hold Ctrl while selecting to select.

### 20.4.4 Position Remaining Components

26. To place the remaining unplaced components (Please bear in mind that the PCB does not
have to be completely placed, due to time restrictions):
a) Use click and move method:
i) Click in the center of a component and hold down the left mouse button.
ii) The component will now move with your cursor.
iii) Release the mouse button at the desired location.
b) Placement from the PCB panel:
i) Open the PCB panel.

<!-- p.207 -->
ii) Set the Drop-down at the top to Components.
iii) For drag and drop, in the select boxes at the top of the panel, uncheck Select and
check Clear Existing.  Feel free to Uncheck Zoom if this makes your flow easier.
iv) Click on the Component Class <Outside Board Components>.
v) All outside board components will be listed in the Components pane.
vi) In the Components section:
Click a component and drag it directly to the right and the component will pop onto
your cursor for placement.
vii) Release the mouse at the desired location.
c) Multiple Placement from the PCB panel:
i) Try selecting multiple components in the pane using Ctrl + Click.
ii) Drag one of the selected components to the right will begin a reposition selected
components for the components that had been selected.
iii) Place the components in the PCB as they pop onto your cursor.
27. For the remainder of the components, in the PCB panel, enable the Select checkbox at the
top. The <Outside Board Components> class should still be selected, so just click the
Apply button. This will select the remaining components outside the board area.
28. Use Tools » Component Placement » Reposition Selected Components to sequentially
load up the cursor with the unplaced parts. Place 5 or 6 footprints for practice. Right click to
escape the Move command.
29. Refer to Figure 262 as a sample of a finished PCB component layout for the training.
30. Once complete, save and close all documents.

*Figure 262. End result of the PCB layout*
