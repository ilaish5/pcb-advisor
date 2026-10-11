# AD20 Essentials - Module 5: Schematic Capture

> Source: `ad20-essentials-exercises.pdf` (same folder), PDF pages 57-71 (printed page = PDF page; `<!-- p.N -->` marks page starts). Text only: figures are not extracted, only their captions. Altium Designer 20 UI; menu and panel names can differ slightly in newer versions.

<!-- p.57 -->

## 5.1 Purpose

In this module, you’ll learn how to add components in the schematic editor, along with
learn the best practices of schematic component placement.
In this exercise, you will start a project called WCTopping.PrjPcb and place components on
three schematics in this design. This is a daughter board providing expansion of a typical
controller board via a 40-pin connector.

## 5.2 Preparation

1. Close all existing projects you may have open.
2. Ensure that you have extracted the AD20 Essentials Exercises.ZIP file to your
Desktop. This will make the project easy to find for later modules.
3. Find the folder AD20 Essentials Exercises\ Module 5 - Schematic Capture.
This folder contains files you will use and can reference while you complete this module.

## 5.3 Create A New Project

4. Select File » New » Project… to launch the Create Project dialog. The dialog shown in
Figure 59 will appear.

*Figure 59. Create a New Project*

<!-- p.58 -->
5. Select Local Projects in the left pane. Use Figure 59 above as a reference for the following
steps.
6. Select <Default> in the Project Type pane, so that we create a new blank project.
7. Enter a project name of WCTopping.
8. Under the Folder area, click on the Triple Dot Icon and navigate to your Desktop. This is
where your project will be saved.
9. Click the Create button to create the new project. Feel free to go to your desktop to confirm
that a WCTopping folder has been created.
10. Return to Altium Designer and notice that in the Projects panel there is a project called
WCTopping.PrjPCB as shown in Figure 60 below.

*Figure 60. Projects panel with the WCTopping project recently created*

### 5.3.1 Adding New Documents

11. Right-click the project and select Add New to Project » Schematic from the pop-up menu
as shown in Figure 61 below. This will add a new schematic to project. The default name is
Sheet1.SchDoc
12. Repeat this operation and add three additional schematic files.

*Figure 61. Added new Schematics to the Project*

<!-- p.59 -->
13. Select menu File » Save All. A dialog box will pop-up prompting you to save the new
schematics you added.
14. Name the schematics in your project using the same names below:
- 1st schematic as Processor_Interface.SchDoc
- 2nd schematic as Digital_IO.SchDoc
- 3rd schematic as Relay_IO.SchDoc
- 4th schematic as CAN_Interface.SchDoc
15. The Projects panel should now look like the one in Figure 62 below. Double check this by
navigating to the Desktop project folder. To do this, right-click on the project name and
select the Explore menu.

*Figure 62. Renamed Project Files*

### 5.3.2 Adding an Integrated Library

The schematic library can be a local library or a library of components contained in an Integrated
Library stored on a server. For this exercise, we will use the Integrated Library located in the
folder AD20 Essentials Exercises\ Module 5 - Schematic Capture.
16. Open the Components panel by clicking on the Panels button in the bottom right corner.
a) The Components panel should open with the Miscellaneous Devices.IntLib
selected as shown in Figure 63. If not, select the drop-down menu from the top of the
Components panel and then select the required library.
b) Note that the Components panel is divided into several panes. The topmost pane displays
a list of library components for the selected library. The subsequent panes have
information related to the selected component, e.g., symbol and footprint previews and
models linked to the component.
17. Click the  button in the top right corner of the Components panel and select File-based
Libraries Preferences…. The Available File-based libraries dialog will open as shown in
Figure 63 and Figure 64.

<!-- p.60 -->

*Figure 63. Components Panel with the Miscellaneous Devices.IntLib selected*

<!-- p.61 -->

*Figure 64. Installed Libraries currently available*
18. Select the Installed tab.
19. Click on the Install… button. This is where we will install a component Library for us to
access the components from that Library.
20. Navigate to the training folder AD20 Essentials Exercises\ Module 5 -
Schematic Capture and select WCT.IntLib, click the Open button.
21. The WCT.IntLib library should now appear in the Available File-based libraries dialog
along with the previously installed libraries as shown in Figure 65.

*Figure 65. WCT.IntLib  added to Installation*
22. Click Close to close the Available File-based libraries dialog.

<!-- p.62 -->

## 5.4 Component Placement

### 5.4.1 Setting the grid

