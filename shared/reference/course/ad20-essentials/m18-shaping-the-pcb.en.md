# AD20 Essentials - Module 18: Shaping the PCB

> Source: `ad20-essentials-exercises.pdf` (same folder), PDF pages 174-185 (printed page = PDF page; `<!-- p.N -->` marks page starts). Text only: figures are not extracted, only their captions. Altium Designer 20 UI; menu and panel names can differ slightly in newer versions.

<!-- p.174 -->

## 18.1 Purpose

In this exercise, you will learn how to define a board shape using several methods.
The board shape or board outline is usually closed a polygon used to define the PCB boundaries.
The board shape does not exist on a particular layer but rather defines the space where components
and traces can be placed. In Altium Designer, the black area is the board shape and can be created
and modified in several ways. This exercise will explore three of these methods.

## 18.2 Preparation

1. Close all open projects. For this exercise, we will be using the WCTopping.PrjPcb project
located in the Module 18 - Shaping the PCB folder.
2. Open the WCTopping.PrjPcb project file located in the
Module 18 - Shaping the PCB folder.

## 18.3 Board Planning Mode

3. Navigate to the Projects panel and double-click the icon for the PCB file
WCTopping.PcbDoc with the left mouse so that the PCB document is open.
4. Set the origin to 2050mil x 2150mil by selecting the menu Edit » Origin » Set. Rather
than clicking the location we want, press the J » L keys to open the Jump Location
command.
5. Enter in the X and Y coordinates as shown in Figure 218 below.

*Figure 218. Jump to Location*
6. Press Enter twice to set the origin at that location. A circle and X will appear at the new
origin location as shown in Figure 219.
7. Change the grid setting to 500mils by pressing Ctrl + G and entering 500mil in the Step X
field, and change the Display setting for Fine to Lines instead of Dots. Click OK.

<!-- p.175 -->

*Figure 219. Defined origin on the grid*
8. Change to the board planning mode with the command: View » Board Planning Mode (the
shortcut to get to this mode is the 1 key).
9. Click on the menu Design » Redefine Board Shape, and then draw a closed rectangle
starting at the origin (0,0). Use the X, Y position to guide you to draw a rectangle 3500mils
wide by 2000mils tall. The Heads-Up Display or Status Bar will tell you the coordinates of
where you’re about to place the vertex. Be sure to left-click on every rectangle vertex and
ending at the origin followed by a right click to end the command. The board should look
like Figure 220.

If the corner mode is not 90° rectangle change it to 90° rectangle. You can change the
corner mode by pressing Shift +Spacebar.
Examine the Status Bar in the bottom center of the window to see the current mode as
you toggle through the five corner style choices.

<!-- p.176 -->

*Figure 220. Board Planning Mode*

Use the Jump » Location command to go to the X, Y locations quickly.

10. Select from the menu Design » Edit Board Shape then select and hold the right vertical
sliding edge.
11. Drag the vertex to expand the rectangle to be 5000mils wide.
12. Repeat with the top horizontal line to expand the rectangle to be 2500mils tall.
13. Left click anywhere in an open space to exit the command, and your board should look like
*Figure 221. *

*Figure 221. Board Outline defined in Board Planning mode*

<!-- p.177 -->
14. From the menu, select Design » Modify Board Shape to get a crosshair.
15. Left-click at the coordinates below to modify the board shape. Use the Heads-Up Display or
Status Bar to see the coordinates, or use the J » L shortcut keys.
a) (5000, 1500)
b) (2500, 1500)
c) (2500, 1000)
d) (5000, 1000)

*Figure 222. Board Outline modified in Board Planning Mode*
16. Your board should now look like Figure 222.
17. Change back to View » 2D Layout Mode (or press the 2 key).
18. Change the Step X grid back to 5mils in the Grid Editor using the keys Ctrl + G.

<!-- p.178 -->

## 18.4 Define Board Shape from Selected Objects

### 18.4.1 Circle

19. Open the View Configurations panel by selecting the View » Panels » View Configuration
or press the L hotkey.
20. Right-click layer Mechanical 1 and Edit Layer as shown in Figure 223. Change the
name to Board Outline and hit Enter to close the dialog.

