# AD20 Essentials - Module 24: Draftsman

> Source: `ad20-essentials-exercises.pdf` (same folder), PDF pages 240-248 (printed page = PDF page; `<!-- p.N -->` marks page starts). Text only: figures are not extracted, only their captions. Altium Designer 20 UI; menu and panel names can differ slightly in newer versions.

<!-- p.240 -->

## 24.1 Purpose

In this exercise, students will learn to create a Draftsman document which can then be
used for board production drawings for fabrication and assembly. Students will learn to
place board views (assembly/fabrication/drill drawing), tables (drill table, layer stack
legend, BOM) and other graphical notes or objects to improve clarity.

## 24.2 Preparation

1. Close all open projects. For this exercise, we will be using the WCTopping.PrjPcb project
located in the Module 24 – Draftsman folder.
2. Open the WCTopping.PrjPcb project.
3. Open the WCTopping.PcbDoc and view it in 3D. In this exercise, we will learn to produce a
board production drawing of this PCB using Draftsman document.

## 24.3 Creating a Draftsman Document

### 24.3.1 Creating Draftsman From a Template

4. Open a new Draftsman document with the command File » New » Draftsman Document.
5. Select the Template Assy Drawing – Main views (rect. board 3x1). Ensure to point to the
WCTopping.PrjPcb and WCTopping.PcbDoc as shown in Figure 310. Click OK to
generate the Draftsman document based off the chosen Draftsman template.

*Figure 310. Create a new Draftsman document dialog*
6. Dock the Properties panel if it appears in the middle of the screen.

<!-- p.241 -->
7. The Draftsman document created will have multiple assembly views of the board, as pre-
defined in the template. Go to File » Save As and save the Draftsman document as
WCTopping - Assembly View.PCBDwf to the project folder.
8. Go to  Preferences. Expand the Draftsman branch and open the Templates page. The
path in this page currently points to the Altium Draftsman template folder by default. The
path could be changed to a company-standard template folder if required.
9. Close the Preferences without making any changes.

### 24.3.2 Creating Draftsman Without a Template

10. Open another new Draftsman document with the command File » New » Draftsman
Document. This time around, select [Default] as the template. Ensure to point to
WCTopping.PrjPcb and WCTopping.PcbDoc.
11. Click OK to generate an empty Draftsman document.
12. Go to File » Save As and save the Draftsman document as My Draftsman
WCTopping.PCBDwf.

## 24.4 Page Configuration

13. We will now define a sheet template for this Draftsman document. Open the Properties
panel and open the Page Options tab. Under the Formatting and Size pane, select
Template and from the Templates dropdown, select ANSI B Landscape as shown in
*Figure 311. *

*Figure 311. Changing the document template*
14. Click on the Parameters tab. In this tab, any parameters associated with the PCB, System
or Project will be listed. In the Parameters tab, locate the Parameter named
DocumentNumber.
15. Change its value to DOC1234 as shown in Figure 312.

<!-- p.242 -->

*Figure 312. Adding a document parameter to the Draftsman sheet*

<!-- p.243 -->

## 24.5 Assembly View

16. We will first place assembly views or also known as mechanical views on our Draftsman
document. Refer to Figure 313 for the following steps.
17. Go to Place » Board Assembly View. By default, the top-side view of the board will be
provided. Place this view in the middle of the document.
18. Right-click on the placed assembly view and click Copy. A crosshair will be present, where
you will need to select the view to Copy it Then, right-click on an empty space to the right of
the Assembly View and click Paste.
19. Double-click on the pasted assembly view to open its Properties panel. In the Properties
pane, change its View side to Right as shown in Figure 313.

*Figure 313. Assembly Views placed in the Draftsman document*
20. Repeat Steps 18 and 19 above twice to place more Assembly Views.
21. Change their View side to Left and Front, respectively to place Left and Front assembly
views onto the document. Move the views to the appropriate locations, as shown in Figure
314.

<!-- p.244 -->

*Figure 314. Multiple Assembly Views of the board*
22. Double-click on the Top Side assembly view to open its Properties panel. Check on Show
Silkscreen and Show SMD and Through-Hole pads as shown in Figure 315.

*Figure 315. Show Silkscreen, SMD pads and Through-Hole Pads from the Properties panel*

<!-- p.245 -->

## 24.6 Fabrication View

23. We would now like to add fabrication views on a new sheet. To add a new sheet to this
document, simply right-click anywhere on the document and click Add Sheet. Scroll down
to see the new sheet that was added. A Draftsman document can contain multiple sheets.
24. To place fabrication views, go to Place » Board Fabrication View. By default, the top layer
of the board will be provided. Place this view on the left half of the document. Use
25. Right-click on the placed fabrication view and click Copy. A crosshair will be present, where
you will need to select the view to Copy it. Then, right-click on an empty space to the right
of the fabrication view and click Paste.
26. Double-click on the pasted fabrication view to open its Properties panel. In the Properties
pane, change its Layer from Top Layer to Bottom Layer.
27. Use Figure 316 as a reference to how your sheet should look.

*Figure 316. Fabrication View and Layer configuration in the Properties panel.*

<!-- p.246 -->

## 24.7 Additional Views and Dimensions

Detail, isometric and section views of the board can also be placed in the Draftsman document.
Various dimensions can then be placed on any of these views.
28. Return to the first page of the Draftsman document containing the Assembly Views. Go to
Place » Additional Views » Board Isometric View and place the view on the bottom left
of the page. Use Figure 317 as a reference.
29. Currently, the components on the left of the board are too small and should be enlarged for
easier visibility.
a) We can place a detail view of this area by going to Place » Additional Views » Board
Detail View.
b) Left-click on any view to starting drawing a circle around the area which we wish to
enlarge.
c) Place this detail view in an empty area on the page. If required, it can also be scaled up
or down in its Properties panel as shown in Figure 317.

*Figure 317. View placement and properties*
30. Section views of the board can also be placed, for better board representation. Go to Place
» Additional views » Board Section View and move the cursor towards the top side
assembly view. Feel free to use Figure 318 as a placement guide.
a) Hit Spacebar to toggle between horizontal and vertical cut
b) Left-click to set the position of the cut line.
c) Then, move the cursor on either side of the cut line to set the view direction. Left -click
again to confirm the view direction.
d) Left-click again to place the section view in the desired location on the top left of the page
as shown in Figure 318.

<!-- p.247 -->

*Figure 318. Assembly Views with additional detail, isometric and section views*
31. We will now place linear dimensions on the top side assembly view by going to Place »
Linear Dimension.
32. Then, left-click on the horizontal and vertical edges of the board shown in Figure 318.
33. To change its units, double-click on the dimension and configure it in the Properties panel.

<!-- p.248 -->

## 24.8 Tables

34. We will add a third page to this document by right clicking anywhere on the document and
click Add Sheet.
35. Scroll down all the way to the newly created page.
36. On this third page, place the following objects with the default configuration. Use Figure 319
as a reference.
a) a Drill Drawing View Place » Additional Views » Drill Drawing View
b) a Drill Table Place » Drill Table
c) a Layer Stack Legend Place » Layer Stack Legend
d) a BOM Table Place » Bill of Materials

*Figure 319. Drill Drawing, Drill Table, Layer Stack and BOM placed on the sheet*

### 24.8.1 Optional

37. Feel free to add a fourth page to this document by right clicking anywhere on the document
and click Add Sheet.
38. Scroll down all the way to the newly created page.
39. On this fourth page, you can place additional objects with the default configuration like:
a) Board region
b) Board Realistic
40. Close and save all projects and documents.
