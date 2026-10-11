# AD20 Essentials - Module 1: Design Environment

> Source: `ad20-essentials-exercises.pdf` (same folder), PDF pages 14-28 (printed page = PDF page; `<!-- p.N -->` marks page starts). Text only: figures are not extracted, only their captions. Altium Designer 20 UI; menu and panel names can differ slightly in newer versions.

<!-- p.14 -->

## 1.1 Purpose

In this exercise, you will learn to use some general GUI and navigation functions. You
will have mastered the basic operations of the Altium Designer Environment after the
completion of this exercise. This will be the foundation for future studies.
Altium Designer is a unified design environment. When you run Altium Designer for the first time,
it will become readily apparent through your first steps of working in the software  that all EDA
tools are included in a single application. This includes schematic design, simulat ion, signal
integrity analysis, PCB design tools, documentation/fabrication/assembly outputs, and library
creation.

## 1.2 Opening Files

1. Click File » Open Project. Select Local Projects and browse to the example projects folder,
which is installed by default in C:\Users\Public\Public Documents\Altium\<AD
Version>\Examples\ Bluetooth Sentinel.
2. Open the Bluetooth_Sentinel.PrjPcb from its Bluetooth Sentinel sub-folder as shown
in Figure 1 below.

*Figure 1. Open Project Dialog*

<!-- p.15 -->
NOTE: If this is your first time opening Altium Designer, some panels may appear in
the middle of your screen. They can be closed by clicking the “x” in the top-right
corner of the panel, or by right-clicking the title bar of the panel, and Close.
3. Locate the Projects panel on the left of the window as shown in Figure 2 below and double-
click on the schematic file Microcontroller_STM32F101.SchDoc. This will open the
schematic document within the active workspace and provide the working view of the
schematic.
4. In the Projects panel, double-click on the PCB file Bluetooth_Sentinel.PcbDoc. This
will open the PCB document within the active workspace and provide the working view of the
PCB.

*Figure 2. Altium Designer Environment*
5. Notice that there are now two tabs on the Document Bar at the top of the editor. Click on
each of these tabs and observe the workspace change to match the document that you are
focused on.
6. Hit the shortcut keys Ctrl+Tab or Ctrl+Shift+Tab to cycle between the documents.
7. If we open multiple documents to the point where the tabs fill up the entire bar, we can
configure its grouping method. Click the Preferences icon  on the upper right corner of
Altium Designer. Expand the System branch and open the View page. Within the Documents
Bar settings, you can enable the Group documents if need checkbox and set it to By
document kind as shown in Figure 3.

<!-- p.16 -->

*Figure 3. Preferences for document grouping*
8. Click OK to close the Preferences window.

If enabled, the documents will be grouped as needed. If there is adequate space
within your documents bar, the documents will not be grouped.

<!-- p.17 -->

## 1.3 Documents & Panels

### 1.3.1 Document Bar

9. Right-click on a Document tab in the Document Bar (as shown in Figure 4 below) and select
Tile All in the pop-up menu. All the currently open documents will be split into individual
windows and will be displayed within the main design window.
To resize the window, simply move the cursor to the divider of the two split windows.
When a bi-directional arrow appears, left-click and drag to resize the split windows.

*Figure 4. Document Bar*
10. While documents are tiled or split within the editing workspace, right-click on any document
tab in the Document Bar and select Merge All from the pop-up menu. The workspace is
restored to a single document display.
11. Feel free to experiment with the other options in the right-click menu like Split Vertically and
Split Horizontally. For multi-monitor display, click on Open in New Window in the right-
click menu to open a new instance or simply drag a document tab to the secondary dis play.

<!-- p.18 -->

### 1.3.2 Panel Access

12. Locate the Panels button in the lower right corner as shown in Figure 5 below.
13. Select Components from the popup to open the Components panel. The panels are also
listed in the menu under View » Panels.

*Figure 5. Panel access*

### 1.3.3 Panel Display Modes

Three different display modes are supported for panels - Docked, Pop-up and Floating.