*Figure 223. Renaming Mechanical Layer*
21. Select Board Outline as the active layer in the Layer Bar at the bottom of the PCB
environment.
22. Select Place » Arc » Full Circle
a) Left-click anywhere near the middle of the existing PCB shape.
b) Move the mouse either towards you or away from you to create enlarge the circle.
c) Left-clicking again will set the size of the circle. To increase or decrease the size of the
circle, select it and modify Radius in the Properties panel, if needed. A Radius of 1300mil
should be fine.
d) Press the right-mouse button to terminate the command. Your PCB should now be similar
to Figure 224.

<!-- p.179 -->

*Figure 224. Placing a circle in the PCB workspace*
23. The circle should be highlighted in white indicating it is selected (if it is not, press Ctrl + A to
select it).
24. To create a circular board shape, go to the menu Design » Board Shape » Define from
Selected Objects. The black area, which is the board outline, should now be limited to the
circle as shown in Figure 225.

<!-- p.180 -->

*Figure 225. Defining the Board Shape from Selected Primitives*
The display may be masked as a result of this action. Click the Clear button or in the
bottom right corner of the editor or press [Shift] + C to return to normal view.

### 18.4.2 Rectangle

25. To simplify the drawing process, we will set a coarse grid. Press Ctrl + G to open the Grid
Editor and change the Step value to 500mil. Click OK to close the Grid Editor.
26. Click menu choices Place » Line and draw a closed rectangle of any shape inside of the
existing circular PCB. Ensure that the rectangle is closed by looking for a white circle at the
cursor when you are completing the polygon as shown in Figure 226.

If you’re having issues placing the lines for the rectangle, this may be because you’re
in Look Ahead Mode. Hit the 1 key to disable this mode, which may help with line
placement.

<!-- p.181 -->

*Figure 226. Drawing a rectangle with lines to define our Board Shape*
26. After you complete the rectangle, right-click to terminate the command.
Try changing the corner style by pressing [Shift]+[Spacebar] while drawing the
rectangle. Examine the Status Bar in the bottom center of the window to see the
current mode as you toggle through the five corner style choices.
27. Right-click a second time to terminate the place line command.
28. Select the lines of the newly defined rectangle by Shift selecting all 4 lines, or using a
selection rectangle.
29. Now we’ll create a board shape to match your rectangle by selecting the menu Design »
Board Shape » Define from selected objects. Your PCB should now be rectangular and
similar to Figure 227.

*Figure 227. Example Board Shape defined from the rectangle*
30. Since we changed our board shape, we can delete the outer circle by selecting it, and hit
Delete. Feel free to view your PCB in 3D, by hitting the 3 key as shown in Figure 228.

<!-- p.182 -->

*Figure 228. Example of a rectangular board shape in 3D*
31. Return to 2D using the 2 key.
32. Remove the outline for the board by pressing Ctrl + A to select the outline, then press the
Delete key to remove the outline.

<!-- p.183 -->

## 18.5 Defining Board Shape from DXF/DWG

33. Select File » Import » DXF/DWG and browse to the project folder Essentials
Exercises\Shaping the PCB for outline.dxf located in the exercise folder.
34. The Import from AutoCAD dialog box will open.
Change the dialog box settings as shown in Figure 229.
a) Scale: mm
b) Layer mapping 0: Not Imported.
c) Layer mapping 1: board_shape -  Board Outline layer.
d) Layer Mapping 2: Title Block - Not Imported.

*Figure 229. Import DXF dialog*
To ensure the proper scale selection, check the Size = which will update based on the
selected scale units and should match the dimensions you are expecting.
35. Click OK.

<!-- p.184 -->
36. After clicking on OK, the board shape will be imported similar to Figure 230.

*Figure 230. Imported DXF outline*
37. Select all the line segments in the imported outline by pressing Ctrl + A.
38. Select Design » Board Shape » Define from Selected Objects to create the new board
shape as shown in Figure 231.

<!-- p.185 -->

*Figure 231. Final Board Shape created from a DXF outline*
39. Save your changes and close the document.
