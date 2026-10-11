# AD20 Essentials - Module 11: Transfer to PCB

> Source: `ad20-essentials-exercises.pdf` (same folder), PDF pages 118-125 (printed page = PDF page; `<!-- p.N -->` marks page starts). Text only: figures are not extracted, only their captions. Altium Designer 20 UI; menu and panel names can differ slightly in newer versions.

<!-- p.118 -->

## 11.1 Purpose

In this exercise, you will be introduced to transferring the design from schematic to
PCB.  An additional part of this exercise is the placement, configuration, and transfer
of directives from the schematic to the PCB.
Using a comparison engine, Altium Designer creates an Engineering Change Order (ECO). This
is used to synchronize the schematic to PCB, as well as update the relevant changes from the
PCB back to the schematic. This bi-directional synchronization guarantees a high level of design
integrity and helps to ensure the PCB and schematics remain synchronized. If any items fail
during the ECO Execution, you should locate and correct the errors before completing the
transfer.

## 11.2 Preparation

1. Close the current WCTopping.PrjPcb project.
2. Open the WCTopping.PrjPcb project located in the
AD20 Essentials Exercises\ Module 11 - Transfer to PCB folder.

## 11.3 Before the Transfer

### 11.3.1 Footprint Validation

The Footprint Manager is used to ensure that all of the components in your schematic
documents, have an associated footprint. This will prevent errors should as “Footprint Not
Found” when pushing your design to the PCB.
3. From the Projects panel, open any schematic document.
4. Select the Tools » Footprint Manager… file menu.
5. Select all the components from the Component List with a right-click and Select All, or use
CTRL+A as shown in Figure 140. All of selected components are now listed in the View and
Edit Footprints list to the right side of the dialog.
6. Select all the footprints in the View and Edit Footprints list.
7. Click the Validate button below the View and Edit Footprints list.
8. After the Validation process is finished, review the Found In column for a listing of
Footprints Not Found. Review the PCB Library column to see the library source for
that footprint.
If you had not installed the WCT.IntLib library, you will see Footprints Not
Found for components that originated from that library. In that case, it will need to be
installed in the Components panel. A connection to the Altium Content Vault is also
needed to find footprints that originated from the Altium Content Vault.

<!-- p.119 -->

*Figure 140. Footprint Manager after footprint validation*
9. Close the Footprint Manager.
10. If all footprints are found, continue with 11.4 Transferring the Design. If not, please follow
the steps below.

#### 11.3.1.1 Connect to the Content Vault

11. This design uses components from the Altium Content Vault. Connection to the Altium
Content Vault is required to load the footprint data into the design. If you’re not signed in,
we will need to connect to the Altium Content Vault.
a) Open the Sign in dialog in the upper right corner as shown in Figure 141 below. If you are
already signed in, your name with your login credentials will already be there. If this is
the case, continue with step 11.3.1.1 c)

*Figure 141. AltiumLive sign in dialog*
b) Sign in to Altium Live with your Altium Live account.
c) Open the Preferences using the  icon, in the upper right corner of Altium Designer.
d) Under Data Management - Servers. Expand the Known Server section if necessary.
e) Check the Automatically connect Altium Content Vault checkbox. Ensure you’re
connected to the Altium Content Vault as shown in Figure 142 and click OK to exit the
Preferences.

<!-- p.120 -->

*Figure 142. Altium Content Vault connection*

#### 11.3.1.2 Install the WCT.IntLib library

12. If you have not installed the WCT.IntLib library, please return to Exercise 5.3.2 Adding an
Integrated Library for instructions to install this library. Access to this library is necessary to
properly complete this exercise.
13. Reopen the Footprint Manager under the Tools menu and validate that all footprints can be
found with a connection to the Altium Content Vault and the WCT.IntLib installed from the
Components Panel. Close the Footprint Manager.

<!-- p.121 -->

## 11.4 Transferring the Design

### 11.4.1 The Initial Transfer

