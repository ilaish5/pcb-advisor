# AD20 Essentials - Module 26: Schematic Library

> Source: `ad20-essentials-exercises.pdf` (same folder), PDF pages 257-265 (printed page = PDF page; `<!-- p.N -->` marks page starts). Text only: figures are not extracted, only their captions. Altium Designer 20 UI; menu and panel names can differ slightly in newer versions.

<!-- p.257 -->

## 26.1 Purpose

In this exercise, students will learn the steps necessary to create a schematic symbol
by creating a custom crystal symbol. Start this exercise will all files and projects
closed.

## 26.2 Create a Crystal Symbol

### 26.2.1 Creating a Schematic Library

1. In your training folder, or wherever you have stored your training files, create a new folder
called My_Components.
2. In Altium Designer, go to File » New » Library » Schematic Library to create a new
schematic library, as shown in Figure 332.

*Figure 332. A new schematic library*

3. Go to File » Save As and save the library as My_Symbols.SchLib in the newly created
My_Components folder.

### 26.2.2 Symbol Properties

4. We are now ready to start creating the symbol. The completed crystal symbol that we wi ll be
building in this exercise will be similar to what is shown in Figure 333.

<!-- p.258 -->

*Figure 333. Completed crystal symbol for this exercise*
5. By default, every new schematic library will contain a default symbol with the name
Component_1 as shown in Figure 334. If you do not see the SCH Library panel, go to View
» Panels » SCH Library.

*Figure 334. Default Component Name in SCH Library panel*
6. Double-click on Component_1 in the SCH Library panel to open its Properties panel as
shown in Figure 335.
7. Locate the Design Item ID of the component and enter Crystal as the new name.
8. Enter X? in the Designator field. The ? syntax will allow us to annotate the components in
our design later on.
9. In the Description field, enter 50MHz 20pF 20ppm.

<!-- p.259 -->

*Figure 335. Changing the symbol Properties*
10. Save the symbol library with the command File » Save. If you would like to view the Library
Options, go to Tools » Document Options and view the options in the Properties panel.

### 26.2.3 Defining the Pins

A proper Snap Grid will simplify symbol creation. The ideal setting for this exercise is a grid of
50mil.
11. Go to Tools » Document Options.... to open the Properties panel. Change the Snap Grid to
50mil as shown in Figure 336, if it is currently 10mil or 100mil. As an alternative, you can
click anywhere in the schematic editor, and hit the G key to toggle between the preset grids.

<!-- p.260 -->

*Figure 336. Snap Grid set to 50mil*
12. Go to Place » Pin (or use the P»P shortcut keys) and hit Tab to open its Properties panel.
Configure the settings to match those in the highlighted box of Figure 337. Hit the Enter key
or the Pause icon  after you’ve updated all fields to continue pin placement.

*Figure 337. Properties of Pin 1 in the Properties panel*

<!-- p.261 -->
13. Notice that one end of the pin has a small “X” at one end as shown in Figure 338. This X
cross-hair defines its electrical connection or hotspot. Use the X key to flip the pin
horizontally while the pin is floating to flip its orientation. You can also use the Spacebar to
help with the orientation if needed.

*Figure 338. Pin with electrical hotspot on the left*
14. Using Figure 339 as reference, place pin 1 to the left of the origin.
15. After placing Pin 1, another pin will appear on the cursor with the pin name and designator
already incremented to 2. Ensure that the X cross-hair of this pin is on the right and the pin
is positioned to the right of the origin as shown in Figure 339.
16. Right-click or hit ESC to exit pin placement mode.

*Figure 339. Position pin 2 to the right of pin 1 separated by a pin length (hotspot for image enlarged)*
Each Pin has a single electrical hotspot on one end for a valid wire connection. When
a placed pin is moved the cursor automatically jumps to the hotspot. Click and hold on
each pin to confirm that the hotspot is positioned on the outer end of each pin, ready
for wiring.

### 26.2.4 Adding Symbol Body

17. To place the two vertical lines on the end of each pin, use the command Place » Line.
18. Press the Tab key during placement to open the Properties panel and set the Line Width to
Medium and choose a color of your choice. Press Enter or the Pause icon  to continue
the placement.
19. Draw the 2 lines similar to what is shown in Figure 340. Right-click to terminate each line
segment. Right-click a second time when you are finished to terminate the command.

*Figure 340. Adding lines to crystal symbol*
20. Go to  Preferences, Schematic branch, and Defaults page. Select the object Round
Rectangle from the Primitive list and change both the Corner X Radius and Corner Y Radius
to 50mil. Click OK to apply this as default.

<!-- p.262 -->
21. Go to Place » Round Rectangle command to add the central body for the crystal.
22. Hit the Tab key to open its Properties panel. Change the Border to Medium and select your
choice of color as shown in Figure 341.

*Figure 341. Round Rectangle dialog*
23. Draw the rectangle in the center of the symbol as shown in Figure 342 by clicking in the top
left corner, then the bottom right corner. Right-click to terminate the command.

*Figure 342. Adding the central body to the crystal*
24. Save the library by going to File » Save.

<!-- p.263 -->

## 26.3 Using the Symbol

### 26.3.1 Installing the Library

25. To install your new Schematic Library, open the Components panel by selecting
Components from the Panels button in the bottom right corner of Altium Designer, or from
View » Panels » Components.
26. Click the Hamburger Button    and choose “File-based Libraries Preferences…”.
27. The Available File-based Libraries dialog will open.
28. Click on the Installed tab to view currently installed system libraries.
29. Click the Install… button.
a) Navigate to the My_Components folder that you created and select the
My_Symbols.SchLib library.
b) Click the Open button.
If your library file is not visible, be sure that the filter drop-down in the lower right
corner of the file browser window is set to Schematic Libraries(*.SCHLIB).

30. Your Available file-based Libraries panel should now be added to the list
as shown in Figure 343.

*Figure 343. My_Symbols.SchLib added to the Installed Libraries list*
31. Click the Close button in the Available File-based Libraries dialog.
32. Back in the Components panel, select My_Symbols.SchLib from the drop-down list. The
crystal symbol should appear as shown in Figure 344.

<!-- p.264 -->

*Figure 344. Crystal symbol appearing in Components panel*

### 26.3.2 Adding Symbol to Schematic

33. Create a new schematic document by going to File » New » Schematic.
34. Place the crystal symbol in the schematic by right-clicking the component in the Components
panel, and Place Crystal.
35. Left-click to place the component in the schematic. Then, right-click to end the placement
command.

<!-- p.265 -->

## 26.4 Revising the Symbol

### 26.4.1 Making a Change to the Symbol

36. Open the My_Symbols.Schlib. If you have closed the window, use the command File »
Open » Recent Documents » My_Symbols.SchLib.
37. Double click the center body of the crystal and change the Fill color in the Properties panel
for the Round Rectangle to Yellow as shown in Figure 345.
38. Save the library file.

*Figure 345. Updated crystal symbol*

### 26.4.2 Updating the Schematic

39. Return to the schematic document created earlier. The symbol on the schematic is still the
initial version before changing the fill color to yellow. To update this symbol:
a) Go to Tools » Update from Libraries. Ensure to check on Fully Replace symbols on
sheet with those from library and click the Finish button.
b) Click Execute Changes in the ECO dialog, followed by Close. The symbol should then
be updated with the newest version, with a yellow-filled rectangle.
40. Close the schematic document without saving.
