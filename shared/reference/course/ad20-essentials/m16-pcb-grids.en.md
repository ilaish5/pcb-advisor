# AD20 Essentials - Module 16: PCB Grids

> Source: `ad20-essentials-exercises.pdf` (same folder), PDF pages 160-167 (printed page = PDF page; `<!-- p.N -->` marks page starts). Text only: figures are not extracted, only their captions. Altium Designer 20 UI; menu and panel names can differ slightly in newer versions.

<!-- p.160 -->

## 16.1 Purpose

In this exercise, the configuration and the functionality for the Cartesian and Polar Grid
will be reviewed. Both grids can be used as a local grid within the PCB editor for a
specific document.
Designers need to precisely place and align components during PCB design and routing which is
extremely difficult without the help of grids systems. Altium Designer supports multiple user -defined
grids in both Cartesian and Polar forms, making component placement predictable and easy.

## 16.2 Preparation

1. Close all open projects. For this exercise, we will be using the WCTopping.PrjPcb project
located in the AD20 Essentials Exercises\ Module 16 - PCB Grids folder.
2. Open WCTopping.PrjPcb project file from the Module 16 - PCB Grids folder.
3. Open WCTopping_Grid.PcbDoc.

## 16.3 Predefined Default Grids

4. Press key G to open a list of predefined grid values.
5. Select one of the predefined grid values. The visible grid will change in the PCB, and the
selected value will show in the Status Bar and the Heads-Up Information as shown in Figure
197 below.

*Figure 197. Grid selection dialog*

<!-- p.161 -->

## 16.4 Grid Manager

You can make your grid choice and tailor the settings to suit both your personal placement
preferences and the immediate design requirements.

### 16.4.1 Global Board Snap Grid

6. Go to Design » Import Changes from WCTopping.PrjPcb and Execute Changes.
If some of the footprints fail to transfer to the PCB, refer to Module 11:Transfer to PCB
to help you resolve those issues. If the footprints transferred successfully, you can
continue with the next step.
7. Open the Properties panel by clicking View » Panels » Properties. The grid configuration
can be seen inside the Properties panel, as shown in Figure 198 below. Close the other
panes from the Properties panel or scroll down to the grid pane if needed to see the relevant
information.
You can change your units from mm to mil using the Q hotkey, or CTRL+Q if you’re in
an action or panel.

*Figure 198. Properties panel with the Grid Manager*

<!-- p.162 -->
8. Double-click on the Global Board Snap Grid line in the Grid Manager pane to access
parameters for the default grid as shown in Figure 199 below.

*Figure 199. Default Grid Settings*
You can access the Cartesian Grid Editor using the Ctrl+G hotkeys.

9. Change the Step X size to 10mil, the Multiplier to 10x Grid Step and the drawing
configuration from Dots to Lines.
The Multiplier determines how many Fine units will be contained in a Coarse grid unit.
One Fine unit is the value of the Step entered in the Cartesian Grid Editor dialog.
10. Click OK to accept changes.
11. Examine the new grid to see the changes as shown in Figure 200 below. Notice that there
are 10 fine grids to each coarse grid and the smallest division is 10mil.

*Figure 200. Modified default grid setting*

<!-- p.163 -->

### 16.4.2 Custom Cartesian Grid

12. Open the Properties panel.
13. Click the Add button in the Grid Manager dialog and select Add Cartesian Grid.
14. A grid named New Cartesian Grid will be added to the list in the Grid Manager, as
shown in Figure 201 below.

*Figure 201. New grid added in the Grid Manager*

<!-- p.164 -->
15. Double click any field in the New Cartesian Grid entry to open the Grid Editor dialog as
shown in Figure 202 below:

*Figure 202. Cartesian Grid Editor*
16. Edit the values for Step, Extents, Quadrants and Display to match those shown in Figure 202
above. The Fine color is set to 127 while Coarse color is set to 123.
a) Name: User Grid1
b) Rotation: 0
c) Steps:20mil
d) Width: 1000mil.
e) Origin X: 1500mil.
f) Origin Y: 1500mil.
g) Quadrants:1,2 and 4.
17. Click OK to return to the PCB editor and note the presence of the new grid. Zoom
accordingly to see the fine grid detail as shown in Figure 203 below.

*Figure 203. New Cartesian grid show in Quadrants 1,2 and 4 in the PCB*
18. Find component DI1 and drag it into the PCB space, to the right side of the new Cartesian
grid. You will notice that the grid is no longer visible. It will reappear when the component is
not selected.

<!-- p.165 -->
19. Open the Properties panel and enable the Comp checkbox for the UserGrid1 Cartesian
grid as highlighted in Figure 204. This will allow us to place components on that grid.

*Figure 204. Enabling the Comp checkbox to be able to place components on the new grid*
20. Move component DI1 to see that the grid now remains visible.

<!-- p.166 -->

### 16.4.3 Custom Polar Grid

21. Open the Properties panel again.
22. Click Add in the Grid Manager pane and select Add Polar Grid.
23. Enable the Comp checkbox to make the polar grid active for component operations.
24. Double-click the New Polar Grid row to open the Polar Grid Editor. Set the values as shown
in Figure 205 below. The Fine and Coarse line colors are assigned to values 106 and 232
respectively.
a) Name: User Grid2
b) Angular Step: 5
c) Radial Step: 50mil
d) Start Angle: 0°
e) End Angle: 180°
f) Origin X: 1500mil.
g) Origin Y: 1500mil.
h) Radial Range  min 0mil.
i) Radial Range Max: 1200mil
25. Click OK.

*Figure 205. Polar Grid editor*
26. Note the new Polar Grid in the PCB editor was generated over the Cartesian Grid we just
generated.

<!-- p.167 -->
27. The Grid Manager allows changing the priority for the overlapping grids if needed as shown
in Figure 206 below.

*Figure 206. Priority for the Grids*
28. Drag component DI1 and DI2 to the newly added polar grid. Test the rotations of the
components by pressing Spacebar and Shift + Spacebar while moving the component to
notice its alignment to the grid as shown in Figure 207 below.
For better visual experience, hide the rat’s nests by going to
View » Connections » Hide All.

*Figure 207. Aligning components to a Polar Grid*
29. Save and close the project documents.
