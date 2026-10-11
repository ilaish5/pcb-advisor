# AD20 Essentials - Module 4: Navigating Schematics

> Source: `ad20-essentials-exercises.pdf` (same folder), PDF pages 45-56 (printed page = PDF page; `<!-- p.N -->` marks page starts). Text only: figures are not extracted, only their captions. Altium Designer 20 UI; menu and panel names can differ slightly in newer versions.

<!-- p.45 -->

## 4.1 Purpose

This module will teach you some basic operations in the schematic editor such as
preference settings, mouse actions, frequently used shortcut keys and search actions
in the schematic environment.

## 4.2 Preparation

1. If not already open, click File » Open Project and browse to your installed Example
projects folder. Select <AD version>\Examples\Bluetooth
Sentinel\Bluetooth_Sentinel.PrjPcb.This project may also be available in the
Recent Projects menu.
The default path to your installed examples is C:\Users\Public\Public
Documents\Altium\<AD Version>\Examples\

## 4.3 Basic Schematic Preference Settings

Schematic Preferences are system specific settings which help you control the behavior and
display of the Schematic Editor to suit your working style and needs. Let's take a look at some
basic preferences you may want to change.

### 4.3.1 Setting the Default Template & Sheet Size

2. Select    Preferences, in the upper-right corner of the interface. Open the Schematic
branch and highlight the General page as shown in Figure 45. From within a focused
schematic document, you can also gain access to the command Tools » Preferences… .

<!-- p.46 -->

*Figure 45. General Page from the Schematic Preferences*
3. Navigate to Sheet Size in the bottom right, and a drop-down menu will appear as highlighted
in Figure 45 above. You can set the default schematic size in this menu.
4. The default setting is A4 or A – depending on the region you are working in. Cancel the
dialog.
5. Use the File » New » Schematic command to add a schematic sheet to the project. The
Sheet Size setting according to your preference is used on the new schematic sheet (e.g.
A4).
6. Reopen  Preferences, click Template and a drop-down menu will appear. You can set
the default template file for new schematics in this menu. By default, No Default Template
File is defined.
7. Change the setting to a template of your choice and OK the dialog.
8. Add a second schematic sheet using the File » New » Schematic command and compare
the two newly added sheets. Now the chosen template is used when adding a schematic
sheet.
9. Close both schematic sheets by selecting them and using the Right Mouse Click Button »
Close command.

<!-- p.47 -->

### 4.3.2 Project Insight

10. To view the connectivity insight of our design, the project needs to be compiled. Use Project
» Validate PCB Project Bluetooth_Sentinel.PrjPcb to compile the project. Close the
Messages panel if it appears.
If you have Dynamic Compiling enabled, there is no need to compile the project to
show the Design Insight, as it would do it automatically. We will discuss Dynamic
Compiling in a later module.
11. In the  Preferences, open the System branch and look at the Design Insight page. Check
Enable Project Insight and click OK as shown in Figure 46 below.

*Figure 46. Preferences for Design Insight*

<!-- p.48 -->
12. In the Projects panel, hover the mouse cursor over the Bluetooth_Sentinel.PrjPcb
project icon  as shown in Figure 47 below, and a thumbnail view of the documents within
the project will appear at the cursor position.

*Figure 47. Project Insight thumbnail when hovering over the Project icon*

<!-- p.49 -->

### 4.3.3 Connectivity Insight

13. In the Preferences  within the Design Insight page, enable the checkbox for Enable
Connectivity Insight and in the Document Tree for Mouse Hover as shown in Figure 48
below.
14. Click OK.

*Figure 48. Connectivity Insight Preferences*
15. Open Bluetooth_Sentinel.SchDoc and Host_Controller.SchDoc.
16. Make Bluetooth_Sentinel.SchDoc the focused document.
17. Hover the mouse over the Processor Sheet Symbol block as shown in Figure 49. A large
thumbnail of the Host_Controller.SchDoc will appear next to the cursor.

<!-- p.50 -->

*Figure 49. Hover over the Sheet Symbol to view the Schematic thumbnail*
18. Next, move the cursor to hover over the Harness as shown in Figure 50 below.

*Figure 50. Hover over the Bus to view connectivity*

<!-- p.51 -->
19. A large thumbnail will appear next to the cursor, as shown in Figure 51 below, which shows
the connections in the design.

*Figure 51. Connectivity Insight after hovering over the Harness*
20. Slowly move your cursor down to Host_Controller.SchDoc at the bottom of the
thumbnail as shown in Figure 52 below, to change the thumbnail view to the lower level
schematic.
21. Left-click Host_Controller.SchDoc from the pop-up insight to open the schematic.

The schematic preview will be blank and only show a name and icon if the
corresponding schematic is not currently opened.

<!-- p.52 -->

*Figure 52. Connectivity Insight with Host_Controller.SchDoc*
22. Open  Preferences and click Set to Defaults » Page in the lower left corner of the
Design Insight page as shown in Figure 53 below. Click OK to exit the dialog.

