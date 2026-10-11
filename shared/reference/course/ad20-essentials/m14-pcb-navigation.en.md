# AD20 Essentials - Module 14: PCB Viewing and Navigation

> Source: `ad20-essentials-exercises.pdf` (same folder), PDF pages 135-146 (printed page = PDF page; `<!-- p.N -->` marks page starts). Text only: figures are not extracted, only their captions. Altium Designer 20 UI; menu and panel names can differ slightly in newer versions.

<!-- p.135 -->

## 14.1 Purpose

In this exercise, users will gain a better understanding of the PCB Editor interface and
learn about basic navigation and viewing tools.
This exercise is for users to become familiar with the PCB workspace. Do not save  the project
or design documents.
In this example, we use special objects called Device Sheets. The logical designators
from the schematic do not match the designator information we see on the PCB. This
is based on the specific Device Sheets function we use in this example. To see the
physical designator on the schematic, you can change the view by selecting the
second (compiled) tab at the lower left side of the schematic page. For further
information about Device Sheets and logical/physical designators have a look at the
documentation.

## 14.2 Preparation

1. If not already open use File » Open Project and browse to your installed Example projects
folder. Select:  Examples\Bluetooth Sentinel\Bluetooth_Sentinel.PrjPcb.
Since this project had been opened previously, it can also access using File » Recent
Projects.
The default path to your installed examples is C:\Users\Public\Public
Documents\Altium\<AD Version>\Examples\
2. Navigate to the Projects panel and double-click the icon for the PCB file
Bluetooth_Sentinel.PcbDoc with the left mouse button so that the PCB document is
open.

## 14.3 Jump Command

The Edit » Jump command is commonly used so the status of this sub-menu has been elevated to a
popup menu with its hotkey J.
3. Hit the 2 key to ensure you’re in 2D mode.
4. To jump to the current origin: press the J - O keys in succession.
5. To jump to a specific location: press the J - L keys in succession, then enter the X, Y
coordinates within the Jump to Location dialog as shown in Figure 162 below.

<!-- p.136 -->

*Figure 162. Jump to Location dialog*
6. To Jump » Component... press the J » C keys in succession. Enter U1 into the resulting
Component Designator dialog as shown in Figure 163 below.

*Figure 163. Jump to Component dialog*
7. Press OK and the cursor will jump to the component U1, a zoom and pan will occur only if
necessary to reach the location of the component, in the event it is currently outside the
visible area.

## 14.4 Cross Probe Mode

8. Keep the PCB Document Bluetooth_Sentinel.PrjPcb open.
9. Navigate back to the Projects panel and open the 3-Axis_Accelerometer.SchDoc.
10. Select from the menu Tools » Cross Probe; the mouse cursor should now be a crosshair.
11. Select component U1. The PCB should briefly pop up before returning to the schematic.
12. Press ESC to stop the cross probe mode.
13. Switch to the PCB Workspace to see footprint LGA16-3X3X1_L now masked.
14. If you are wondering why U1 is selected in the schematic – and cross-probe is selecting U3
in the PCB, select the ‘Compiled Sheets’ tab of the schematic and you’ll see it’s U3 (device
sheet says U1), as shown in Figure 164.

<!-- p.137 -->

*Figure 164. Logical and Physical View for a Schematic document*
15. Press Shift+C to clear the mask.
For more information on Device Sheets and how they work, please refer to our online
documentation. This exercise is only used to demonstration navigation techniques in
the PCB.

## 14.5 Cross Select Mode

Tools » Cross Select Mode allows a PCB component to be selected directly from its
schematic symbol counterpart. Used in conjunction with the PCB's Tools »
Component Placement » Reposition Selected Components command, it enables a
very powerful and effective way to go about component placement.
16. Verify that cross-select mode is enabled within the preferences.
a) Open the  Preferences, in the upper right corner of Altium Designer, and head to the
System branch, and the Navigation page.
b) Verify the Cross Selection checkbox is enabled. The Cross Selection Mode section also
controls the selection scope.
c) Click OK to close the preferences dialog.
17. To toggle the Cross Selection Mode from the menu use Tools » Cross Select Mode. If the
icon has a blue outline around it, then Cross Select Mode in enabled as shown in Figure
165 below.

*Figure 165. Cross Select mode enabled*
18. Navigate to the Projects panel and double-click on
Microcontroller_STM32F101.SchDoc to open the schematic document.
19. Select component U2A
20. Switch back to the Bluetooth_Sentinel.PcbDoc PCB document to see the
VFQFPN36_N footprint selected.

<!-- p.138 -->

## 14.6 3D Layout Mode

21. While still being in the active PCB document, select View » 3D Layout Mode or press the
‘3’ key to enter 3D mode.

Numbers on the numerical keypad won’t work,
use the ones above the qwerty keys.

a) Press the ‘8’ key to change the 3D view to “Orthogonal Rotation” view.
b) Press the ‘9’ key or ‘0’ key for “90 Degree Rotation” or "Zero Rotation”.
c) Press and hold the Shift key until you see an orb as shown in Figure 166 below.

*Figure 166. Orb to navigate in the 3D environment*
d) While still holding Shift, press and hold the right mouse button on one of the
navigation objects in the orb shown in Figure 167 below (arrow, circle, dot) and now
move the mouse to change the 3D view.

*Figure 167. Orb controls for navigating in the 3D environment*
22. Select View » 2D Layout Mode or press the ‘2’ key to go back to the 2D view mode.

<!-- p.139 -->

## 14.7 PCB Layers

