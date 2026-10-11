# AD20 Essentials - Module 3: Schematic Preferences

> Source: `ad20-essentials-exercises.pdf` (same folder), PDF pages 34-44 (printed page = PDF page; `<!-- p.N -->` marks page starts). Text only: figures are not extracted, only their captions. Altium Designer 20 UI; menu and panel names can differ slightly in newer versions.

<!-- p.34 -->

## 3.1 Purpose

In this exercise, you will learn about schematic preferences and how to customize
them. These preferences will allow you to customize your schematic environment and
ensure document clarity and standardization.

## 3.2 Preparation

1. Close all open projects in the Projects panel.
2. Go to File » Open Project and browse to the installed Example projects folder. Open
<AD Version>\Examples\Bluetooth Sentinel\Bluetooth_Sentinel.PrjPcb.
This project may also be available in the Recent Projects menu.
The default path to your installed examples is C:\Users\Public\Public
Documents\Altium\<AD Version>\Examples\

## 3.3 Setting Preferences

3. Go to  Preferences in the upper right corner of Altium Designer.
4. Expand the Schematic branch and open the General page. Verify that Components Cut
Wires is enabled as shown in Figure 29.
5. Open the Graphical Editing page. Verify that Display Strings as Rotated is unchecked (it’s
enabled by default). It can be found in Figure 29.

*Figure 29. General and Graphical Editing Preference Settings*
6. Click OK to save and close Preferences.

<!-- p.35 -->
7. In the Projects Panel, double-click on Microcontroller_STM32F101.SchDoc to open it
(Figure 30 below).

*Figure 30. Projects Panel*
8. Open the Components Panel from the Panels button. In this panel, set the drop-down to
select the Miscellaneous Devices.IntLib as shown in Figure 31 below.

*Figure 31. Library Selection from the Components panel*
9. Type cap in the keyword search to reduce the list to capacitors and select Cap Semi from
the library as shown in Figure 32 below.

<!-- p.36 -->

*Figure 32. Select Cap Semi from the Miscellaneous Devices.IntLib^*
10. Right click and select Place Cap Semi and then rotate the capacitor using the Spacebar.
11. Left-click to place the capacitor on existing wires as shown in Figure 33 below.
12. After you place the capacitor, right-click to exit the Place Part command.
Notice that the capacitor will be dropped on the wire which will automatically be cut into two
segments, which are terminated at the components’ pins. This is because we enabled the
Component Cut Wire preference

*Figure 33. Place Cap Semi onto the existing wire*
13. Before continuing to the next schematic, open the Components panel and reset the ‘cap’
search as shown Figure 34 below.

<!-- p.37 -->

*Figure 34. Reset "cap" search in the Components panel*
14. Open the schematic Oscillator_16MHz.SchDoc.
Observe how the wires are currently displayed on the left of component X1, displayed in
Figure 35 below. For document clarity, it is usually recommended for Cross-Overs to be
displayed. This can be enabled in Preferences.
*Figure 35. Schematic Connections for X1*
15. Click  Preferences, in the upper right corner of Altium Designer. Expand the Schematic
branch and open the General page. Enable Display Cross-Overs as shown in Figure 36
below.
16. Click OK.

<!-- p.38 -->

*Figure 36. Display Cross-Over Preference*
17. Notice in Figure 37 below that the cross-overs will then be displayed in the schematics.

*Figure 37. Cross-Overs being displayed after enabling it in Preferences*

<!-- p.39 -->

## 3.4 Graphical Editing

### 3.4.1 Always Drag

18. Make the schematic file Microcontroller_STM32F101.SchDoc the active document.
19. Click  Preferences, in the upper right corner of Altium Designer. Expand the Schematic
branch and open the Graphical Editing page. Check if Always Drag is active. Click OK to
close the Preferences dialog.
20. Left-click on U2B. While holding the left-click, move the cursor to drag the component
around. Notice the behavior of the connections where the wires will remain connected to the
components.
21. Hit Escape or Right-Click to abort the drag.
22. To move the component without maintaining connections, hold the Ctrl key, left-click and
hold it on U2B. The component should now move independently of the previously connected
tracks.
23. Go to Edit » Undo or hit Ctrl+Z to undo any changes if necessary.
While dragging a component, ensure to check the connections that it is about to
create. Before releasing the left mouse button, an indicator will show if there is a
netlist modification or not.

