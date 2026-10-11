# AD20 Essentials - Module 19: PCB Design Rules

> Source: `ad20-essentials-exercises.pdf` (same folder), PDF pages 186-197 (printed page = PDF page; `<!-- p.N -->` marks page starts). Text only: figures are not extracted, only their captions. Altium Designer 20 UI; menu and panel names can differ slightly in newer versions.

<!-- p.186 -->

## 19.1 Purpose

In this exercise, students will learn various methods to create PCB design rules. Rule
priorities will also be defined, to ensure proper rule application on objects targeted by
multiple rules.
Design rules are used to ensure the PCB layout meets the specified design requirements and
highlights violations when items fall outside of their defined constraints. These rules cover various
aspects of the design and collectively form an “instruction set” for the PCB editor to follow. Many of
them can also be monitored in real-time by the online Design Rule Checker (DRC).

## 19.2 Preparation

1. Close all open projects. For this exercise, we will be using the WCTopping.PrjPcb project
located in the Module 19 - PCB Rules and Panels folder.
2. Open WCTopping.PrjPcb from the Module 19 - PCB Rules and Panels folder.
3. Open the Rules.PcbDoc file from the Projects panel.

## 19.3 Basic Design Rule

### 19.3.1 PCB Rules and Constraints Editor

4. Go to Design » Import Changes From WCTopping.PrjPcb and verify that there are no
differences reported. Close the Comparator Results dialog.
5. Go to Design » Rules (D » R) and the PCB Rules and Constraints Editor dialog will open.
6. The tree on the left lists the rule categories. Expand the Electrical rule category. Notice that
there are 6 rule types within this category. This can be seen in Figure 232.
7. Expand the Clearance rule type to display all clearance rules currently defined. Notice that
there is only a single, default rule called Clearance. Select it to view its rule definition on the
right of the window as shown in Figure 232.

<!-- p.187 -->

*Figure 232. PCB Rules and Constraints Editor*
8. We will now create a new rule which will target the 12V power net. Right-click on the
Clearance rule type, just underneath Electrical and click New Rule. You should notice a new
rule added with a default name given as Clearance_1.
9. Select the new rule Clearance_1 on the left pane of the window to open the rule and
assign each field according to Figure 233 below.
a) Set the Name field to PowerNets.
b) Set the first query (Where the First Objects Matches) to Net, and then 12V.
c) Set the Minimum Clearance constraint to 15mil.

*Figure 233. PowerNets clearance rule definition*

### 19.3.2 Rule Priorities

10. Now that we have multiple clearance rules, let’s ensure that their priorities are set correctly.
Click on the Priorities… button on the bottom left of the PCB Rules and Constraints Editor
window to open the Edit Rule Priorities window.

<!-- p.188 -->
11. Ensure that the newly added rule’s priority is number 1 as shown in Figure 234 below. If it’s
not, select that rule and click Increase Priority.
12. Click Close and then OK to accept changes and close all dialogs.

*Figure 234. Rule Priorities window*
To simplify the process of defining and managing rules, the idea is to first define the
general rules that cover broad requirements of the PCB. Then, override these rules
with specific rules in specific situations. Thus, it is a general practice to make the
generic or “All-All” rule the least prioritized so that objects are applied with their
specific rules.

<!-- p.189 -->

## 19.4 Design Rule Using Net Classes

13. Instead of scoping objects of a single net in Design Rules, we can target objects from
multiple nets by grouping them in Net Classes. We will now add a Net Class to the 12V net,
and assign a Width rule to this Net Class. Open Power Supply.SchDoc.
14. Go to Place » Directives » Parameter Set. Your mouse cursor will contain the Parameter
Set attached to it.
15. Before placing it, hit the Tab key to open the Properties panel.
16. Assign the fields according to the following steps, while also referring to the images in
Figure 235, Figure 236 and Figure 237.
a) Change the Label value to PowerNets

*Figure 235. Change the Label value to "PowerNets"*
b) Under the Parameters pane, click Add… and add a Net Class.

*Figure 236. Adding a NetClass through the Parameters pane in the Properties panel*

<!-- p.190 -->
c) Name the new NetClass as PowerNets.

*Figure 237. Changing the NetClass value to "PowerNets"*
17. Click on the pause symbol  to continue and place it on the 12V power line as shown in
*Figure 238. Once placed, right-click to end the placement command.*

*Figure 238. Placing the PowerNets directive*
18. Perform a Design » Update PCB Document Rules.PcbDoc.
19. Click Execute Changes and Close as shown in Figure 239. The focus will automatically
change to the PCB file.

*Figure 239. Engineering Change Order (ECO) showing the addition of the PowerNets NetClass*

If you add a new net class directly from the PCB, they will not be present on the
schematic. When running the Engineering Change Order, you may be prompted of a
possible removal of the net class. Simply untick the box to prevent the removal within,
or edit the Project » Project Options » ECO generation tab to prevent any removal of
net classes.

<!-- p.191 -->
20. We will now add a Width rule for the PowerNets Net Class that we just added.
Go to Design » Rules, then navigate to the Routing » Width design rule.
21. Add a new Width rule and assign the name and constraints according to Figure 240.

