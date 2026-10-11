# AD20 Essentials - Module 10: Adding Hierarchy

> Source: `ad20-essentials-exercises.pdf` (same folder), PDF pages 109-117 (printed page = PDF page; `<!-- p.N -->` marks page starts). Text only: figures are not extracted, only their captions. Altium Designer 20 UI; menu and panel names can differ slightly in newer versions.

<!-- p.109 -->

## 10.1 Purpose

In this exercise, the basics of a hierarchical design will be explored. Creating a
Hierarchical design allows you to control connectivity from sheet to sheet in a multi -
sheet design.
The top-level schematic will be completed by populating it with Sheet Symbols corresponding to
each of the lower level schematics and creating lower level schematic sheets from newly created
Sheet Symbols.

## 10.2 Preparation

1. Close the current WCTopping.PrjPcb project.
2. Open the WCTopping.PrjPcb project located in the
AD20 Essentials Exercises\ Module 10 - Adding Hierarchy folder.

## 10.3 Create Top-Level Schematic

3. Right-Click on WCTopping.PrjPcb in Project panel and select Add New to Project »
Schematic.
4. Save the new schematic using File » Save. Name the file Top_Level.SchDoc when
prompted.

## 10.4 Sheet Symbols

Adding sheet symbols on the Top Level Schematic establishes the hierarchical order. The next
steps cover two methods of creating sheet symbols.

### 10.4.1 Creating a Sheet Symbol from Scratch

5. From the Place menu, select Place » Sheet Symbol.
6. With the sheet symbol on your cursor, press Tab to open the Properties panel.
a) Set the Designator property to MID1 as shown in Figure 129.
b) Type the value for the Field File name to Processor_Power as shown in Figure 129.

<!-- p.110 -->

*Figure 129. Sheet Symbol properties dialog*
Processor_Power will be a new schematic that we will use in step 10.6 Creating a
Schematic Sheet from Sheet Symbol. Do not link this value to the
Top_Level.SchDoc. Simply type in Processor_Power in the File Name field.
c) Press Enter or hit the  icon to continue the placement of the sheet symbol.
7. Position the Sheet Symbol with two left-clicks:
a) Click once to define the upper left corner of the sheet symbol.
b) Click a second time to define the lower right corner.
c) Right-click to exit the command.

<!-- p.111 -->

### 10.4.2 Adding Sheet Entries

#### 10.4.2.1 Use the Smart Paste to convert Ports to Sheet Entries

8. Open the Processor_Interface.SchDoc from the Projects Panel.
9. Group select the ports in the Processor_Interface.SchDoc
a) Open the Properties Panel
b) At the pane Selection Filter, deactivate the selection filter for All-On and activate only the
Ports as shown in Figure 130 below.
c) Select the Ports with the command Edit » Select » Inside Area
d) Right-click the selection and select Copy.
In this scenario, we’re configuring the Selection Filter to only select Ports. Don’t forget
to activate the All Objects button after you’re finished your current task to be able to
select any objects moving forward.

*Figure 130. Selection Filter for Ports*
10. Change focus back to the Top_Level.SchDoc by clicking on its document tab.
11. Run Edit » Smart Paste
a) Select Sheet Entries in the pane Choose Paste Action, Paste As list box
as shown in Figure 131.
b) Press the OK button

<!-- p.112 -->

*Figure 131. Smart Paste dialog*
12. Click on the MID1 sheet symbol and place the sheet entries on the right side of the sheet
symbol. You’ll notice the sheet entries will snap to the side of the sheet symbol shown in
Figure 132 below.
13. Position the sheet entries and adjust the size of the sheet symbol similar to Figure 132
below.
a) Setting the grid to 100mil will help with placement, press G to change the grid
b) Change the value of Snap Distance if needed. (Properties panel)

*Figure 132. Sheet Symbol and Sheet Entry placement*

<!-- p.113 -->

### 10.4.3 Creating a Sheet Symbol from Existing Sheet

14. Right-click anywhere on the schematic and select Sheet Actions » Create Sheet Symbol
from Sheet.
15. Select the IO Logic Block.SchDoc from the Choose Document to Place dialog and
select OK as shown in Figure 133 below.

*Figure 133. Choose Document to Place as a Sheet Symbol*
16. With the Sheet Symbol still attached to your cursor, press Tab to bring up its properties
17. Enter MID2 in the Designator properties and press Enter.
18. Place the Sheet Symbol to the right of the MID1 Sheet Symbol and align the Sheet Entries
adjacent to the sheet entries in Sheet Symbol MID1 as shown in Figure 134 below.
Activate the large 90° cursor (Preferences, section Schematic – Graphical Editing).
With an active Large Curser 90, it is easier to position the entries.

*Figure 134. Sheet Symbol Alignment*

<!-- p.114 -->

## 10.5 Connecting the Sheet Symbols

Now that the sheet symbols have been placed, you will wire the connections between the two
sheet symbols

### 10.5.1 Wiring the Sheet Symbols

