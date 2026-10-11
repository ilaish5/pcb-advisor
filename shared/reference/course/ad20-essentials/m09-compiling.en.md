# AD20 Essentials - Module 9: Compiling in Altium Designer

> Source: `ad20-essentials-exercises.pdf` (same folder), PDF pages 98-108 (printed page = PDF page; `<!-- p.N -->` marks page starts). Text only: figures are not extracted, only their captions. Altium Designer 20 UI; menu and panel names can differ slightly in newer versions.

<!-- p.98 -->

## 9.1 Purpose

In this exercise, you will learn how to compile a PCB Project and learn how to review
and resolve any reported messages after compiling, such as warnings and errors.
Compiling is an important step that should not be overlooked. Compiling builds a netlist for each
schematic sheet, creates sheet-to-sheet connectivity and builds the Unified Data Model. Running
the compiler analyzes the complete design to check for drafting and electrical errors.

In addition to traditional compiling, we have the option to enable Dynamic Compiling. The design
connectivity model is incrementally updated after each user operation. You do not need to
manually compile the project to see the contents of the Navigator panel, run the BOM, perform
an ECO, etc.

## 9.2 Preparation

1. Close your current WCTopping.PrjPcb project.
2. Open the WCTopping PrjPcb project from the
AD20 Essentials Exercises\ Module 9 - Compiling in Altium Designer
folder.

## 9.3 Project Options

Before compiling the project, you should first check the Error Reporting settings to be sure they
are defined properly for what you are designing.

### 9.3.1 Error Reporting Tab

3. Right-click the WCTopping project from the Projects panel, and select Project Options.
Click on the Error Reporting tab as shown in Figure 116.

<!-- p.99 -->

*Figure 116. Project Options Error Reporting Tab*
4. Scroll down to view the different categories of violation checks that the compiler performs.
5. Left-click one of the Report Mode icons (such as Warning or Error) and change it to a
different value. Error reporting for all of these violations can be changed at any time, and
will only apply to the specific project.
6. Click on Set to Installation Defaults button in the bottom left corner to reset, confirm the
reset with YES.

<!-- p.100 -->

### 9.3.2 Connection Matrix Tab

7. Click the Connection Matrix tab. You can set the reporting mode for the connections
between the different pin, port, and sheet entry types. Left-click on some of the boxes to
change the level of reporting as shown in Figure 117 as shown below.

*Figure 117. Connection Matrix Tab*
8. Click the Set to Installation Defaults button in the bottom left corner to reset the
Connection Matrix settings, confirm the reset with YES.

A common setting that is user for the default ERC matrix setting, is to set the
Unconnected information to Warning instead of No Report, to report all open Pins,
Ports, and Entries.

<!-- p.101 -->

### 9.3.3 Options Tab

9. Open the Options tab as shown in Figure 118 below.

*Figure 118. Options Tab showing Netlist Options*
10. In the bottom left corner of this dialog, ensure that the Netlist Options checkboxes are all
disabled, except for Allow Ports To Name Nets. These choices modify the net names
based on your selection of checkboxes.
If you do not disable the other features; in a hierarchical project the Sheet Entries
would generate different nets from connecting schematics, resulting in warning
violations stating that there are Multiple Net Names, even if the net labels are the
same.
11. Click OK to accept the changes.
12. Go to Preferences » System » Navigation. In the Highlight Methods section, set the Far-
Close slider to mid-range. Click OK to save and close Preferences.

<!-- p.102 -->

## 9.4 Running the Compiler

13. Compile the WCTopping design using the menu Project » Validate PCB Project
WCTopping.PrjPcb or by right-clicking on the project in the Project panel and selecting
Validate PCB Project WCTopping.PrjPcb.
14. After you compile/validate, the Messages panel will appear. If no window appears, the
project has either passed the Electrical Rules Check (ERC), or there are only Warnings
and no Errors or Fatal Errors.
If you cannot find the Messages Panel, click the Panels button in the bottom right
corner of Altium Designer and select Messages from the popup menu.

### 9.4.1 Correcting Errors and Warnings

15. Upon compilation, you should see many Errors and Warnings in the Messages Panel.
Double-clicking a warning or error message in the Messages Panel will navigate to the
location where the warning or error occurs. It will display the affected elements in the
Details section of the Messages panel.
16. Sort the listings in the Message panel to group the Warnings and Errors by clicking the
Class column header until the Errors are brought to the top of the list.
17. You should see 3 “Net GPIOXX has only one pin” Errors in the Messages Panel as
shown in Figure 119 below.
18. Double-clicking on each of these 3 errors (“Net <GPIO##> has only one pin) will
highlight the affected pins associated to that error. In this case, it’s Pin 11, Pin 15 and Pin
13 of the J4 component.

*Figure 119. Net <name> only has one Pin error in the Messages panel*
19. For suppressing warning and errors, we will assign a No ERC directive as follows:
a) Right-click on the error in the Messages panel called
Net GPIO17 has only one pin (Pin J4-11)
b) Select Place Specific No ERC for this Violation… from the menu as shown in Figure
120.

