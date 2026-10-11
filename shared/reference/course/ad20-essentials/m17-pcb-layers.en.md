# AD20 Essentials - Module 17: PCB Layers

> Source: `ad20-essentials-exercises.pdf` (same folder), PDF pages 168-173 (printed page = PDF page; `<!-- p.N -->` marks page starts). Text only: figures are not extracted, only their captions. Altium Designer 20 UI; menu and panel names can differ slightly in newer versions.

<!-- p.168 -->

## 17.1 Purpose

In this exercise, we will examine the layers associated with your design and learn how
to add plane layers to simplify power and ground connections used later.

## 17.2 Preparation

1. Close all open projects. For this exercise, we will be using the WCTopping.PrjPcb project
located in the AD20 Essentials Exercises\Module 17 - PCB Layers folder.
2.  Open the WCTopping.PrjPcb project file from the Module 17 - PCB Layers folder.

## 17.3 Adding a new PCB

3. Add a new PCB Document to the project by opening the Projects panel and right-clicking on
the project name. From the right-click menu, select Add New to Project » PCB as seen in
Figure 208 below.

*Figure 208. Add new PCB to the Project*
4. Go to File » Save All and save the PCB document as WCTopping.PcbDoc.

<!-- p.169 -->

## 17.4 Layer Stack Manager

### 17.4.1 Modify Default Layer Stack

5. With the WCTopping.PcbDoc as the active document, from the menu select Design »
Layer Stack Manager or using the shortcut keys D » K. A new document will appear as
shown in Figure 209 below. The Properties panel will also appear. Dock it along the left or
right side of the workspace.

*Figure 209. Layer Stack Manager*
6. Select the layer Top Layer.
7. Right Click on Top Layer, select Insert layer below » Plane as shown in Figure 210 below.

*Figure 210. Adding Layers*

<!-- p.170 -->
8. As a default configuration, two Plane layers are added to create a symmetric stack as shown
in Figure 211 below. Stack Symmetry can be enabled or disabled from the Properties panel.

*Figure 211. New Plane layers added*
9. Click on the new Layer 1 label created in the layer stack and rename it GND.

Edit text by selecting the cell then click the cell again with Left Mouse Button,
or just press F2

10. Repeat the previous step to name the second Plane layer as 3V3. The layer stack should
look like Figure 212 below.

*Figure 212. Layer Stack with renamed Plane Layers*
11. Select one of the Plane layers that was just created, right-click and select Delete Layer to
remove the Plane Layer. Repeat the step to remove the Dielectric 2/3.
12. Right click on Top Layer, select Insert layer below » Signal. As the default configuration,
two signal layers are added, to create a symmetric stack.
13. Open the Properties panel. The Properties panel shows the layer information, e.g. the
option for a symmetric stack.
14. Select the Layer 1 and then Dielectric 1, observe the change in the Properties panel

<!-- p.171 -->
15. Select the Material cell from Dielectric 1 . Click on  to open the Select
Material dialog. Select a new core material, e.g. Core-29 as shown in Figure 213 below.
16. Click OK.

*Figure 213. PCB Material database*
17. Select Signal Layer 2 and move the layer by right clicking the layer and selecting the Move
Layer Up and Move Layer Down to observe the changes.
18. At the bottom of the Layer Stack Manager select the tab Via Types.
By default, a through-hole Via from the Top Layer to Bottom Layer is available, as shown in
Figure 214 below. Additional Vias like Blind or Buried vias, or uVias for HDI Designs can be
added as well.

*Figure 214. Layer Stack Manager with default via pairs*
19. Close the Layer Stack Manager and save the changes.

<!-- p.172 -->

## 17.5 Layer Stack Table

20. With the PCB Workspace in focus, press the L hotkey or select View » Panels » View
Configuration to see all the layers for our design.
a) Locate the Mechanical 1 layer name in the list. If needed expand the section of the
Mechanical Layers (M).
b) Right-click and select Edit Layer and rename the layer to Layer Stack. You may also
assign a Layer Type as shown in Figure 215 below. Click OK to close the dialog.

*Figure 215. Renaming mechanical layers*
21. With the PCB in focus, select from the menu Place » Layer Stack Table to add a table of
the layer stack in the workspace.
22. Press Tab before placing the Layer Stack table.
23. Modify the following parameters as shown in Figure 216.
a) Change Layer to Layer Stack
b) Uncheck the Show Board Map
c) Set Line Width to 8mil
d) Set Text Height to 30mil
e) Set Stroke Width to 5mil

*Figure 216. Layer Stack Table*

<!-- p.173 -->
24. Press the Pause button in the middle of the workspace and position the compact table
below the board outline as shown in Figure 217 below. Right Click to exit Layer Stack
Table placement.

*Figure 217. Place Layer Stack Table*
25. Save and Close the Project and its documents.
