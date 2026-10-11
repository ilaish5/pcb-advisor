# AD20 Essentials - Module 13: PCB Introduction

> Source: `ad20-essentials-exercises.pdf` (same folder), PDF pages 128-134 (printed page = PDF page; `<!-- p.N -->` marks page starts). Text only: figures are not extracted, only their captions. Altium Designer 20 UI; menu and panel names can differ slightly in newer versions.

<!-- p.128 -->

## 13.1 Purpose

In this exercise, you’ll explore some of the PCB specific preference settings and learn
to customize them. You will also briefly use basic commands, such as navigating to
specific objects and more. We’ll take a more in-depth look at some of these
commands in later exercises.

## 13.2 Preparation

1. Close all open projects.
2. Open the PCB project using File » Open Project and browse to your default installed
example projects folder. Select:
<AD Version>\Examples\Bluetooth Sentinel\Bluetooth_Sentinel.PrjPcb.
Since this project had been opened previously, it can also access using File » Recent
Projects.
The default path to your installed examples is C:\Users\Public\Public
Documents\Altium\<AD Version>\Examples\
3. Navigate to the Projects panel and double-click the icon for the PCB file
Bluetooth_Sentinel.PcbDoc with the left mouse button so that the PCB document is
open.

## 13.3 Moving PCB View

4. When the PCB is first opened, you may be in the 3D environment. To get into the 2D
workspace, where we do the majority of our work, hit the 2 key.
5. Hold the Right-Mouse-Button until the dragging hand cursor appears. Move your mouse
while holding the right mouse button to drag the PCB around. This is how we Pan. Release
the right button to end the drag operation.
6. Scroll the mouse wheel to scroll the PCB vertically.
7. Hold Shift while scrolling the mouse wheel to scroll horizontally.
8. Hold Ctrl while scrolling the mouse wheel to zoom in and out.
9. Press and hold both right and left mouse buttons simultaneously to zoom in and out.
10. Press and hold the mouse wheel down to zoom in and out.

<!-- p.129 -->

## 13.4 View Commands

11. Maintain the focus on the PCB Workspace and observe the behavior of the following
shortcut keys:
a) To View » Fit Board or press the V » F keys in succession.
b) To View » Fit Document or press the V » D keys in succession.
c) To View » Zoom In or press the V » I keys in succession or press Page Up.
d) To View » Zoom Out or press the V » O keys in succession or press Page Down.
e) To View » Area or press the V » A and draw a rectangle with the Mouse.
f) To View » Zoom Point or press the V » P keys in succession, then draw a rectangle with
the mouse somewhere on the PCB. The contents of the rectangle will be focused and
shown with the zoom level adjusted.

## 13.5 General

12. Click    in the upper right corner, to open the Preferences. Open the PCB Editor branch
and look in the General page as shown in Figure 155 below.

*Figure 155. General Preferences for the PCB Editor*

<!-- p.130 -->
13. Verify that Online DRC is enabled. Click OK to close the preferences dialog.
14. Zoom to the left side of the PCB and select on component R13 as shown in Figure 156
below.

*Figure 156. R13 from the Bluetooth_Sentinel.PcbDoc*
Quickly find the component using the command:
Edit » Jump » Component (J»C).
15. Left-click and hold component R13.
a) Drag and drop R13 so it overlaps with component R16.
b) Notice that the overlapping components highlight in green with error markers.
16. Undo the changes by selecting Edit » Undo.
17. Go back to the Preferences: Click  in the upper right corner.
a) In PCB Editor » General, enable the option Display popup selection dialog under the
Editing Options category
b) Press OK to exit Preferences
18. Locate component X2. You can use the J » C shortcut keys. Left-click component X2 and a
selection window may appear as shown in Figure 157. Select X2 from the list.

<!-- p.131 -->

*Figure 157. Selection Window*
19. Press Shift+C to clear the selection.
20. Open the Properties panel using
a) View » Panels » Properties
b) or from the Panels menu accessed from the Panels button in the lower right of the
workspace.
21. Expand the section Selection Filter pane as shown below.
22. Activate the selection filter for Components and deactivate it for all other elements as
shown in Figure 158 below. This will allow us to only select components.

