# AD20 Essentials - Module 25: PCB Fabrication Files

> Source: `ad20-essentials-exercises.pdf` (same folder), PDF pages 249-256 (printed page = PDF page; `<!-- p.N -->` marks page starts). Text only: figures are not extracted, only their captions. Altium Designer 20 UI; menu and panel names can differ slightly in newer versions.

<!-- p.249 -->

## 25.1 Purpose

In this exercise, students will learn to work with the Smart PDF as well as configure
and export a Bill of Materials (BOM). Additionally, an Output Job is added to the
project to manage outputs including documentation outputs, report outputs (BOM) and
fabrication outputs like Gerber, NC-Drill.

## 25.2 Preparation

1. Close all open projects. For this exercise, we will be using the WCTopping.PrjPcb project
located in the Module 25 - PCB Fabrication Files folder.
2. Open the WCTopping.PrjPcb project
3. Open any of the schematic document, such as Digital_IO.SchDoc.

## 25.3 Bill of Materials

4. To generate a Bill of Materials (BOM), we can go to Reports » Bill of Materials from the
schematic environment. The BOM dialog will appear as shown in Figure 320.

*Figure 320. Bill of Materials dialog window*
5. Currently, multiple components appear on a single row because they are grouped by  the
Comment and Footprint parameters as shown in the Columns tab of the Properties panel
on the right. This is what we consider the Grouped Columns pane. Click the Trash icon
next to the Comment and Footprint parameters and the BOM will have one component
per row.
6. To control which parameters are available for your Bill of Materials, you can enable or
disable the options under the Sources pane. If you hover over the icons under the Sources
tab, it will show you where the parameters originate from.
7. Component parameters can be added or removed from your Bill of Materials, by clicking on
the  icon in the Columns pane. Columns can also be re-arranged by dragging their
headers to the intended locations. This is all shown in Figure 321.

<!-- p.250 -->

*Figure 321. BOM with parameters from the PCB*
8. Under Export Options from the General tab, select Microsoft Excel Worksheet (*.xls) as
the file format as shown in Figure 322. Click Export to generate the report. Save the file to
your Desktop. Close the generated Excel file upon opening.

*Figure 322. BOM export options*
9. Click OK to save and close the BOM dialog.

<!-- p.251 -->

## 25.4 Output Job File

An Output Job file allows users to add, configure, and reuse a variety of output configurations. In
this exercise, you will define a single output job file containing all outputs we need for the
working project. The outputs will include schematic and PCB printouts, validation reports,
Gerbers, an NC Drill file report and a Pick & Place output.

### 25.4.1 Creating a New Output Job File

10. In the Projects panel, right-click on the project and go to Add New to Project » Output Job
File. A new Output Job file will be added to the project as shown in Figure 323.

*Figure 323. Output Job File added to the project*

### 25.4.2 Defining Outputs

#### 25.4.2.1 Documentation Outputs

11. In the Outputs pane, find the category for Documentation Outputs. Use Figure 324 as a
guide for the following steps.
12. Click [Add New Documentation Output] » PCB Prints » [PCB Document].
13. Click [Add New Documentation Output] » Schematic Prints » All SCH Documents.

<!-- p.252 -->

*Figure 324. Output Job output configuration*
14. Right-click on Schematic Prints output and click Page Setup…. Ensure that its Color Set
option is set to Color as shown in Figure 325. Click Close to close the dialog.

*Figure 325. Schematic Print Page Setup*
Defining the data source as the generic [SCH Document], [Project] or [PCB
Document] instead of the specific file name would allow the Output Job file to be re-
used in multiple projects as a Template.

#### 25.4.2.2 Assembly Outputs

15. Find the category for Assembly Outputs. The following steps will be similar to what was
done previously in Section 25.4.2.1 using Figure 324.
16. Click [Add New Assembly Output] » Assembly Drawings » [PCB Document].
17. Click [Add New Assembly Output] » Generates Pick and Place Files » [PCB
Document].

<!-- p.253 -->

#### 25.4.2.3 Fabrication Outputs

18. Find the category for Fabrication Outputs. The following steps will be similar to what was
done previously in Section 25.4.2.2 using Figure 324.
19. Click [Add New Fabrication Output] » NC Drill Files » [PCB Document].
20. Click [Add New Fabrication Output] » Drill Drawings » [PCB Document].
21. Click [Add New Fabrication Output] » Gerber Files » [PCB Document].
22. Double-click on the Gerber Files output to open its Gerber Setup dialog. Open the Layers
tab. Click on Plot Layers and choose to plot Used Layers as shown in Figure 326. Click
OK.

*Figure 326. Gerber Setup*

#### 25.4.2.4 Report Outputs

23. Find the category for Report Outputs.
24. Click [Add New Report Output] » Bill of Materials » [Project].
25. Double click on the Bill of Materials output to open its BOM dialog. Here you can
customize the grouping and desired columns as explored previously. Click OK  to close the
dialog.

#### 25.4.2.5 Validation Outputs

26. Find the category for Validation Outputs.
27. Click [Add New Validation Output] » Electrical Rules Check » [Project].
28. Click [Add New Validation Output] » Design Rules Check » [PCB Document].

<!-- p.254 -->

### 25.4.3 Defining Containers

#### 25.4.3.1 PDF Container

29. In the Output Containers section on the right side of the Output Job File, click on PDF to
select it as shown in Figure 327.
30. Then, click on the balloons in the Enabled column, corresponding to the outputs to map it to
the PDF container. Ensure to click in the order shown in Figure 327.

*Figure 327. Output Job File with outputs linked to PDF container*

#### 25.4.3.2 Folder Container

31. In the Output Containers pane, select Folder Structure.
32. Then, click on the balloons in the Enabled column, corresponding to the outputs to map it to
the Folder Structure container. Ensure to click in the order as shown in Figure 328.

*Figure 328. Output Job File with outputs linked to the Folder Structure Container*
33. Save the output job file by going to File » Save. Save it with the default name, Job1.Outjob.
34. The outputs have now been created, configured and mapped to their corresponding
containers. Next, we will generate these outputs.

<!-- p.255 -->

### 25.4.4 Generating the Outputs

#### 25.4.4.1 Generating the PDF

35. To create the PDF file of all seven outputs, highlight the PDF container and click on the
Generate Content link as shown in Figure 329.
36. The PDF file will pop up after processing and will be saved to the Project Outputs for
WCTopping project sub-folder.

*Figure 329. Generating the PDF outputs*

*Figure 330. Generated PDF based on our outputs from the Output Job*

#### 25.4.4.2 Generating the Folder Structure

37. Click on the Generate content link in the Folder Structure section. Individual outputs will
appear as separate tabs in the Altium Design workspace and as folders under the
Generated section of the Projects panel as shown in Figure 331.
38. These files will also be saved to the Project Outputs for WCTopping project sub-
folder.

<!-- p.256 -->
If you wanted to save these Generated files in another folder, choosing the Output
Container and clicking “Change” would allow you to specify the Output Folder.
39. Save and close all files.

*Figure 331. Folder Structure outputs generated from the Output Job*