14. Right-click the project name in the Projects panel and select Add New to Project » PCB.
15. Save the PCB and name it WCTopping.PcbDoc
16. From within a schematic, click on Design » Update PCB Document WCTopping.PcbDoc .
17. Click the Execute Changes button in the lower left of the dialog, as shown in Figure 143
below.

*Figure 143. Engineering Change Order dialog*
18. Enable the Only Show Errors checkbox to check for any errors.
19. Close the Engineering Change Order dialog.

### 11.4.2 Cross Select Mode

20. Right-click on the WCTopping.PcbDoc tab in the Documents Bar and select Split Vertical.
21. Select the Relay_IO.SchDoc tab in the Documents Bar so that you see that particular
schematic, along with the PCB on the other side as shown in Figure 144 below.

*Figure 144. Split Vertical view with selected components in Cross Select mode*
22. Check to see if cross selection mode is enabled in the schematic by going to Tools »
Cross Select Mode. Ensure this option is enabled and highlighted as shown in Figure 145
below.

<!-- p.122 -->

*Figure 145. Cross-Select mode enabled*
23. Group-select the following components within the Relay_IO.SchDoc in the following order
by holding down the Shift key and selecting components: RL1, D1, Q1B, DI1, RLY1, RLY2.
a) Right-click on the WCTopping.PcbDoc tab in the Documents Bar and select Merge All
to condense the tiling.
b) Under the Tools menu, select Component Placement » Reposition Selected
Components.
c) Click in the PCB workspace to place the component on your cursor. With each
subsequent click, the next component will snap onto your cursor based on the order
selected in the schematic.

### 11.4.3 Assigning Directives

24. If not already open, open the Processor_Interface.SchDoc and make it your active
document.
25. Replace the net label GPIO2 and the GPIO3 net labels with CLK_P and CLK_N
Right-click the Directives icon in the Active Bar and select Differential Pair, as shown in

26. Figure 146 below. This can also be done from the Place » Directives menu.
27. With the Differential Pair directive on your cursor, hit the Tab key to access its Properties.

*Figure 146. Placing a Differential Pair directive in the Schematic*
a) In the Properties pane, ensure the value for Label is DIFFPAIR as shown in

b) Figure 146 above.
c) Click on the pause symbol  in the center of the Schematic to continue the placement.
d) Place this directive on the CLK_P and CLK_N wires as shown in Figure 147.

<!-- p.123 -->
e) Right-click to exit the command.

*Figure 147. Directives placed in the schematicUse the command Place » Directives » Parameter Set.*
a) With the directive on your cursor, press the Tab key.
b) In the Properties pane, ensure the value for Label is PCB Rule
c) Under the Parameters pane, click Add... » Rule, as shown in Figure 148.

*Figure 148. Adding PCB rule directive from the schematic*

<!-- p.124 -->
d) Select the Width Constraint rule from within the Routing section.
e) Press the OK button
f) In the upper section set:
i) Min Width to 30mil
ii) Preferred Width to 50mil
iii) Max Width to 100mil.
iv) Press the OK button and the Pause symbol to continue the placement of the PCB
Layout Directive.
g) Place the PCB Layout Directive on both the 3V3 and 5V wires extending from the top of
the J4 component as shown in Figure 147.
h) Right-click to exit the command.
29. Select Design » Update PCB Document WCTopping.PcbDoc from the file menu.
a) The Design Rules are listed in the Engineering Change Order.
b) Click Execute Changes.
c) Close the Engineering Change Order.

30. With the PCB document active, open the PCB panel from the Panels button.
31. Click the drop-down menu to select Differential Pairs Editor as shown in Figure 149 below.
32. Then, click on <All Differential Pairs> to see all of the Differential Pairs in the design. You
should see the CLK Differential Pair that you added from the schematic directive.

*Figure 149. Differential Pair Editor in the PCB panel*
33. Open the PCB Design Rules and Constraints Editor with Design » Rules… and check to
see that the PCB Rule directive is transferred to the PCB as shown in Figure 150 below.

<!-- p.125 -->

*Figure 150. Design Rules showing the new Width rule that was added from the Schematic*
34. Save all documents and close the project.