19. Move the Processor_Power sheet symbol directly in contact with the IO Logic Block
sheet symbol so that the sheet entries line up beside each other. You will notice a small
green checkmark that will appear.
20. Drag the Processor_Power sheet symbol back to its original position. Wires should appear
connecting the two blocks (this is dependent on your preferences; you may need to try again
while holding down the Ctrl key).

### 10.5.2 Wiring the Relay Bus

21. From the Place menu, select Place » Bus.
a) Start the Bus at the RELAY[1..2] sheet entry in the MID2 sheet symbol and extend
half way to the MID1 sheet symbol.
b) Proceed downwards so that there is a sufficient amount of bus wire available for wires to
extend from the RELAY1 and RELAY2 sheet entries of the MID1 sheet symbol and left-
click.
c) Right-click twice to exit the command.
22. Wire the RELAY1 and RELAY2 sheet entries of the MID1 sheet symbol to the bus using
Place » Wire, as shown in Figure 135 below.

*Figure 135. Wired Sheet Symbols*

### 10.5.3 Labeling the Bus and Bus Slices

23. Label the Bus and Bus Slices using the Place » Net Label command.
a) With the net label attached to your cursor, hover over the RELAY[1..2] sheet entry and
press Insert key. The new net label inherits the RELAY[1..2] name. Alternatively,
press Tab and manually change the value.

<!-- p.115 -->
b) Left-click to place the RELAY[1..2] net label on the Bus.
c) With a net label attached to your cursor, hover your cursor over the RELAY1 Sheet Entry
in the MID1 Sheet Symbol.
d) Press Insert so that the net label picks up the RELAY1 Sheet Entry name.
e) Left-click to place the net label on the extended wire from the RELAY1 sheet entry.
(After placing the net label, the net label on the cursor automatically increments to
RELAY2).
f) Left-click to place the RELAY2 net label on the wire extending from the RELAY2 Sheet
Entry. Use Figure 136 as a reference.
g) Right-click to exit the command.

*Figure 136. Net Labeled Bus and Bus Slices*

## 10.6 Creating a Schematic Sheet from Sheet Symbol

The MID1 Processor_Power Sheet Symbol is not referencing an existing schematic sheet. In this
exercise, you will create the Processor_Power Schematic Sheet from the existing Sheet
Symbol.

### 10.6.1 Create Sheet from Sheet Symbol

24. Right-click on the MID1 Processor_Power sheet symbol in the Top_Level.SchDoc and
execute the Sheet Symbol Actions » Create Sheet From Sheet Symbol command.

### 10.6.2 Completing the Newly Created Schematic Sheet

25. In the newly created Processor_Power.SchDoc you will see ports that reflect the sheet
entries of the created MID1 sheet symbol in the Top_Level schematic.
a) Hit Shift+C to clear all selections from multiple documents in the project. Group-select
the ports by dragging a selection box around them.

<!-- p.116 -->
b) Once selected, move them off to the left of the schematic sheet. The ports will still be
selected after the move.
26. With the ports selected, open the Properties Panel.
a) Change the width to 700mil
b) Press Enter to accept the new value
c) Click on the schematic to clear the selection or use Shift + C.
27. Still in the Processor_Power.schdoc create a new sheet symbol from a schematic by
selecting the menu command, Design » Create Sheet Symbol From Sheet.
a) Select the Processor_Interface.SchDoc from the list in the Choose Document to
Place dialog.
b) Click OK and place the sheet symbol into the center of the schematic sheet.
28. Create a second sheet symbol.
a) Right-click an empty space in the schematic and select Sheet Actions » Create Sheet
Symbol From Sheet.
b) Select the Power Supply.SchDoc from the list in the Choose Document to Place
dialog.
c) Click OK and place the sheet symbol into the lower right of the schematic sheet.
29. Arrange and position the sheet entries of the Processor_Interface.SchDoc sheet
symbol as shown in Figure 137 below. (You may need to toggle your grid settings using the
G key for easy positioning)

*Figure 137. Sheet Entry position*
30. Place wire connections from the sheet entries of the Processor_Interface.SchDoc
sheet symbol to the corresponding ports as shown in Figure 138.
a) Move the port so that it makes direct contact with the corresponding sheet entry.
b) Drag the port away from the sheet to the desired location. Dragging to create wires can
be done simultaneously with multiple ports. First, move all of the ports to be in direct
contact with the sheet entries. Then group select the ports and drag.

<!-- p.117 -->

*Figure 138. Sheet Symbol wired to Ports*
31. Right-click on the project in the Projects panel and select Validate PCB Project
WCTopping.PrjPcb. If you have Dynamic Compiling enabled, manually compiling is not
necessary. Dynamic Compiling is covered in Module 9: Compiling in Altium Designer.
32. After compiling the project, the resulting hierarchical structure is visible in the Projects panel
as shown in Figure 139 below.

*Figure 139. Hierarchical Design Project Structure*
33. Disregard any Warnings or Errors and select File » Save All.