<!-- p.103 -->

*Figure 120. Place No ERC Directive directly from the Messages panel*
c) The appropriate schematic will open and the No ERC directive will be on your cursor.
Place the directive at the end of the wire for that pin (GPIO17).
d) Continue to add Specific No ERC directives to the
2nd & 3rd errors as shown in Figure 121 below.

*Figure 121. Placed No ERC directives*
20. Compile the project once more using Project » Validate PCB Project WCTopping.PrjPcb.
21. Verify the list of messages no longer reports the “Net <GPIO##> has only one pin
(Pin J4-##)” errors.
22. Open the Messages panel notice that there are still other warnings that need to be
addressed.
NOTE: Placing a “No Specific ERC” will mask the Error or Warning associated with
that object. This directive should only be used if you want to purposely disregard that
Error or Warning (e.g. pin not connected or being used)

It is best practice to resolve the Warning or Error correctly, instead of placing a No
Specific ERC directive. Be cautious when using them.
23. The next group of warnings Net <Net ##> has no driving source occurs when an
input of an IC is connected to a passive component as shown in Figure 122 below.
24. Open the Project Options using the Project » Project Options menu.

<!-- p.104 -->

*Figure 122. Input of an IC with no driving source*
In the Error Reporting tab find the Violations Associated with Nets section
a) Locate the Nets with no driving source error listing.
b) Set this to No Report in the Report Mode column.
c) Press the OK button to exit the dialog.
25. Re-Run the compiler to verify there are no more Nets with no driving source Warnings.
26. To resolve the next set of warnings for “SPI_xxxx contains IO Pin and Output
Port”, open the Project Options again using the Project » Project Options menu.
a) In the Connection Matrix tab; locate the IO Pin to Output Port square and click the square
until it is green. This will be set to No Report.
b) Click the OK button to exit the dialog. Re-run the compiler to verify there is only 2
Warnings remaining.
27. Finally, to resolve the final 2 warnings for “Nets Element[x]:RELAY has multiple
names”, place a no ERC directive on the bus with the RELAY[1..2] port on it located in
the Relay_IO.SchDoc as shown in Figure 123 below.

*Figure 123. Placing a no ERC on the RELAY [1..2] Bus*

This violation occurs when a net in the design has been detected to have multiple
names associated with it. This could be by intention, e.g. connecting two different
pages in a hierarchical design or it could be an indication for a short circuit.

<!-- p.105 -->
28. Re-run the compiler by going to Project » Validate PCB Project WCTopping.PrjPcb.
There should not be any Errors or Warnings, indicating a clean compile as shown in Figure
124 below.

*Figure 124. Messages panel with no errors or warnings*
29. Save your work with File » Save All.

<!-- p.106 -->

## 9.5 Dynamic Compiler

As mentioned at the start of this module, we have the option to enable Dynamic Compiling. The
design connectivity model is incrementally updated after each user operation. You do not need to
manually compile the project to see the contents of the Navigator panel, run the BOM, perform an
ECO, etc.

### 9.5.1 Enabling the Dynamic Compiler

30. To enable the Dynamic Compiler, go into   Preferences » System » General and click
the Advanced… button as shown in Figure 125 below.

*Figure 125. Dynamic Compiling settings*
31. With the Advanced Settings dialog open, use the search bar at the top of the window, and
search for “Dynamic” as shown in Figure 126.

<!-- p.107 -->
32. Enable the Schematic.Dynamic.Compiler.Navigator.Autorefresh option to enable the
Dynamic Compiler as shown in Figure 126 below.

*Figure 126. Enabling the Dynamic Compiler in Advanced Settings*
For the Dynamic Compiler to take effect, Altium Designer must be closed and re-
launched. Ensure that you save any important documents before closing the
application.
33. Close the Advanced Settings dialog box, and click OK to close the Preferences.
34. Close Altium Designer completely, and re-launch the Application. This is necessary for the
Dynamic Compiler to take effect.
35. When Altium Designer has re-opened, the WCTopping.PrjPcb should still be present in
the projects panel. If you closed the project, it can be re-opened by going to File » Recent
Projects and the WCTopping.PrjPcb project for this exercise should be the 1st option in
the pop-up menu.
36. Open the Processor_Interface.SchDoc.
37. Expand the Components sub-folder, as well as the Capacitors sub-folder from the Projects
panel as shown in Figure 127. You will see there is 17 components with the “C” designator.

<!-- p.108 -->

*Figure 127. 17 Capacitor components in the design*
38. Select and Copy (CTRL+C) C6 from the Processor_Interface.SchDoc and paste
(CTRL+V) a new capacitor component beside it as shown in Figure 128 below.
39. You will then notice that the Components list in the Projects panel will automatically be
updated, and will now show 18 components with the “C” designator. This automatic updating
also updates all nets and sheet connectivity for the entire project when Dynamic Compiling is
enabled.

*Figure 128. Dynamic Compiler automatically updating the Components folder after adding a Capacitor*
40. Close the Project and click NO to save any changes when prompted.