*Figure 158. Selection Filter for Components*
22. Left-click component R13 and select it in the Pop-up Selection dialog.
23. Move the resistor to the left, being sure to select the center of the component body, not the
designator or comment. Notice a violation with the surrounding polygon.

<!-- p.132 -->
24. Repour the Polygon with the command Tools » Polygon Pours » Repour Violating
Polygons or by a right-clicking over the polygon and execute Polygon Actions » Repour
violating polygons….
25. Reopen the Preferences.
a) Under General, enable Repour Polygons After Modification and Repour all
dependent polygons after editing.
b) Click OK to close the preferences.
26. Left-click and move component R15 to the left near R13. Release the component to see the
polygon automatically repour when modified.
27. Undo changes with Edit » Undo.
28. Use Shift+C to clear the selection of R15
29. Open the Properties panel and the Selection filter pane.
30. Click on Custom to allow the selection of all kinds of objects again. It should now say “All-
On”.

## 13.6 DRC Violations Display

31. Jump to component R13 using J»C and drag the component to overlap component R16. It
should now have  violation overlays on the two components. Additional to the  , Altium
shows error markers, e.g. short circuits .
32.  Open the Preferences:
a) Select the DRC Violations Display section.
b) Change the Violation Overlay Style from Style B to Style A and press OK.
c) Notice the violations have now changed to  violation markers shown in Figure 159
below.
d) Repeat steps and try other Violation Overlay Styles.

*Figure 159. Violation Display Markers*

33. For individual DRC violations, the section “Choose DRC Violations Display Style” in the
Preferences allows you to configure the Violation Detail and Violation Overlay information.
a) Access the DRC Violations Display in the preferences and deactivate the details
information for the Short Circuit rule shown in Figure 160 below.
b) Press OK
c) Notice the violations detail for Short Circuit are now removed.

<!-- p.133 -->

*Figure 160. Configuration for the DRC details and violations*
34. Undo the violation by selecting Edit » Undo.
35. Clear the selection using Shift+C.

## 13.7 Interactive Routing

Shelving the Polygons with Tools » Polygon Pours » Shelve… could make it easier
to see the routing on a PCB. But, before sending the PCB out for fabrication, make
sure you Restore Shelved Polygons. This is covered in a later module.
36. Try different Interactive Routing modes:
a) Open the Preferences and select the Interactive Routing page.
i) In the Routing Conflict Resolution options, set Current Mode to Ignore Obstacles.
ii) Press OK.
b) Zoom to Pad U4-28 and activate the route by selecting Route » Interactive Routing.
c) Place crosshair over Pad U4-28 and route from the pad to the net JTDI on the pad
below. Notice that the track can go past the JTDI, creating a violation due to the Ignore
Obstacles option.
d) Right-click twice to exit the routing mode. Undo any tracks that you may have made.
e) Repeat to experiment with other Routing Conflict Resolution modes.
Quickly toggle through the routing modes while actively routing using Shift + R. The
Heads up display and Status bar will show the active routing conflict resolution mode.
37. Place a Route from Pad U4-28:
a) Press Shift+Space to toggle through routing angles. Notice that there are options to route
at Any Angle and Arcs (This is indicated at the bottom of the workspace in the Status
Bar).
b) Right-click twice to exit routing mode.
38. Clear the selection using Shift+C.
39. Open Preferences and go to Interactive Routing.
a) Enable Display Clearance Boundaries and select OK to confirm.

<!-- p.134 -->
b) Route from Pad U4-28 to see an outline around objects on the board as shown in Figure
161 below.
The clearance boundaries will not show if you have Ignore Obstacles as the active
routing conflict mode. Press Tab while routing to access the routing preferences
where you can enable Display Clearance Boundaries.

*Figure 161. Clearance Boundaries*
Reduce this outline by enabling Reduce Clearance Display Area in Preferences

40. Explore Routing Gloss Effort options by routing on the board.
a) Try dragging some of the vias outside U4, e.g. Via close to U4-32 and note the attached
track behavior, avoiding the GND net vias.
b) Open the Preferences, Page Interactive Routing pane Routing Gloss Effort and change
the routing Gloss Effort from Weak to Strong.
If you finished the exercise and are looking for another position to do some test routing
you can activate Mid-Layer 2 and reroute the signal Wake.
41. Close the project without saving.