#### 1.3.3.1 Docked Mode

14. Right-click on the title bar of the Projects panel. Click on Allow Dock in the pop-up menu as
shown in Figure 6 below and ensure that it is enabled for both Horizontally and Vertically.

*Figure 6. Allowed docking mode settings*

<!-- p.19 -->
15. Left-click on the title bar of the Projects panel to move it. Drag it to the center of the window
and notice that while the panel is attached to the cursor, we have both horizontal and vertical
docking option as shown in Figure 7 below. Hover the cursor above the left docking option
and release the left-click hold.

*Figure 7. Docking Options*

#### 1.3.3.2 Pop-up Mode

16. Locate the Components panel tab on the right of the window. Hover above its tab to open
the panel. This mode is what we refer to as Pop-up mode, and is often used to maximize
screen’s real estate especially when working on a small monitor. If the Components panel is
not in pop-up mode, head to the Panels button to the lower right side of Altium Designer to
open it.
17. To change the Components panel to a docked mode, click on the pin symbol  while the
panel is open. The pin symbol will then change to  indicating that it is in docked mode.
18. To revert it back to a pop-up mode, click on the pin symbol again. While in this mode,
moving the cursor away would hide then panel after a brief amount of time.
19. Note that the pop-up and hide delay is controlled in  Preferences under the System
branch, in the View page as shown in Figure 8.

<!-- p.20 -->

*Figure 8. Pop-up panel delay settings*

#### 1.3.3.3 Floating Mode

20. In the bottom right corner of Altium Designer, click on Panels and select Storage Manager
to open the Storage Manager panel shown in Figure 9 below. By default, this is a floating
panel and handy to explain Floating Mode.

*Figure 9. Opening the Storage Manager panel*
21. A panel in this mode can be placed anywhere within or outside the Altium Designer
environment. For example, the Components panel is commonly made to be floating and
placed on another monitor. Move the Storage Manager panel to the middle of the window.
22. To observe the transparency effect of this floating panel, invoke a command by going to
Place » Wire. Move the command crosshair towards the panel and notice the change of its
transparency. Note that the transparency settings can be controlled in  Preferences under
the System branch, in the Transparency page as shown in Figure 10 below.
23. End the Place » Wire command using the ESC key and close the Storage Manager panel
by clicking on the  close cross button.

<!-- p.21 -->

*Figure 10. Transparency setting for Floating panels*

### 1.3.4 Grouping Panels

Two modes of grouping panels are supported: Tabbed Grouping and Fractal Grouping.

#### 1.3.4.1 Tabbed Panel Grouping

24. By default, the Projects, Navigator and SCH Filter panels are grouped together in one panel.
To open any one of them, click on the tabs at the bottom of the panel shown in Figure 11.
This is what we refer to as Tabbed Panel Grouping.

*Figure 11. Tabbed Panel Grouping*

<!-- p.22 -->

#### 1.3.4.2 Fractal Panel Grouping

25. Left-click on Projects tab of the panel group and drag it out to enter Floating mode. Drag it
back into the original panel area and notice that as we hover above any of the 4 directional
icons, it will display a blue highlight as shown in Figure 12.
26. Release the click on the top directional icon and notice that the panel will be split into fractal
segments.

*Figure 12. Fractal Panel Grouping*
To prevent a moving panel from automatically docking, grouping or snapping, hold the
CTRL key

### 1.3.5 Closing Panels

27. Close any panel by right-clicking in its title bar or on its tab, then choose Close from the pop-
up menu. Alternatively, click the close cross  at the far right of a panel's caption bar, if it
is not in tabbed mode.
If the panel is part of a group, clicking the    entry closes all panels in the group. To
close a particular panel, right-click on its name in the title bar and close.

### 1.3.6 Maximizing/Restore Panels

28. When in floating mode, a panel can be maximized by right-clicking in its title bar (or on its
tab, where available) and choosing the Maximize entry from the pop-up menu.
29. To restore a maximized panel back to its original size, simply right-click in its title bar or tab
and choose the Restore command from the pop-up menu. Alternatively, you can double-
click the title bar to toggle between maximized and restored states.