The visible layer tabs will be displayed at the bottom of the workspace. These are the layers that
are a part of your PCB design.
23. We can toggle through the different layers in multiple ways.
a) Click the two small arrows  beside the layer tabs to scroll through the tabs similar to
what is shown in Figure 168.
b) Click directly on different layer tabs change the current layer. When you’re on a certain
layer, this is what is called the Active layer.
c) Press the  “+” , “-” ,  or  “*” shortcut key on the numerical keypad to change the
active layer.
d) Notice the Heads Up Display (HUD) in the top left corner will display the current layer
name.

*Figure 168. Layers tab showing all available layers*

<!-- p.140 -->

## 14.8 View Configurations

24. Open the View Configuration panel by clicking on the Panels button at the lower right side
and selecting View Configuration, or the L shortcut key.
a) The View Configuration panel with the tab Layer & Colors will open as shown in Figure
169 below.

*Figure 169. View Configuration panel*
b) Activate or deactivate the visibility for different layers with a click on the  icon next to
the layer color.
c) Click on a color box to change the color of a particular layer.
d) Select the View Options tab as shown in Figure 170 below.
e) Under Objects Visibility click on the  icon for polygons to hide the polygons.

<!-- p.141 -->

*Figure 170. Object Visibility tab in the View Configuration panel*
Although the polygons are not visible while hidden, they will still affect your design.
They are still considered objects/obstacles for other features such as Interactive
Routing. If you prefer to temporarily disregard them from your design, you can go to
Tools » Polygons Pours » Shelve Polygons.
f) Under Objects Visibility click on the eye icon for Polygons to show the polygons again.
g) Move the slider on the right side to change the transparency for the polygon. You will also
notice that you can manual change the % of transparency, beside the slider.
h) View the results in the PCB.
i) If you changed the color of a layer in Step 24.c) above, change it back to its original color.
25. Experiment with other options and observe changes in the PCB view.
26. You can revert to the “Altium Standard 2D” configuration by selecting Altium Standard 2D
from the Configuration drop-down list as shown in Figure 171 below.

Please note that changing the configuration back to Altium Standard 2D does not
revert any changes that you’ve manually made to any layer colors.

<!-- p.142 -->

*Figure 171. Different predefined Views*

## 14.9 Board Insight Display

27.  Open the Preferences, and head to the section PCB Editor:
a) Select the Board Insight Display page.
b) Enable all options under Available Single Layer Modes if not enabled already and press
OK.
28. In the PCB document, toggle through the single layer modes by pressing Shift + S. Notice
the differences between the modes as indicated in Figure 172, Figure 173,Figure 174 and
Figure 175 on the following pages.
Notice in the HUD. It will show (Single) when you are in Single-Layer Mode. Single-
Layer mode is a very useful viewing mode when you simply want to work on a specific
layer and would like to hide the other layers that you’re currently not working on.

<!-- p.143 -->

*Figure 172. Regular 2D view*

*Figure 173. Single Layer Mode - Hide Other Layers*

<!-- p.144 -->

*Figure 174. Single Layer Mode - Grayscale other layers*

*Figure 175. Single Layer Mode - Monochrome other layers*
29. Return to the non-single layer mode using Shift+S until you see all the layers again.
30. Press Shift+H to toggle the HUD (Heads Up Display). We can also change the visibility in
Preferences » PCB Editor » Board Insight Modes » Display Heads Up Information.
Make sure the HUD is enabled when finished.

<!-- p.145 -->

## 14.10 Display

31. Open the Preferences dialog and select the Display page from the PCB editor branch.
32. Under the Highlighting Options section:
a) Enable all of the options.
b) Press OK to exit the Preferences dialog.
33. Jump to component C21 using the shortcut J»C and entering C21 into Component
Designator dialog.
34. If not already the active layer, change to the Top Layer as the active layer by selecting it
from the Layer Tabs at the bottom of the Workspace. You may have to click the left or right
arrows near the layer tabs to make it visible and select the Top Layer.
35. Enter Single Layer Mode by pressing Shift+S. All layers are now gray except the active
layer (Top Layer).
36. Mask net VBAT by selecting Pad 2 from C21, or the via next to the Pad, using the
command Ctrl + left-click. Notice that tracks connected to that Pad are now masked as
well as shown in Figure 176 below. Do Not Clear the highlight.

*Figure 176. Highlight all primitives*
37. Press Shift+S again, and now all other layers are hidden, instead of grey.
38. Open Preferences again, and head to the Display page under PCB Editor.
a) Disable Show All Primitives in Highlighted Nets.
b) Click OK to confirm. Notice that tracks on the Bottom Layer are no longer masked.
39. Clear selection by pressing Shift + C.
40. Exit single layer by executing Shift + S until all layers are showing.
41. Jump to component U4 using the shortcut J » C.
42. Place a Route from Pad U4-28 (Located in the upper left corner of the component) by
selecting Route » Interactive Routing.
a) Place the crosshair on Pad U4-28 and select it. Notice that the pad and existing routing
is now highlighted and the rest of the board is masked.
b) Right-click twice to exit the routing mode.
43. Open the Preferences dialog- page Display.

<!-- p.146 -->
a) Disable Apply Mask During Interactive Editing and disable Apply Highlight During
Interactive Editing.
b) Click OK to return to the PCB.
44. In the PCB, the pad should no longer be highlighted.
45. Press Shift+C to clear the board.
Feel free to change the Preferences for Interactive Routing as you wish. These
settings are based on personal preferences, and they will help you in the later
modules of this course.

## 14.11 Board Insight Mode

46. Open the Preferences, section PCB Editor:
a) Select the Board Insight Modes page.
b) Ensure the Display Heads Up Information is active.
c) Press OK.
47. Hover over component U4 to see the Heads Up Display as shown in the top left corner as
shown in Figure 177.

*Figure 177. Heads Up Display*
The Heads-Up Display can be disabled by pressing Shift + H

48. Close the project without saving.
