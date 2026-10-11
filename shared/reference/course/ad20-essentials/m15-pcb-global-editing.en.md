# AD20 Essentials - Module 15: PCB Panels and Global Editing

> Source: `ad20-essentials-exercises.pdf` (same folder), PDF pages 147-159 (printed page = PDF page; `<!-- p.N -->` marks page starts). Text only: figures are not extracted, only their captions. Altium Designer 20 UI; menu and panel names can differ slightly in newer versions.

<!-- p.147 -->

## 15.1 Purpose

In this exercise, we’ll explore the common panels used in the PCB environment such
as the Properties Panel, Filter panel, Find Similar Objects and List panel and PCB
panel.
Global Editing allows us to make a change to multiple objects at the same time. Global E diting
tools are available in the schematic, schematic symbol editor, PCB editor, and footprint editors.

## 15.2 Preparation

1. Close any open PCB projects. For this exercise, we will be using the WCTopping.PrjPcb
project located in the
AD20 Essentials Exercises\ Module 15 - PCB Global Editing folder.

## 15.3 Properties Panel

The Properties panel is used to modify properties for multiple objects easily. In this section, we
will use the mouse and Edit » Select commands to select items then use the Properties panel to
make changes in both the Schematic and PCB editors.

### 15.3.1 Modify PCB Traces

2. Open the WCToppingGlobalEditing.PcbDoc document and zoom in on U1 as shown in
Figure 178 below.

*Figure 178. WCToppingGlobalEditing.PcbDoc near component U1*
3. Ensure nothing is selected on the board. Then, open the Properties panel from the Panel
button located in the bottom right corner of the editor. Ensure that the filter is set so that all
the objects are highlighted in blue. Otherwise, click on All-On. The same pre-selection filter
can also be accessed from the Active Bar as shown in Figure 179 below.

<!-- p.148 -->

*Figure 179. Selection filter with the scope set to "All-On"*
4. Select multiple irregular traces quickly by using the Edit » Select » Connected Copper
command, or the hotkeys Ctrl+H then hold Shift while clicking on the four traces, or by
pressing the Tab button with a single trace selected to toggle the selection options, as
shown in Figure 180 below. Right-click or hit Esc to terminate the command.

*Figure 180. Selecting multiple traces with the Shift key and "Connected Copper" command*
5. We now would like to change the widths of the selected tracks to 10mil. The Properties panel
contains parameters and values of the selected objects. However, the visible values are
represented by ‘*’ since there are different values for the selected objects.
a) As of right now, both tracks and pads are currently selected. Let’s change the post -
selection filter to only show properties of tracks by clicking on the down arrow button at
the top-right of the panel (refer to Figure 181).
b) Click on All-Objects, then ensure to only click Track from the post-selection filter (refer to
Figure 181).

<!-- p.149 -->

*Figure 181. Properties panel with the post-selection filter set to Tracks only*
6. In the Properties panel, locate the Width field and change the value from 15mil to 10mil.
Hit Enter. The modified layout is then shown in Figure 182 below.

*Figure 182. Board Layout with modified traces*
In this exercise, we use the Global Editing workflow to modify the trace width. An
excellent alternative is to re-apply the preferred width and clearance rules of an
existing route using the command Route » Retrace Selected.

## 15.4 Filter Panel

The PCB Filter panel is another method to select items based on a query language. In the
examples in this section, we will once again use the Properties panel to make changes after the
appropriate elements have been selected by the PCB Filter panel.

<!-- p.150 -->

### 15.4.1 Object Checkboxes

7. We will first familiarize ourselves with the checkbox options within the PCB Filter panel.
Open the PCB Filter panel accessible via the Panels button in the bottom right corner of the
editor.
8. Enable the Track checkboxes associated with Net and Component objects as well as the
Via checkbox for Net and Component object as shown in Figure 183. Notice that the Filter
field is populated with a query based on the combination of checkboxes you have selected.

*Figure 183. PCB Filter panel selections reflected in the PCB*
9. Make sure that at the bottom of the PCB Filter panel you have Matching set to Select, Non-
matching with Deselect enabled and with the mode set to Mask. Ensure that the filter in the
Properties panel is set to All objects.
10. Click the Apply to All button in the bottom right corner of the panel to see the effect of the
query to the design. You should have tracks highlighted as shown in Figure 183.
11. Disable the Track on Comp checkbox hit Apply to All again. Notice that the component
outlines have now been excluded from the selection on the board.
12. Enable the Top Layer checkbox in the Layer pane then click Apply to All. Only tracks on
the Top Layer will be highlighted.
13. Click the Clear button to reset the selection on the board.

<!-- p.151 -->
14. Try enabling different combinations of the checkboxes then click Apply to All to see which
objects are selected.
15. Right-click anywhere in the top pane of the PCB Filter panel and choose the Uncheck All
checkbox to reset the query back to Not All. Uncheck any selections in the Layer pane
as well.

### 15.4.2 Query Selection

16. In this section, we’ll build a query using the PCB Filter panel to select components having
designators starting with character C, and move them from the top to bottom layer.
17. To simplify the view, we will temporarily hide the tracks and vias. First, we will open the
View Configuration panel by going to View » Panels » View Configuration. Select the
View Options tab and set the Tracks and Vias to hidden as shown in Figure 184 below.

*Figure 184. Hiding Tracks and Vias from the Properties panel*

