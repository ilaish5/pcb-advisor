# AD20 Essentials - Module 29: Integrated Library

> Source: `ad20-essentials-exercises.pdf` (same folder), PDF pages 282-287 (printed page = PDF page; `<!-- p.N -->` marks page starts). Text only: figures are not extracted, only their captions. Altium Designer 20 UI; menu and panel names can differ slightly in newer versions.

<!-- p.282 -->

## 29.1 Purpose

In this exercise, you will recreate the WCT Integrated Library by creating a library
package project.

## 29.2 Preparation

1. Close all open projects and documents. For this exercise, we will be using files located in the
AD20 Essentials Exercises\ Module 29 - Integrated Library Project
folder.

## 29.3 Create Integrated Library Project

2. Create an Integrated Library Package Project using the menus:
File » New » Library » Integrated Library as in Figure 374. A new Integrated Library
Project is created and added to the Projects panel.

*Figure 374. Create project dialog*

<!-- p.283 -->
3. Add the WCT.SchLib and WCT.PcbLib libraries
a) Right-clicking on the WCT.LibPkg from the Projects panel, and Add Existing to
Project… .
b) Browse to the Module 29 - Integrated Library Project training exercise
folder to find both the WCT.SchLib and WCT.PcbLib libraries.
Be sure that the drop-down filter in the bottom right is set to All files.
It is possible to select both using Ctrl + Left-click.
4. Save the project and give it a name of WCT. It should look like Figure 375.

*Figure 375. WCT.LibPkg Project*
5. Compile the project by right-clicking the WCT.LibPkg from the Projects panel and Compile
Integrated Library WCT.LibPkg.
6. The Messages panel will automatically appear if there are any errors. In this case, there is
an intentional error named:
Cap10uf25V_0603: Could not find port ‘3’ on model ‘0603C_L’ for pin ‘3’. (Figure 376).

*Figure 376. Error highlighted in Messages panel*
7. Double-click the error in the Messages panel to jump to the violating symbol. From the
Properties panel, notice that the Pins tab shows that the symbol has Pin 1 and Pin 3, as
shown in Figure 377.
If you have closed the Messages panel, it can be reopened from View » Panels »
Messages. To open the Properties panel, use the menus View » Panels »
Properties and select that symbol.

<!-- p.284 -->

*Figure 377. Pin information of the schematic symbol in the SCH library*
8. From the Projects panel, double-click to open the WCT.PcbLib.
9. From the PCB Library panel, select the 0603C_L footprint.
10. Notice that the footprint has Pad 1 and Pad 2 which do not match the schematic Pin 1
and Pin 3 of Cap10uF_25V_0603 from the schematic library.
11. Set the WCT.SchLib as the active document and Cap10uF_25V_0603 as the active
symbol.
12. Select Pin 3 in the workspace (pin on the right-side) and change the value for the
Designator and Name to 2 as shown in Figure 378, so that it matches the pads of the
0603C_L footprint.

*Figure 378. Pin properties*
13. Save the WCT.SchLib.
14. Compile the WCT.LibPkg again by right-clicking on the project name in the Projects panel
and select Compile Integrated Library WCT.LibPkg.
If there are no errors in the library, the Messages panel will not automatically appear .
The messages panel can be opened and reviewed from View » Panels » Messages.

15. Notice that the error Could Not Find Port error has been resolved in the Messages
panel but, there are still some warnings for Could Not Find Footprint, as shown in
*Figure 379. *

<!-- p.285 -->
16. Extra footprints have been linked to the symbols shown in these warnings, but the footprints
were not included in the PCB library.

*Figure 379. Removing extra models from the Models area of the Schematic Library Editor*
17. Double-click each Inductor: Could not find <Name> warning in the Messages
panel to jump to the symbol with the invalid footprint link as shown in Figure 380.
18. Remove the footprint model that is causing the Warnings, by pressing the Remove button. In
this case, it’s the INDCxxxx and 0603 footprint models.

*Figure 380. Remove links for footprints from SCH Library*
19. Save the schematic library.
20. Compile the project again by selecting Project » Compile Integrated Library WCT.LibPkg.
21. Open the Messages panel, and you’ll notice the errors & warnings associated with that
component are no longer present.
22. Verify the Integrated Library has been generated in the Integrated
Libraries\Project Outputs for WCT folder, or wherever the WCT.LibPkg was
saved.
a) Right-click on the project name in the Project panel and select Explore to browse the
folder.
b) Navigate to the Project Outputs subfolder to verify that it contains the WCT.IntLib file.

<!-- p.286 -->

## 29.4 Using the New Library

When opening an Integrated Library, a prompt to Extract Sources or Install Library will open.
23. Close all projects and files in the Projects panel.
a) Select File » Open.
b) Navigate to the Project Outputs for WCT folder.
c) Select the WCT.IntLib file and click Open. The popup window shown in Figure 381 will
appear.
d) Select Install Library. Note: The library will already have been installed as it gets added
during the compile process.

*Figure 381. Opening the WCTopping.IntLib*

If you select the Extract Sources button when you open an integrated library, Altium
will create a new library project and decompile the file into the SchLib and PcbLib files,
allowing you to edit the libraries.
You can then recompile these edited files to update the IntLib.

24. Open the Components panel and select the new library from the drop-down list. You will see
the symbol and footprint previews and these components would be ready to use.