*Figure 53. Set Design Insight Preferences back to Default*
In the preferences within the Navigation page, in the section Highlight Methods, you’ll
find a slider that allows you to control the mask level for the objects. The mask level is
used for navigation, cross-probing and exploring differences. To clear any masking, hit
Shift+C to clear any selections or masking.

<!-- p.53 -->

### 4.3.4 Schematic Navigator

23. Use the Navigator panel to browse nets, components, or pins across the entire design.
24. Open the Navigator panel by clicking Panels button and select Navigator as shown in
Figure 54 below.

*Figure 54. Opening the Navigator panel*
25. The Navigator panel will open and docked to the left by default. Use Figure 55 as a
reference for the following steps.
26. Click on a document name in the Navigator panel to see nets and components just for that
page.
If no components or nets are displayed inside the Navigator panel, compile the project
by selecting Project » Validate PCB Project Bluetooth_Sentinel.PcbDoc. If
Dynamic Compiling is enabled, the components and nets will be populated
automatically.
27. Click on the Flattened Hierarchy to see the nets and components for all schematics in the
project.
28. With the Flattened Hierarchy tab selected, search for component R9 to jump to that
component as shown in Figure 55.

<!-- p.54 -->

*Figure 55. The Navigator Panel docked to the left*

## 4.4 Navigation within the Schematic Workspace

### 4.4.1 Basic Navigation using the Mouse

29. Make the schematic file Microcontroller_STM32F101.SchDoc the focused document
by left-clicking on its document tab or from the Projects panel.
a) From the View menu, select Fit All Objects
b) In the schematic, right-click and hold until the panning hand cursor appears .
c) Drag the schematic around while holding the right mouse button down.
d) Release the right mouse button to end.
30. To change the zoom, click & hold mouse wheel, then slide mouse forward/back.
31. To Zoom in or out click and hold Ctrl + roll mouse wheel
32. Up/Down: roll mouse wheel (scrolling)
33. Left/Right: click and hold Shift + roll mouse wheel

### 4.4.2 Basic Navigation using the Keyboard

34. Maintain the focus on the Schematic Workspace and observe the behavior of the following
Shortcut Keys:
35. To Zoom out press PAGE DOWN.
36. To Zoom in press PAGE UP.
37. To Fit All Objects, press CTRL+PAGE DOWN.
38. To pan and re-center your workspace based on your cursor position press HOME.
39. To move in a direction by one Grid Step press the ARROW KEYS.
40. To move in a direction by 10 Grid Steps press SHIFT+ARROW KEYS.

<!-- p.55 -->

### 4.4.3 View Menu Hotkey Sequences

41. Maintain focus on the Schematic Workspace and try the following Hotkey Sequences:
Follow the underlined letters within menus and sub-menus to learn hotkey sequences.
- To View » Fit Document press the V » D keys in succession
- To View » Fit All Objects press the V » F keys in succession
- To View » Area press the V » A keys in succession, define the viewing area by
drawing the diagonal corners of a rectangular area
- To View » Around Point press the V » P keys in succession
- To View » Selected Objects press the V » E keys in succession

### 4.4.4 Jump Menu Hotkey Sequences

42. Maintain the focus on the Schematic Workspace and observe the behavior of the following
jump commands. The Edit » Jump menu is commonly used, so the status of this sub-menu
has been elevated to a popup menu with its hotkey J.
43. To Jump » Origin, press the J » O keys in succession
44. To Jump » Location, press the J » L keys in succession. Then enter the X, Y coordinates
in the Jump to Location dialog as shown in Figure 56 below and click OK to move the
cursor to the defined coordinate location. Zooming and panning will occur when necessary
if the target location is outside the visible area.

*Figure 56. Jump to Location (Shortcut Keys J » L)*
45. Maintain the focus on Microcontroller_STM32F101.SchDoc
a) To Jump » Component, press the J » C keys in succession.
b) Enter U2 into the resulting Component Designator dialog.
c) Press OK and the cursor will jump to the component U2.
In this example U2 is a component with two parts. You have the option to jump to the
next part of U2 when the Find Text – Jump dialog opens.
d) Zoom and pan will occur only if necessary to reach the location of the component in the
event it is currently outside the visible area.
e) Click Close for the Find Text – Jump dialog, then close the Messages panel.

<!-- p.56 -->

### 4.4.5 Search with the Search Field

46. Make the schematic file Bluetooth_Sentinel.SchDoc the focused document by left-
clicking on its document tab or open it from the Projects panel.
47. With the Projects panel open, enter R10 in the search field at the top of the Projects panel
as seen in Figure 57 below.
48. You will notice that the search result will highlight all fields that matches the input of the
search field. Locate the component R10 by opening the Components folder and its
subdirectory.

*Figure 57. Component Search from the Projects panel*
49. Close all documents from the Window menu and Close All. Do not save any changes if
prompted.
50. Then, delete the “R10” text in the search field at the top of the Projects panel, which can
be seen in Figure 58 below.

*Figure 58. Delete search field from the Projects panel*