*Figure 240. PowerNets Width Rule definition*
22. Once again, ensure that the newly created PowerNets_Width rule is of the highest priority as
described in Section 19.3.2 Rule Priorities.
23. Click OK to save and close PCB Rules and Constraints Editor.

<!-- p.192 -->

## 19.5 Design Rule Using Custom Queries

### 19.5.1 Create Queries Using Find Similar Objects

We will now create a design rule which targets components of a specific footprint. We can build a
custom query for this purpose, using Find Similar Objects.
24. While in the Rules.PcbDoc, right-click on component RLY4 and click on Find Similar
Objects.
25. Ensure that Object Kind and Footprint are set to Same, and the Create Expression
checkbox is ticked as shown in Figure 241. Then, click OK.

*Figure 241. Find Similar Objects dialog*
26. Open the PCB Filter panel by going to Panels button in the lower right corner  and select
PCB Filter or View » Panels » PCB Filter. Feel free to dock this panel wherever you wish.
27. Within this panel, the query created by running Find Similar Objects will be shown in the
Filter pane. We’ll now create a Placement rule that will apply to the selected components.
28. Within the PCB Filter panel, click on Create Rule near the bottom of the panel
as shown in Figure 242.

<!-- p.193 -->

*Figure 242. Creating a Clearance Rule from the PCB Filter panel*
29. In the Choose Design Rule Type window, under Placement, click on Component
Clearance Constraint. Click OK.
30. We will define a component clearance constraint between components of the
Anderson_BLK_RHT_BOT footprint and components of the Anderson_Red_RHT_BOT
footprint.
31. In the PCB Rules and Constraints Editor, define the rules through the following procedure.
Refer to Figure 243 for the following steps:
a) Copy the query from Where The First Object Matches field with Ctrl+C.
b) Change the Where The Second Object Matches from All to Custom query and paste
the query into the field using Ctrl+V.
c) Then, change “Anderson_BLK_RHT_BOT” to “Anderson_Red_RHT_BOT”.
Please keep in mind that the query is case sensitive.
d) Rename the rule to “Anderson”
e) Set the minimum horizontal clearance to 100mil.

<!-- p.194 -->

*Figure 243. Anderson Component Clearance rule definition*
32. Ensure that the newly created Anderson Component Clearance rule is of the highest priority
as described in Section 19.3.2 Rule Priorities.
33. Click Close and then click OK.

### 19.5.2 Verifying Applied Design Rules in the PCB

34. Go to  Preferences. Under the PCB Editor branch, open the General page. Ensure that
Online DRC is enabled. Click OK. Hit Shift+C to clear any masks or selection.
35. Notice that 5 components (RLY4, RLY3, PWRP1, PWRN1, RLY1) have green highlights as they
are violating the new Component Clearance constraint. Moving the components will remove
or add the green highlight depending on the distance between each other.
36. Drag RLY4 away from the other components to remove the violations on RLY4 and RLY3.
37. Drag PWRN1 towards RLY4; while dragging, hit R to change the component pushing mode to
Push:Avoid, as indicated in the Heads-up Display. Drop it to the right of RLY4.
38. Lastly, drag RLY1 towards RLY4 and drop it to the left of RLY4.
Notice the clearance allowed between RLY1 and RLY4 is larger than between RLY4 and
PWRN1, because of the Anderson Component Clearance rule defined earlier. This can be
seen in Figure 244 below.

<!-- p.195 -->

*Figure 244. Applied Anderson Component Clearance constraint*

<!-- p.196 -->

## 19.6 Design Rule Wizard

41. We will now see how we can create design rules using the Design Rule Wizard.
42. Go to Design » Rule Wizard… and click Next.
43. Set:
a) Name to PwrWidth
b) Comment to Need wider traces for power
44. Select Width Constraint as shown in Figure 245 and click Next.

*Figure 245. Rule Wizard rule type setup*
45. Select A Few Nets for the Rule Scope and click Next.
46. Within the Advanced Rule Scope:
a) Change the first Belongs to Nets condition value field to 5V.
b) Change the second Belongs to Nets condition value field to 12V.
c) Right click on the third Belongs to Nets condition and click on Delete. Repeat the step
for the fourth condition as well.
d) Ensure that the operator is set to OR. See Figure 246 for the final configuration of the
rule.

<!-- p.197 -->

*Figure 246. Rule Wizard configuration*
47. Click Next. Verify that its priority is the highest on the list (#1).
48. Click Next. Check the Launch main design rules dialog checkbox, then click Finish.
49. The PCB Rules and Constraints Editor will appear with the new rule. We can then modify the
minimum, preferred and maximum width constraints for this rule as shown in Figure 247.

*Figure 247. New PwrWidth rule created*
The PowerNets_Width rule which we created in Section 19.4 Design Rule Using Net
Classes is now invalid and superseded by the PwrWidth rule. Objects within the 12V
nets will now only be applied by the PwrWidth rule.
50. Click OK to close the Design Rules dialog. Save and Close all documents.