23. Start by double clicking on the Processor_Interface.SchDoc schematic to make it the
focused schematic.
a) Open the Properties panel from the Panels button.
b) In the General tab, set the Snap Grid value to 200mil, and press Enter to apply the new
value as shown in Figure 66.

*Figure 66. Set the Snap Grid to 200mil*

### 5.4.2 Processor Interface Schematic Component Placement

24. Ensure that the Processor_Interface.SchDoc is the active schematic document.
Figure 67 below will be used a reference for the following section.

<!-- p.63 -->

*Figure 67. Processor_Interface Schematic*
25. Select the Miscellaneous Connectors.IntLib from the drop-down list of libraries in
the Components as shown in Figure 68 below.

*Figure 68. Select the Miscellaneous Connectors library*
26. Scroll down the list of components to find the 40-pin I/O Connector called Header 20x2
as shown in Figure 68 above.
27. Right-click to Place Header 20x2 and move the cursor with the attached symbol inside the
schematic page.

<!-- p.64 -->
28. Before placing the connector on the schematic, press the TAB key:
a) In the Properties panel that opens, any changes to the default properties will be applied to
subsequently placed objects.
b) Change the reference designator to J1 as shown in Figure 69.
c) To apply the changes press, Enter and continue with the placement.
The TAB key is used to pause the command that you are currently in. This allows you
to make changes to an item’s properties. To resume the command, hit the Enter key,
or the “Pause” icon in the middle of the editor to continue with the command.

*Figure 69. Component Properties dialog*
29. While in placement mode with a connector attached to the mouse pointer, experiment with
commands to orient the component.
a) Spacebar to rotate counterclockwise 90°
b) Shift+Spacebar to rotate clockwise 90°
c) X to flip along the X-axis
d) Y to flip along the Y-axis
If a placed component should be rotated, select the component and press Spacebar
to rotate counterclockwise 90°) or Shift+Spacebar to rotate clockwise 90°.
30. Left-click anywhere in the schematic to place the component.
31. Continue placing multiple components, up to at least J4. The reference designators will
increment automatically. You will remain in placement mode and be able to place multiple
components until you right-click or press ESC.

<!-- p.65 -->
32. Delete all the connectors on the schematic except for J4. This will give you the opportunity
to experiment with the Smart Drag Selection feature:
a) Drag a selection window from left-to-right using the left-mouse-click, around the 3
connectors (J1 to J3). This will select all objects that fall completely within the bounds of
the selection area. This behavior is the same as using the Edit » Select » Inside Area
command.
b) Now drag a selection window from right-to-left. This will select all objects that fall
completely inside the selection area and are touched by its boundary. This behavior is
the same as using the Edit » Select » Touching Rectangle command.
c) The Green or Blue coloring is used to distinguish which mode of selection is being used
visually. Dragging left-to-right uses a blue rectangle while dragging right-to-left uses
a green rectangle as shown in Figure 70 below.

*Figure 70. Colored boxes indicating the drag-select method used*
33. Make sure you hit the Delete key to delete the appropriate connectors from the schematic.
34. Open the Components panel, and make sure the WCT.Intlib is the active library. It can be
found from the topmost drop-down menu of the Components panel.
35. Use the library search, or simply navigate down the list of components, and place two
Cap100nF_50V_0603 capacitors from the WCT.IntLib library, into to the
Processor_Interface.SchDoc. Making the Components panel larger may help you
see the full name of the component you wish to select and place.
36. Save the schematic by right-clicking on the schematic in the Projects panel, and click Save.

### 5.4.3 CAN_Interface Schematic Component Placement

*Figure 71. CAN_Interface Schematic*

<!-- p.66 -->
37. Open the CAN_Interface.SchDoc.
38. Since we would now like to place components from the Manufacturer Part Search panel, we
will need to connect to the Altium Content Vault to yield the maximum component search
results.
a) Ensure that you are signed into your AltiumLive account, by going to the icon in the upper
right corner as shown in Figure 72 below, or click Licenses to open the Licenses
Management page, and enter your AltiumLive credentials.
If you already see your name in the upper-right corner instead of the icon shown in
Figure 72, this means you’re already signed into your AltiumLive account. If you don’t
remember your login information, please contact your in-house Altium administrator,
or contact Altium Technical Support.

*Figure 72. Signing into your AltiumLive account to access the Altium Content Vault*
b) Select  Preferences, in the upper right corner of Altium Designer.
i) Open the page Data Management - Servers
ii) Expand the “Known Servers” option as shown in Figure 73.
iii) Ensure that Automatically connect Altium Content Vault is enabled, and that the
“On” option is also enabled. You will know that you are connected when the
“Connected” word is visible.
iv) Close the preferences by clicking OK.

