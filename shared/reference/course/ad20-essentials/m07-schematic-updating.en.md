# AD20 Essentials - Module 7: Schematic Updating

> Source: `ad20-essentials-exercises.pdf` (same folder), PDF pages 81-88 (printed page = PDF page; `<!-- p.N -->` marks page starts). Text only: figures are not extracted, only their captions. Altium Designer 20 UI; menu and panel names can differ slightly in newer versions.

<!-- p.81 -->

## 7.1 Purpose

In this exercise, we’ll perform modifications to multiple schematic objects as once,
such as alignment, formatting and net color highlighting. These operations are what
we refer to as Global Editing. We’ll also look at the schematic annotation of
components.
1. Close the current WCTopping.PrjPcb project.
2. Open the WCTopping.PrjPcb project from the
AD20 Essentials Exercises\ Module 7 - Schematic Updating folder.

## 7.2 Align

### 7.2.1 Align Right

Alignment tools are used to ensure that objects are aligned to one another, or to the grid to
achieve a clean document.
3. Open the Processor_Interface.schdoc from the Project Panel.
4. Left-click and drag a rectangular selection from left to right around the ports on the left of the
schematic.
5. Go to Edit » Align » Align Right or use the Active Bar to align the ports.
Use the Edit » Align » Align to Grid to align objects within inherited/imported designs
that were not captured on grid. This is to maintain proper connectivity between
electrical objects.

It is also possible by right mouse click on the Source Documents to Open All
documents or Open All Schematic Documents.

## 7.3 Formatting Net Labels

### 7.3.1 Selecting All Net Labels

In this section, we’ll modify all the Net Labels in the project to ensure they have the same font,
font size, and color.
6. Open the Processor_Interface.SchDoc.
7. Right-click on one of the net labels such as GPIO2. In the right-click menu, click on Find
Similar Objects… (also referred to as “FSO” for short). This will open the Find Similar
Objects window.
8. Set the selection options as defined in Figure 88.

<!-- p.82 -->

*Figure 88. Find Similar Objects configuration for Net Label selection*
9. Click OK. Notice that all the net labels in the schematic are selected.
10. Without clicking anywhere on the schematics, open Digital_IO.SchDoc. Notice that the
Net Labels in this schematic are selected as well. Return to
Processor_Interface.SchDoc.

### 7.3.2 Apply Formatting to Net Labels

11. While the net labels remain selected, open the Properties panel if not already opened.
12. Change the text font to Verdana change the text size to 9.
13. Click on the color box within this panel and click on a dark green color. Then, click on
to italicize the net labels shown in Figure 89 below.

*Figure 89. Net Label formatting defined in the Properties panel*
14. The formatting defined in this panel will be applied on all the Net Labels selected in the
project. Click once in the main workspace and hit Shift+C to clear the highlight and mask.

<!-- p.83 -->

## 7.4 Locking Components Designators

### 7.4.1 Selecting only 100nF 50V Capacitors

In the previous section, we selected all Net Labels by using a single selection filter (Object Kind
is Net Label). In this section, we will use three filters to select components of a specific name.
15. Hit J then C to jump to a component. Type C5 and click OK. Close the Messages panel if it
appears.
16. Right click on C5 and click on Find Similar Objects.
17. In the Find Similar Objects window, set the three filters as shown in Figure 90 below.

*Figure 90. Three filters to ensure we select only the 100nF 50V Capacitors with unlocked designators*
18. Click OK. Notice that only 100nF 50V capacitors with unlocked designators are selected.
19. Without clicking anywhere on this schematic, open the Digital_IO.SchDoc. Similarly,
only the 100nF 50V capacitors are selected and not the other components.
The total number of selected objects and the document count are displayed at the
bottom of the Properties panel. In this case, five components are selected, and their
common attributes are shown and can be modified through this Properties panel.

<!-- p.84 -->

### 7.4.2 Lock the 100nF 50V Capacitors Designators

20. While the capacitors remain selected, open the Properties panel.
21. To lock the component designators, simply click on the padlock icon beside Designator in
the panel, as shown in Figure 91 below.

*Figure 91. Lock the designators of the selected Capacitors*
22. Note that once the component designators are locked, they will not be modified through
either the annotate schematics window or the Properties panel. They must be unlocked first
by clicking on the padlock icon again.
23. Click once in the main workspace and hit Shift+C to clear the highlight and mask.

<!-- p.85 -->

## 7.5 Net Color Highlighting

24. Open the Processor_Interface.SchDoc from the Projects Panel.
25. Select the color Red from View » Set Net Color » Red as shown in Figure 92 below.

*Figure 92. Set Net Colors menu*
26. Click on a wire connected to a 5V Power Port to highlight the entire net in Red as shown
in Figure 93.
27. Then, right-click to exit the command.

<!-- p.86 -->

*Figure 93. Processor_Interface.SchDoc with 5V net highlighted in red*
28. Notice that power ports that are directly connected to a component will not have a Red
highlight because there are no wires to highlight on. For example, the power port connected
to C5.
29. Drag the 5V power port away from C5 to create a wire between them. We will then see that
wire being highlighted in Red, as shown in Figure 94 below.

*Figure 94. Red highlight on wire connected to C5*
30. All the wires connected to 5V in the other schematics such as in Digital_IO.SchDoc
and Power Supply.SchDoc are highlighted in Red as well. They may be hiding by the
yellow rectangles drawn over the circuitry.

<!-- p.87 -->

## 7.6 Schematic Annotation

31. Head to Tools » Annotation » Annotate Schematics… to open the Annotate dialog. The
window shown in Figure 95 below, will appear.

*Figure 95. Annotate Dialog*
a) Set the Order of Processing using the pull-down menu. Set it to Across Then Down.
b) Click Reset All.
c) Click OK on the pop-up dialog that appears.
32. Notice that the capacitors which designators were locked earlier will not be reset, as shown
in the Proposed Change List. Next, while still in the Annotate window, perform the following:
a) Click the Update Changes List button
b) Click OK on the pop-up dialog that appears.
c) A preview of the proposed designator values will be displayed similar to what is shown in
*Figure 96. *

<!-- p.88 -->

*Figure 96. Proposed Designator changes based on the Annotation settings*
d) These changes are only proposed so far. To commit this change to the design, press the
Accept Changes (Create ECO) button, and then Execute Changes within the resulting
Engineering Change Order. All undesignated parts should now have a unique
designator.
e) Press the Close button to close the completed ECO, and then again press the Close
button to close the Annotate dialog.
33. View the schematics to confirm that they now have assigned designators. Right-click on the
project in Projects panel and click on close project. Click on Save All and click on OK.
If there are any “old” designators, they are referenced as a superscript in light gray
next to the newly named designators. Compiling will remove the superscript of the
“old” designators.