<!-- p.152 -->
18. Open the PCB Filter panel and ensure that the “Filter” pane is set to (Not All.)
19. Enable the Component “Free” checkbox. IsComponent should appear in the filter pane.
Click Apply to All to select all the components in the PCB.
20. Add the following text to the Filter pane: and (Name like 'C*')as shown in Figure 185
below then apply the changes. This naming syntax is important.
The asterisk is a wildcard identifier. With this filter, any component that has a name
beginning with the letter 'C' will be selected. The selected components should now only be
components with designators starting with letter “C” as shown in Figure 185 below.

*Figure 185. Components with designators starting with the letter "C" selected via the PCB Filter panel*
21. Now modify the query from 'C*' to 'C?'.
22. After you apply the change, only components with a single character following the letter 'C'
will be selected.
23. Now that the nine capacitors are selected, open the Properties panel via the Panels button
in the bottom right corner of the editor. Feel free to close the PCB Filter panel if desired.

<!-- p.153 -->
24. Ensure that the filter option at the top is configured to show Components, as shown in
Figure 186 below or else you will not see any information about the Components in the
Properties panel.

*Figure 186. Filter to only Components*
25. Then, locate the Layer attribute and change the value to Bottom Layer. The selected
capacitors should now be blue indicating they have been flipped to the back side of the
board as shown in Figure 187 below.

*Figure 187. Nine capacitors flipped to the Bottom Layer*
26. While the nine capacitors remain selected, change their layer back to Top Layer in the
Properties panel.

<!-- p.154 -->

## 15.5 Find Similar Objects

The Find Similar Object (FSO) dialog is another powerful way to select multiple items in either
the schematic or PCB environments. It allows you to choose a particular element in the design
and then identify one or more common parameters that will be used as the basis for global
selection.

### 15.5.1 PCB Find Similar Objects Dialog

#### 15.5.1.1 Selecting Vias

27. Let’s first unhide the tracks and vias by going to the View Configuration panel (View »
Panels » View Configuration). Open the View Options tab and activate the Tracks and
Vias. We will now select vias of a specific size on this board and change their sizes.
28. Use Shift+C to verify that there are no objects currently selected or masked.
29. Select the via located near UI1-14 and right-click to Find Similar Objects as shown in
Figure 188 below.

*Figure 188. Right-click and select Find Similar Objects*
30. The FSO dialog will appear, displaying via parameters as shown in Figure 189 below. Note
that by default the Object Kind is set to a scope of Same. Enable Mask in the scope
settings to mask the rest of the board.

<!-- p.155 -->

*Figure 189. FSO for the selected Via*
31. Click the Apply button to select all vias in the design as shown in Figure 190 below.

*Figure 190. All Vias selected using the Find Similar Objects dialog*

#### 15.5.1.2 Changing Via Size

32. Instead of all vias, we only would like to change the via diameter of the 30mil vias. In the
Find Similar Objects dialog, set the column of the Via Diameter parameter as shown in
Figure 191 below.

<!-- p.156 -->
33. Click the Apply button. Now only the vias of 30mil diameter are selected.

*Figure 191. Find Similar Objects dialog to target specific Vias*
34. In the FSO dialog click the OK button to close the dialog.
35. Change to the Properties panel.

<!-- p.157 -->
36. Change the selection filter for the Properties panel to Vias as shown in Figure 192 below.
a) Locate the Via Diameter field and change the value from 30mil to 20mil.
b) Change Hole Size from 16mil to 10mil.
c) Hit Enter and see the changes made on the selected vias.

*Figure 192. Properties panel with the new values for Via Diameter and Hole Size*
37. Hit Shift-C to return to standard board view.

## 15.6 List Panel

The PCB List panel displays items from your design in a tabular format and is used for both
selecting and editing.

### 15.6.1 Selecting Components

38. We will now view attributes of selected components in a tabular form and lock their
positions, using the PCB List panel. Open the PCB List panel through the Panels access
button in the bottom right corner of the editor.
39. Change the list settings at the top of the panel to match those shown in Figure 193. Note
that all objects are included in the PCB List panel.

<!-- p.158 -->

*Figure 193. PCB List panel showing All Objects in the design*
40. Open Power Supply.SchDoc.
41. Ensure Cross Select Mode is turned on, indicated by its blue highlight in Tools » Cross
Select Mode (as shown in Figure 194 below). If it’s not enabled, click the icon to enable it.

*Figure 194. Cross Select mode enabled*
42. Hold the Shift key to select all of the capacitors on Power Supply.SchDoc. Return to
the PCB document and the five components should now be selected in the bottom right
corner of the PCB.
43. In the PCB List panel, click on the “View” name hyperlink, and change it to Edit and change
the “all objects” hyperlink to selected objects. The PCB List panel will now display only
the selected components as shown in Figure 195 below.

*Figure 195. PCB List panel showing 5 components selected in the PCB.*

### 15.6.2 Modifying Properties

Our objective is to lock all of these selected components on the board. We will do this by
changing the Locked column in the PCB List panel.
44. Enable the Locked checkbox for the first component in the PCB List panel.
45. Click on the cell that you just locked and copy it with the Ctrl+C keys.

<!-- p.159 -->
46. Select the locked cells for all the remaining four components by clicking on the first
unchecked one, hold the Shift key then click on the last cell as shown in Figure 196 below.

*Figure 196. Copy & Paste to quickly change multiple rows in the PCB List panel at once*
47. Use the Ctrl+V keys to paste the locked property quickly as shown in Figure 196 above.
The same method can be used to copy and paste multiple parameters in the PCB List
panel at the same time.
48. Try to move any of the five components you just locked to confirm they will not move. Save
and close all files.
Consider the circumstances where these batch replacement methods would help you
with your designs.
