# AD20 Essentials - Module 28: Component Creation

> Source: `ad20-essentials-exercises.pdf` (same folder), PDF pages 277-281 (printed page = PDF page; `<!-- p.N -->` marks page starts). Text only: figures are not extracted, only their captions. Altium Designer 20 UI; menu and panel names can differ slightly in newer versions.

<!-- p.277 -->

## 28.1 Purpose

In this exercise, students will learn to link the Crystal symbol with its footprint, both
created in earlier exercises. A linked symbol and footprint is what we generally refer to
as a unified component.

## 28.2 Linking Footprint to the Symbol

1. Open your My_Symbols.SchLib created earlier from the My_Components folder.
2. Open the Crystal symbol from the SCH Library panel. If you do not see the SCH Library
panel, go to View » Panels » SCH Library.
3. In the Model pane at the bottom, click Add Footprint as shown in Figure 368.

*Figure 368. The Model pane in the Symbol Editor Workspace*
4. The PCB Model dialog will open. Click Browse… and the Browse Libraries dialog will open
as shown in Figure 369. Ensure to set My_Footprints.PcbLib as the active library. If not,
click on the  button and install My_Footprints.PcbLib.
5. Select the footprint HC49SMD.

<!-- p.278 -->

*Figure 369. Link the HC49SMD footprint with the crystal symbol*
In the PCB Model dialog, there are 3 PCB Library options (Any, Library name and
Library path). If the Any option is chosen, it will search for the footprint that has
matching name in all currently available libraries. Thus, it is recommended for either
the library name or library path option to be used when working with passives or
generic footprint names which may be duplicated in multiple installed PCB libraries.
6. Close the dialogs Browse Libraries and PCB Model with OK
7. Note the crystal footprint preview in the Symbol Editor and shown in Figure 370. The crystal
footprint is now linked to the symbol.

<!-- p.279 -->

*Figure 370. Symbol Editor with linked footprint*
8. Save the schematic library by going to File » Save.
9. Close all documents.

## 28.3 Using Linked Component

Now we will test our linked component by adding it to a schematic, and then synchronize it with
the PCB.
8. Create a new project by going to File » New » Project. Give it a name of your choice and
click Create.
9. Right-click on newly created project from the Projects panel and add a new Schematic and a
new PCB document.
10. Save the Project and its files by going to File » Save All.
11. Open the Components panel with the My_Symbols.SchLib active. You should see a
preview for both the symbol and footprint of the crystal as shown in Figure 371

<!-- p.280 -->

*Figure 371. Components panel showing symbol and footprint for crystal component*
12. With the schematic document active, right-click the Crystal from the Components panel and
place it into the schematic. Right-click to end the component placement.
13. Annotate the component by going to Tools » Annotation » Annotate Schematic Quietly.
Click Yes when prompted.
14. Update the PCB by going to Design » Update PCB Document. Disable the Add Rooms
checkbox and click Execute Changes in the ECO. Click Close to close the ECO dialog.
15. Now the crystal footprint is visible in the PCB as shown in Figure 372.

<!-- p.281 -->

*Figure 372. 2D Crystal in PCB Editor*
15.  Change to 3D view by hitting the 3 key and rotate the view by holding Shift and the right
mouse button see Figure 373.

*Figure 373. 3D Crystal in PCB Editor*
16. Close all files without saving, including the project in the Projects panel.