<!-- p.67 -->

*Figure 73. Connecting to the Altium Content Vault in Preferences*
c) Make the CAN_Interface schematic the active document.
39. Placing components from the Manufacturer Part Search panel is possible, allowing you to
view Supplier Information prior to placement. Open the Manufacturer Part Search panel by
clicking on the Panels button and choosing Manufacturer Part Search.

*Figure 74. Manufacturer Part Search panel*
40. With the CAN_Interface schematic open, search for MCP2515 by typing in the upper
main field of the Manufacturer Part Search panel as shown in Figure 74 above and pressing
Enter.
41. In the search results, right-click MCP2515-E/SO and select Place as shown in Figure 75
below. You may need to expand the panel for easier viewing.
42. With the component still on your cursor, before clicking to place on the schematic, press
Tab and change the reference designator to UC1 in the Properties panel.

<!-- p.68 -->

*Figure 75. Select and Place component from the Manufacturer Part Search panel*

43. Right-click once the component has been placed to return focus to the Manufacturer Part
Search panel. If you closed the Manufacturer Part Search panel, it can be re-opened from
the Panels button.
44. Using the search bar in the Manufacturer Part Search Panel, search for MCP2551. Right-
click and place MCP2551-I/SN to the right of UC1. During placement, press TAB to set
the reference designator to UC2. Once again, you may need to move or close the
Manufacturer Part Search panel before changing the designator of the component.
45. Return to the Manufacturer Part Search panel and search for CSTCE16M0V53-R0 (a
16MHz Crystal).
46. Right-click and place CSTCE16M0V53-R0 to the left of the UC1 MCP2515 component, as
shown in Figure 71 on a previous page. Press TAB before placing it and set the reference
designator to X1. You can always open the Properties panel to access the components
properties.
47. Hit ESC to end the command, and Save the CAN_Interface schematic from the Projects
panel.

<!-- p.69 -->

### 5.4.4 Relay_IO Schematic Component Placement

*Figure 76. Relay I/O Schematic*
48. Open the Relay_IO.SchDoc
49. From the Components panel, place the NTHD4508NT1 from the WCT.IntLib library. Use
the search bar, or navigate to the component to find it as shown in Figure 77.
a) This is a multi-part component as indicated by the part information below the Symbol
preview as shown in Figure 77. A multi-part component is represented by multiple
schematic symbols. Expand the Models pane if necessary.

<!-- p.70 -->

*Figure 77. Placing NTH Multi-Part into the Relay I/O schematic*
b) Select Part A.
c) Right-click and place the component. During placement, press TAB to change the
designator to Q1, hit Enter and place the component.
d) It will place Part A, and now Part B will be on your cursor. Place that part as well.
This is considered a Multi-Part component that is represented by more than 1 schematic
symbol.
e) Right-click to end the command after placing Q1A and Q1B.
50. We will now place another component from the Manufacturer Part Search panel.
a) Open the Manufacturer Part Search panel from the Panels button.
b) Search for CD40109BPW.
c) Right-click and Place CD40109BPW, which should be the first option that appears.
d) Right-click to end the command once the component is placed, and close the
Manufacturer Part Search panel.
51. Search and place the remaining components for the Relay_IO.SchDoc from the
WCT.IntLib found in the Components panel. Press TAB to set the designators
accordingly. Refer to Figure 76 on a previous page to reference the component placement.
a) Res1K_0805 (2)
b) LED_Red0603 (2)
c) Diode 1N4148 (2)
d) Anderson-1Pin BLK_PCB_RHT (2)
e) Anderson-1Pin Red_PCB_RHT (2)
52. Save the Relay_IO.SchDoc schematic.

<!-- p.71 -->

## 5.5 Adding an Existing Schematic to Your Design

53. In Altium Designer, right-click the WCTopping.PrjPcb project in the Project panel and
select Add Existing to Project… as shown in Figure 78 below.

*Figure 78. Right-click the Project to Add Existing to Project*
54. In the Choose Documents to Add to Project dialog, locate the schematic Power
Supply.SchDoc found in the AD20 Essentials Exercises\ Module 5 -
Schematic Capture folder on your desktop.
55. Click Open to add the file to your project.
56. Open the Power Supply schematic from the Projects panel and ensure its focused
document.
57. Right-click the Power Supply schematic in the Projects panel, and click Save As. Browse
to your WCTopping folder (stored on your desktop) to save the schematic into our project
folder.
58. Save all documents using File » Save All.