### 3.4.2 Convert Special Strings

24. Ensure Microcontroller_STM32F101.SchDoc schematic is the active document. Open
Preferences, in the Schematic branch, go to Graphical Editing. Ensure that the option
Display Names of Special Strings that have No Value Defined is enabled. Click OK to
exit the Preferences.
25. Navigate to the title block at the bottom right of the schematic sheet and notice the placed
text strings. These strings are pointing to parameters which currently do not have values yet.
Hence, the parameter names are shown, instead of their values.
26. We will make some changes to the Parameters as shown in Figure 38 below.
a) Open the Properties panel from the Panels button and open the Parameters tab.
b) Try changing the Title parameter value to Test and hit enter. Notice the change on
the title block.
c) Change the Title parameter value back to Microcontroller STM32F101.

<!-- p.40 -->

*Figure 38. Document Parameters*
27. Other parameters like =ProjectTitle are not in the document’s parameters list yet.
28. However, instead of adding a parameter as a Document Parameter, we will add a Project
Parameter. Note that the Document Parameters are local and unique per document, while
Project Parameters are global and common for all project documents.
29. To modify the project parameter list, we will refer to Figure 39 below.
a) Go to Project » Project Options. Then, open the Parameters tab.
b) Click Add…. Type ProjectTitle as the Parameter Name and Training Project
as its Value. Click OK.
c) The newly created parameter will then be listed. Click OK.

*Figure 39. Project Options*

<!-- p.41 -->
30. Notice that in Figure 40 below, the schematic should now show the newly created parameter
value in the Title Block. Open Bluetooth.SchDoc and notice that it will also share the
same value for the project parameter.

*Figure 40. Project Parameter added to each Schematic*
Special strings of the title block are defined & modified within the Schematic Template
file *.SchDot.

<!-- p.42 -->

## 3.5 Grids

31. Click  Preferences and expand Schematic branch and open the Grids page.
32. Under Imperial Grid Presets, click Altium Presets and select Course (3 settings) as shown
in Figure 41 below.
33. Click on the color box to the right of Grid Color if you wish to change the color of the grid.
34. Click OK to save and close the dialog.

*Figure 41. Grid Settings in Preferences*
35. In the schematics, toggle the snap grid through your new presets by hitting the G  key. You
can see the grid change between 50mil, 100mil, and 200mil on the Status Bar as shown in
Figure 42 below.

*Figure 42. Grid Information from the Status Bar*

<!-- p.43 -->

## 3.6 Schematic Defaults

### 3.6.1 Default Primitives

Currently, when placing a wire, it will be a blue, small-width wire. In this section, we will change
the default settings for wires so that it defaults to green, large-width wire when placed.
36. Click  Preferences and expand the Schematic branch and open the Defaults page.
37. In the Primitives List, select Wire as shown in Figure 43 below. Change the default Wire
width to Large and the color to Green.

*Figure 43. Default Primitives for Wire*
38. Click OK to save and close the preferences dialog.
39. Open a schematic document. Go to Place » Wire. Try placing some wires on the schematic.
Notice that the wires placed will now be default to green, large wires as shown in Figure 44
below.

*Figure 44. Large Green default Wires*

<!-- p.44 -->
40. Hit Esc to end command.
41. Click  Preferences, expand the Schematic branch and open the Defaults page. To reset
all primitive defaults, click Reset All.
The reset is applied by clicking the "OK" button. Also, we can hit F1 while in a
Preferences page or any general menu to open the corresponding online
documentation regarding the active window or menu.
42. In the Projects panel, close all projects and files without saving.
