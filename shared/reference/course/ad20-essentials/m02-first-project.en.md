# AD20 Essentials - Module 2: It Starts with a Project

> Source: `ad20-essentials-exercises.pdf` (same folder), PDF pages 29-33 (printed page = PDF page; `<!-- p.N -->` marks page starts). Text only: figures are not extracted, only their captions. Altium Designer 20 UI; menu and panel names can differ slightly in newer versions.

<!-- p.29 -->

## 2.1 Purpose

In this exercise, you will learn to create a new project, add new and existing files to the
project and save the project. You will then package the project for archiving or to
transfer to external parties.
A project file contains references to its design documents such as schematic and PCB
documents. It also stores project-specific options and parameters defined. In this exercise, we
will be creating a new PCB project.

## 2.2 Create a New Project

### 2.2.1 Project Wizard

1. Close all open projects in the Project panel.
2. Go to File » New » Project... to launch the Create Project dialog  as shown in Figure 22
below.

*Figure 22. Project Wizard*
3. Select Local Projects under the Locations area as shown in Figure 22 above.
4. In the Project Type area, under PCB, select <Default> to create a blank project.
5. Enter a project name of MyFirstProject.
6. Click on the Triple Dot button in the Folder area (as shown in Figure 22) and select your
Desktop so this project will be easy to find later on.

<!-- p.30 -->
7. Expand the Parameters area and add a project parameter. This parameter will be available
throughout all of the schematic documents of our project later on. Use the same name and
value as shown in Figure 22 on the previous page.
Projects can be directly saved to a Version Control repository if VCS is chosen under
Locations.
8. Click the Create button to create the new project. Go to your Desktop to confirm that a
MyFirstProject folder has been created on your desktop.
9. In Altium Designer, notice there is now a project called MyFirstProject.PrjPcb in the
Projects panel as shown in Figure 23 below.

*Figure 23. Projects panel with the new project you just created*

### 2.2.2 Adding New Documents

10. Right-click on MyFirstProject.PrjPcb in the Projects panel.
a) Select Add New to Project and choose Schematic to add a new schematic to the
Project as shown in Figure 24. The default name for the schematic is Sheet1.SchDoc
b) Repeat this operation to add a second schematic. The default name for the second
schematic is Sheet2.SchDoc.

<!-- p.31 -->

*Figure 24. Adding new Schematics to the Project*
11. Go to File » Save All. A dialog box will open, prompting you to save the new files you
created. Save the files in the default desktop folder MyFirstProject that you created
earlier:
- 1st schematic as Hello
- 2nd schematic as World
12. The Projects panel should now look like Figure 25 below.

*Figure 25. Project panel with new files names*

<!-- p.32 -->
13. We will navigate to the Desktop project folder directly by right-clicking on
MyFirstProject.PrjPcb in the Projects panel and clicking on Explore as shown in
Figure 26 below.

*Figure 26. Navigate to the File Explorer from the Projects Panel*
Add existing files to a project by right-clicking on the project name in the Projects
panel and clicking on Add Existing to Project. Files located outside the project’s
directory structure are displayed in the Projects panel with a linked icon .

### 2.2.3 Project Options

14. Go to the menu Project and select Project Options.
a) Select the Options tab.
b) Select the Parameters tab, and you’ll see the parameter you added during the project
creation.
c) Click OK. Go to File » Save All.

<!-- p.33 -->

## 2.3 Package a Project for Easy Transfer

15. We can use the Project Packager to generate an archive of the project and its documents:
a) Right-click the project from the Projects panel, and select the Project Packager.
b) Use the default settings and click next to progress through the Project Packager as
shown in Figure 27 below.
c) Click Finish when all the settings are defined.

*Figure 27. Project Packager*
16. In the Projects panel, right-click on MyFirstProject.PrjPcb and click Explore to see the
MyFirstProject.zip file added to the project folder (Figure 28 below). The Name and
Location of the ZIP file were defined in the Zip File Options page of the Project Packager.
The default ZIP name includes the project name with the date and time stamps.

*Figure 28. Navigate to the Packaged Project*