<!-- p.23 -->

### 1.3.7 Desktop Layouts

30. The panel arrangements are what we refer to as Desktop Layouts. It can be saved, loaded
and reset to default in  Preferences. Open the Preferences, accessible from the upper
right corner of Altium Designer.
31. Open the System branch and open the View page as shown in Figure 13 below. Within the
Desktop pane, desktop layouts can be saved, loaded or reset to default.
32. Click on Reset. Close the Storage Manager and SCH List panel if they’re open. Then, click
OK to exit the Preferences.

*Figure 13. Desktop Layouts*

## 1.4 Toolbars

Like menus and panels, both the Active Bar and Classic Toolbars are context sensitive, so only
commands that are relevant to the document of focus are displayed.

### 1.4.1 Active Bar

33. Make the schematic the current document of focus. At the top of the document, the Active
Bar appears, as shown in Figure 14 below.
34. Move the cursor to any of the icons in the Active Bar. Wait a second for a hint to appear
describing the function of the tool.

*Figure 14. Active Bar in the Schematic Editor*
35. Open the PCB document. Observe the icons as shown in the Active Bar and note the
changes shown in Figure 15 below.

<!-- p.24 -->

*Figure 15. Active Bar in the PCB Editor*
36. Return to the schematic document.

### 1.4.2 Classic Toolbars

In addition to the Active Bar, classic toolbars are also available.
37. To open a classic toolbar, go to View » Toolbars and select Schematic Standard to enable
it.
38. Notice that the toolbar will then be added underneath the menu list on the top of the window
as shown in Figure 16 below. To disable it, simply return to View » Toolbars and uncheck
on Schematic Standard.

*Figure 16. Classic Toolbar*

<!-- p.25 -->

## 1.5 Menu Operations

### 1.5.1 Right-Click Context Menu

39. Right-click any free space in the schematic editor and observe the changes to the menu as
shown on the left side of Figure 17 below.
40. In the Microcontroller_STM32F101.SchDoc, left-click to select any component, then
right-click to observe the content in the context menu as shown on the right side of Figure
17 below.
*Figure 17. Right-click context menu*
41. Feel free to explore the menus and options available while in the right-click menu.

### 1.5.2 Shortcut Keys

42. Some menu and menu entries have underlined letters.
a) With the schematic in focus, access the File Menu by pressing the F key directly. The
File menu opens at the location of your cursor.
b) From the popup, press the S key to access the Save command.

<!-- p.26 -->

## 1.6 Status Bar and Command Status

43. Click the View menu and locate the Status Bar and Command Status entries as shown in
Figure 18 below.

*Figure 18. Activation status for the Status Bar and Command Status*
44. Ensure that both entries are enabled with a check next to their name. To enable the options,
click the item to toggle it.
45. Move the cursor in the schematic editor area and you’ll notice the X and Y values changing
in the Status Bar, as shown in Figure 19 below.
46. Go to Place » Wire. The active command is displayed in the command status area shown in
Figure 19 below. Hit Escape or right-click to exit from the command.

*Figure 19. Status Bar and Command Bar information with in the Place » Wire command*

## 1.7 Undo and Redo

47. Select a component and hit Delete to delete a component in the schematic.

<!-- p.27 -->
48. Click the Undo and Redo icons in the top left corner as shown in Figure 20 below.

*Figure 20. Undo and Redo icons*
49. As an alternative, use the shortcut key Ctrl+Z or Alt+Backspace for Undo. For redo, the
shortcut key is Ctrl+Y or Ctrl+Backspace.

Feel free to experiment with your panels, opening them, closing them, docking,
undocking, creating tabbed and fractal groups. You can always revert to defaults so
give them a try and become comfortable with their controls.
50. Open the Projects panel. Right click on the project and click on Close Project on shown in
*Figure 21. Click Save None and click OK.*

<!-- p.28 -->

*Figure 21. Close Project*
