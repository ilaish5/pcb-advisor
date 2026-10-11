# AD20 Essentials - Module 8: Schematic Graphics

> Source: `ad20-essentials-exercises.pdf` (same folder), PDF pages 89-97 (printed page = PDF page; `<!-- p.N -->` marks page starts). Text only: figures are not extracted, only their captions. Altium Designer 20 UI; menu and panel names can differ slightly in newer versions.

<!-- p.89 -->

## 8.1 Purpose

In this exercise you will add text and graphics to the schematics to provide
documentation and organization. You will also number schematic sheets and print
them to PDF using the SmartPDF Wizard.

## 8.2 Preparation

1. Close the current WCTopping.PrjPcb project.
2. Open the WCTopping.PrjPcb project from the
AD20 Essentials Exercises\ Module 8 - Schematic Graphics folder.

## 8.3 CAN Interface Schematic

### 8.3.1 Text String

3. Open the CAN_Interface.SchDoc from the Projects panel.
4. Place a text string by selecting Place » Text String.
5. While in the middle of string placement, press the Tab key to enter the string’s properties.
6. Enter the text 3.3V Logic Levels, change the size of the font size to 16 by typing in 16,
as shown in Figure 97 below and press Enter to continue the text placement.

*Figure 97. Font dialog in the Properties panel*
7. Place the string on top of UC1 as shown in Figure 98.
8. With the place string command still active, we will place another text string.
9. Press Tab to enter the String’s properties.
10. Enter the text 5V Logic Levels.
11. Change the size of the font to 22.

<!-- p.90 -->
12. Press the Enter to continue the text placement
13. Place the 5V Logic Levels string on top of UC2 as shown in Figure 98 below.

*Figure 98. Placing a Text string*
14. Double-click on the 5V Logic Levels string to open the Properties panel.
15. In the Properties pane, decrease the size of the font size to 16 to match the other string.

### 8.3.2 Round Rectangle

16. Place a Round Rectangle by selecting Place » Drawing Tools » Round Rectangle  or use
the Active Bar.
17. Left-click to place the top left corner of the Round Rectangle similar to what is shown in
Figure 99 below.
18. Move the mouse down and to the right.
19. Left-click again to place the lower right corner of the Round Rectangle. Right click to escape
the command.

*Figure 99. Placing a Round Rectangle*

<!-- p.91 -->
20. The Round Rectangle will appear in front of the schematic objects. Select Edit » Move »
Send to Back as shown in Figure 100 below.

*Figure 100. Move » Send to Back menu*
21. With the Send to Back command active, left-click on the Round Rectangle with the
crosshair cursor to send it behind the other objects. Right click to escape the command.
22. The result should look similar to Figure 101 below.

*Figure 101. Round Rectangle moved to the Front*

<!-- p.92 -->
23. Using the same steps, place another Round Rectangle for the right part of the schematic
similar to Figure 102 below.

*Figure 102. Placing a second Round Rectangle*
24. With both Round Rectangles selected, open the Properties panel.
25. Select Smallest for the Border width.
26. Click on Fill Color field and set the fill color to light blue as shown in Figure 103 below.

*Figure 103. Select Light Blue for the Fill Color*

<!-- p.93 -->
27. Click on the Border Color field and set the border color to dark blue as shown in Figure 104
below.

*Figure 104. Select Dark Blue for the Border Color*
28. Set the Corner Y radius to 200mil.
29. Set the Corner X radius to 200mil.
30. Once you’ve changed the properties, the schematic should look similar to Figure 105 below.

*Figure 105. CAN_Interface schematic with text and rectangle placement*

<!-- p.94 -->

## 8.4 Number Schematic Sheets

31. Select Tools » Annotation » Number Schematic Sheets as shown in Figure 106 below.

*Figure 106. Sheet Annotation dialog*
32. Click Auto Sheet Number to assign numbers to the sheets in the order of the list you see
in the table as shown in Figure 107 below.

*Figure 107. Sheet Annotation dialog with Sheet Numbering*
33. Select Processor_Interface.Schdoc.
34. Move Processor_Interface.Schdoc up to the top by pressing the Move Up button.
Only the order has changed. Left-click Auto Sheet Number to renumber everything as
shown in Figure 108 below.

*Figure 108. Sheet Annotation dialog after Sheet Numbering*

<!-- p.95 -->
35. Click Update Sheet Count to fill in the SheetTotal column as shown in Figure 109 below.

*Figure 109. Annotation dialog after updating the sheet count*
36. Click the Auto Document Number drop-down as shown in Figure 110 below.
37. Add prefix DOC_.

*Figure 110. Annotation dialog for Auto Document Number options*
38. Click Auto Document Number again as shown in Figure 111 below.
*Figure 111. Annotation dialog for Auto Document Number*
39. Click OK to close the Sheet Numbering window.

<!-- p.96 -->
40. The title block in each schematic will now show the proper sheet number according to how it
was numbered as shown in Figure 112 below.

*Figure 112. Title Block with Sheet number*

## 8.5 Smart PDF

41. Select File » Smart PDF to open the Smart PDF wizard.
42. Click Next to begin the wizard.
43. Select Current Project, enter the name of the output file and the location on where you
want to save the PDF as shown in Figure 113 below. Click Next.

Figure 113 Choose SmartPDF Export target
44. All project files will be selected by default on the next page. Press the Next button with all
files selected.
45. Ensure that is unchecked. The Bill of Materials (BOM) generation is
explored fully in a later exercise. Click Next.
46. Leave the PCB Printout Settings options as is, and click Next.
47. Leave the Additional PDF Settings options as is, as shown in Figure 114 below.
48. Click Next to continue the wizard.

<!-- p.97 -->

*Figure 114. SmartPDF settings*
49. Because we have a flat design, structure settings are not relevant. Leave
unchecked and click next.
50. Ensure that  is enabled and click Finish.
51. Review the pages of the PDF by expanding the different sections under the bookmarks tab
as shown in Figure 115 below. You can now select components, nets, and ports from
Bookmarks.

*Figure 115. SmartPDF with generated schematics and bookmarks*
